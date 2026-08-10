import re
import logging
from difflib import SequenceMatcher


logger = logging.getLogger(__name__)

def normalize_name(name):
    """Step 6: Convert to RAHULVERMA format."""
    if not name: return ""
    # Uppercase and strip everything except A-Z
    text = name.upper()
    return re.sub(r'[^A-Z]', '', text)

def verify_aadhaar_document(uploaded_file, expected_name, expected_number):
    """
    Enterprise-Grade Aadhaar Verification with Multi-Stage Checks (Requirement 1-10).
    """
    from django.conf import settings
    
    print("\n" + "="*40)
    print(f"KYC ENGINE: PaddleOCR {'(DEBUG MODE)' if settings.DEBUG else ''}")
    print("="*40)

    res = {
        "verified": False,
        "name_match": False,
        "number_match": False,
        "confidence": 0.0,
        "extracted_name": "",
        "extracted_number": "",
        "extracted_dob": "",
        "extracted_gender": "",
        "error": None,
        "error_code": None,
        "review_required": False,
        "warning": None,
        "stages": {
            "text_found": False,
            "id_found": False,
            "name_found": False,
            "dob_found": False,
            "gender_found": False,
            "template_matched": False
        }
    }

    try:
        from ai_features.services.ocr_engine import OCREngine
        engine = OCREngine()
        # Step 1: Multi-Pass Extraction (Requirement 6)
        # Pass A: Raw Box Extraction
        raw_results = engine.extract_with_boxes(uploaded_file)
        
        # Pass B & C: Fallback to compat text if Box extraction is empty (Requirement 6)
        if not raw_results or len(raw_results) < 3:
             print("KYC ENGINE: Initial box pass weak, triggering robust secondary pass...")
             from ai_features.services.ocr_engine import extract_text_compat
             compat_text = extract_text_compat(uploaded_file)
             
             if compat_text:
                 # Reconstruct lines from robust compat pass
                 raw_results = [{"text": line, "confidence": 0.75, "box": [[0,0],[0,0],[0,0],[0,0]]} for line in compat_text.splitlines() if line.strip()]
             
        # MANDATORY LOGGING (Requirement 3)
        print("-" * 30)
        print("KYC DEBUG: RAW LINES DETECTED")
        for i, r in enumerate(raw_results[:10]):
            print(f"Line {i}: {r['text']} (Conf: {r.get('confidence',0):.2f})")
        print("-" * 30)

        if not raw_results:
            res["error"] = "OCR failed to detect readable text. Upload clearer front-side image."
            res["error_code"] = "ocr_fail"
            return res

        res["stages"]["text_found"] = True

        # Clean and sort lines
        processed_lines = []
        full_document_text = ""
        for line in raw_results:
            text = line.get('text', '').strip()
            if not text: continue
            full_document_text += " " + text
            
            conf = line.get('confidence', 0.0)
            box = line.get('box', [])
            y_pos = min(p[1] for p in box) if box else 0
            
            processed_lines.append({
                "text": text,
                "confidence": conf,
                "y_position": y_pos
            })

        processed_lines.sort(key=lambda x: x['y_position'])
        full_document_text = full_document_text.upper()

        # Requirement 5: Smarter Number Extraction
        # Aadhaar Number (12 digits with optional spaces/newlines)
        # Regex: \d{4} followed by space/newline/nothing thrice
        aadhaar_pattern = r'(\d{4}[\s\n]?\d{4}[\s\n]?\d{4})'
        dob_pattern = r'(\d{2}/\d{2}/\d{4}|\d{4})'
        gender_pattern = r'(MALE|FEMALE)'

        # Step 2: ID Detection
        number_candidates = []
        # First check full document text (Requirement 5)
        all_num_matches = re.findall(aadhaar_pattern, full_document_text)
        for val in all_num_matches:
            clean_num = re.sub(r'[\s\n]', '', val)
            if len(clean_num) == 12:
                number_candidates.append({"number": clean_num, "confidence": 0.8})

        # Then check individual lines for higher precision
        for line in processed_lines:
            match = re.search(aadhaar_pattern, line['text'])
            if match:
                clean_num = re.sub(r'[\s\n]', '', match.group(0))
                if len(clean_num) == 12:
                    number_candidates.append({
                        "number": clean_num,
                        "confidence": line['confidence'],
                        "y_position": line['y_position']
                    })

        if number_candidates:
            res["stages"]["id_found"] = True
            number_candidates.sort(key=lambda x: x['confidence'], reverse=True)
            res["extracted_number"] = number_candidates[0]["number"]
            expected_num_clean = re.sub(r'\D', '', str(expected_number))
            res["number_match"] = (res["extracted_number"] == expected_num_clean)

        # DOB and Gender
        dob_match = re.search(dob_pattern, full_document_text)
        if dob_match:
            res["extracted_dob"] = dob_match.group(1)
            res["stages"]["dob_found"] = True
            
        gender_match = re.search(gender_pattern, full_document_text)
        if gender_match:
            res["extracted_gender"] = gender_match.group(1)
            res["stages"]["gender_found"] = True

        # Template Keywords
        template_keywords = ["GOVERNMENT", "INDIA", "UIDAI", "AUTHORITY"]
        if any(kw in full_document_text for kw in template_keywords):
            res["stages"]["template_matched"] = True

        # Step 3: Name Detection
        metadata_keywords = ["DOB", "YEAR", "MALE", "FEMALE", "GOVERNMENT", "INDIA", "UIDAI", "ADDRESS", "MOBILE", "PHONE", "GOVT", "AUTHORITY", "UNIQUE", "FATHER", "ENROLLMENT", "HELP"]
        name_candidates = []
        max_y = max([p['y_position'] for p in processed_lines]) if processed_lines else 1
        
        for line in processed_lines:
            text = line['text']
            l_upper = text.upper()
            if any(kw in l_upper for kw in metadata_keywords): continue
            
            # Use lenient words check
            words = text.split()
            if 2 <= len(words) <= 6 and 5 <= len(text) <= 50 and line['confidence'] >= 0.40:
                norm_cand = normalize_name(text)
                norm_exp = normalize_name(expected_name)
                sim = SequenceMatcher(None, norm_cand, norm_exp).ratio()
                
                score = (line['confidence'] * 30) + (sim * 40)
                if line['y_position'] < max_y * 0.5: score += 10 
                
                name_candidates.append({"text": text, "score": score, "confidence": line['confidence'], "sim": sim})

        if name_candidates:
            res["stages"]["name_found"] = True
            name_candidates.sort(key=lambda x: x['score'], reverse=True)
            res["extracted_name"] = name_candidates[0]["text"]
            res["name_match"] = (name_candidates[0]["sim"] >= 0.80) # More lenient

        # Requirement 4: Reduced Confidence Thresholds
        ocr_avg = sum(p['confidence'] for p in processed_lines) / len(processed_lines) if processed_lines else 0
        name_sim = name_candidates[0]['sim'] if name_candidates else 0
        final_conf = (ocr_avg * 0.4) + (name_sim * 0.4) + (0.2 if res["number_match"] else 0)
        res["confidence"] = round(final_conf, 3)

        base_score = final_conf * 100
        print(f"KYC FINAL SCORE: {base_score:.1f}")

        # Requirement 8: Debug/Test Mode
        is_strict = not settings.DEBUG
        
        # Decision Logic (Enterprise Grade - Requirement 5 & 8)
        # 1. Base Metrics
        ocr_conf_score = round(ocr_avg * 100, 1) if processed_lines else 0.0
        name_sim_score = round(name_sim * 100, 1) if name_candidates else 0.0
        
        # 2. Map Outcomes to Codes and Messages (Requirement 1 & 3)
        res["reason_code"] = None
        res["reason_text"] = None
        res["user_message"] = None # Never reveal technical percentages to users

        if not res["number_match"]:
             res["verified"] = False
             res["reason_code"] = "AADHAAR_NUMBER_MISMATCH"
             res["reason_text"] = f"Aadhaar mismatch: Submitted {expected_number}, Found {res['extracted_number']}"
             res["user_message"] = "The identity number provided does not match the uploaded document."
        elif not res["stages"]["name_found"]:
             res["verified"] = False
             res["reason_code"] = "DOCUMENT_UNREADABLE"
             res["reason_text"] = "Name not detected on document."
             res["user_message"] = "We could not verify your identity details. Please upload a clearer ID document."
        else:
            # Main Decision Matrix
            if name_sim >= 0.98 and ocr_avg >= 0.60:
                res["verified"] = True
                res["reason_code"] = "AUTO_APPROVED"
                res["reason_text"] = "High confidence auto-approval"
                res["user_message"] = "Your identity has been verified successfully."
            elif name_sim >= 0.90 and name_sim < 0.98:
                res["verified"] = False
                res["review_required"] = True
                res["reason_code"] = "MANUAL_REVIEW_REQUIRED"
                res["reason_text"] = f"Moderate name mismatch ({name_sim_score}%) with valid identity number"
                res["user_message"] = "Your identity details require manual verification. Our team will review shortly."
            elif ocr_avg < 0.60:
                res["verified"] = False
                res["review_required"] = True
                res["reason_code"] = "LOW_OCR_CONFIDENCE"
                res["reason_text"] = f"Low document quality (OCR: {ocr_conf_score}%) requires manual audit"
                res["user_message"] = "The uploaded document is unclear. Please upload a clearer image."
            elif name_sim < 0.90:
                res["verified"] = False
                res["reason_code"] = "NAME_MAJOR_MISMATCH"
                res["reason_text"] = f"Major name mismatch: Extracted '{res['extracted_name']}' vs Expected '{expected_name}' ({name_sim_score}%)"
                res["user_message"] = "We could not verify your identity details. Please recheck your information or upload a clearer ID document."
            else:
                res["verified"] = False
                res["reason_code"] = "MULTIPLE_FIELDS_MISMATCH"
                res["reason_text"] = "Multiple verification heuristics failed"
                res["user_message"] = "Identity verification failed. Please ensure the document is a valid official Aadhaar."

        # Final audit metrics for database (Requirement 4)
        res["audit_metrics"] = {
            "name_similarity": name_sim_score,
            "aadhaar_match": res["number_match"],
            "ocr_confidence": ocr_conf_score,
            "decision": "verified" if res["verified"] else ("manual_review" if res.get("review_required") else "rejected"),
            "reason_code": res["reason_code"],
            "reason_text": res["reason_text"],
            "manual_action": None
        }

        # Logging (Requirement 6)
        print(f"KYC STAGES: {res['stages']}")
        print(f"METRICS: {res['audit_metrics']}")
        print(f"USER MSG: {res['user_message']}")
        print("="*40 + "\n")

    except Exception as e:
        logger.error(f"KYC Verification Critical Error: {e}")
        res["error"] = f"Verification engine error: {str(e)}"
        res["review_required"] = True

    return res

def save_kyc_record(user, result, expected_name, expected_number, file_name, existing_id=None):
    """
    Enterprise KYC Persistence Service.
    Supports update_or_create logic to link anonymous attempts to registered users.
    """
    from accounts.models import AadhaarKYCVerification
    from django.utils import timezone
    from django.db import transaction
    
    # 1. Status decision mapping
    status = "rejected" # Default to rejected for any mismatch
    if result.get("verified"):
        status = "verified"
    elif result.get("review_required"):
        status = "manual_review"
    
    # 2. Forensic Metrics
    details = result.get("audit_metrics", {})
    if not details: # Fallback
        details = {
            "name_similarity": result.get("name_similarity", 0),
            "ocr_confidence": result.get("ocr_confidence", 0),
            "aadhaar_match": result.get("aadhaar_match", False),
            "reason_code": result.get("reason_code", "AUTO_LOG"),
            "reason_text": result.get("reason_text", "Audit captured via registration flow")
        }

    # 3. Idempotent Save / Update Logic
    defaults = {
        "user": user,
        "submitted_full_name": expected_name,
        "submitted_aadhaar_number": expected_number,
        "extracted_name": result.get("extracted_name", ""),
        "extracted_number": result.get("extracted_number", ""),
        "source_document_name": file_name,
        "status": status,
        "details": details,
        "verified_at": timezone.now() if status == "verified" else None
    }

    try:
        if existing_id:
            # Link or Update existing attempt
            logger.debug(f"Updating existing KYC record ID: {existing_id}")
            AadhaarKYCVerification.objects.filter(id=existing_id).update(**defaults)
            record = AadhaarKYCVerification.objects.get(id=existing_id)
        else:
            # Create fresh attempt
            logger.debug(f"Creating fresh KYC record for {expected_name}")
            record = AadhaarKYCVerification.objects.create(**defaults)
            
        logger.info(f"KYC Record Saved: ID={record.id}, Status={record.status}, User={user}")
        return record

    except Exception as e:
        logger.error(f"DATABASE PERSISTENCE ERROR in save_kyc_record: {str(e)}")
        raise e
