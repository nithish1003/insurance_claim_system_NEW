import logging
import os
import re
from typing import Optional
from difflib import SequenceMatcher
import threading

logger = logging.getLogger(__name__)

# Configuration for fallback/engine internals
TESSERACT_CMD = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

class OCRService:
    """
    Singleton service for extracting text from images.
    Implements lazy-loading for heavy OCR engines (Requirement 2 & 10).
    """

    _instance = None
    _lock = threading.Lock()
    _engine = None

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(OCRService, cls).__new__(cls)
            return cls._instance

    @classmethod
    def get_engine(cls):
        """Lazy loader for the backend OCR Engine."""
        if cls._engine is None:
            with cls._lock:
                if cls._engine is None:
                    # Requirement 8: Initialization Logging
                    print("\n[AI-SERVICE] Initializing OCR Engine Pipeline...")
                    from ai_features.services.ocr_engine import OCREngine
                    cls._engine = OCREngine()
                    print("[AI-SERVICE] OCR Engine Pipeline Ready.")
        return cls._engine

    # =========================================================================
    # 1. HELPER UTILITIES (Foundational Logic)
    # =========================================================================

    def _normalize_final(self, name: str) -> str:
        """Returns uppercase letters only, stripping all noise."""
        return re.sub(r'[^A-Z]', '', (name or "").upper())

    def _get_words(self, name: str) -> list:
        """Splits into significant alpha-words only."""
        return re.sub(r'[^A-Z ]', '', (name or "").upper()).split()

    def _has_word_overlap(self, candidate: str, expected: str) -> bool:
        """
        Anti-Fraud overlap guard. 
        Supports: Exact word, Merged name (RAHULVERMA), and Fuzzy character match.
        """
        c_words = self._get_words(candidate)
        e_words = self._get_words(expected)
        
        # Pass 1: Set-based intersection
        if set(c_words) & set(e_words):
            return True
            
        # Pass 2: Substring/Merged support
        cand_norm = self._normalize_final(candidate)
        exp_norm = self._normalize_final(expected)
        if exp_norm in cand_norm or cand_norm in exp_norm:
            return True
            
        # Pass 3: Fuzzy character overlap (Tolerates minor OCR jitter)
        for cw in c_words:
            if len(cw) < 3: continue
            for ew in e_words:
                if len(ew) < 3: continue
                if SequenceMatcher(None, cw, ew).ratio() >= 0.8:
                    return True
        return False

    def _is_valid_aadhaar_name(self, name: str) -> bool:
        """
        Heuristic filter to identify legitimate human names vs address labels.
        Supports: 2+ word names and long merged single-word names (RAHULVERMA).
        """
        if not name: return False
        clean_name = name.upper().strip()
        
        # 🛡️ Metadata / Address Label Rejection
        unwanted = {
            "DOB", "YEAR", "MALE", "FEMALE", "GENDER", "INDIA", "GOVT", "UIDAI", 
            "ADDRESS", "RESIDENTIAL", "FATHER", "MOTHER", "PHOTO", "SIGNATURE", 
            "VERIFIED", "VALID", "ENROLLMENT", "STREET", "ROAD", "VILLAGE", "DISTRICT",
            "STATE", "AUTHORITY", "GOVERNMENT", "IDENTIFICATION", "UNIVERSAL", "UNIQUE"
        }
        if any(label in clean_name for label in unwanted):
            return False

        words = clean_name.split()
        
        # Multi-word names (Standard)
        if 2 <= len(words) <= 5:
            if all(w.isalpha() for w in words):
                return True
                
        # Merged / Single-word names (OCR Artifacts)
        if len(words) == 1:
            word = words[0]
            if len(word) >= 5 and word.isalpha():
                return True
                
        return False

    def _score_aadhaar_name_candidate(self, name, expected_name, index, total_cands):
        """Final-grade probabilistic selection engine."""
        score = 0.0
        
        norm_name = self._normalize_final(name)
        norm_expected = self._normalize_final(expected_name)
        
        # 1. Similarity (60%)
        if norm_name and norm_expected:
            similarity = SequenceMatcher(None, norm_name, norm_expected).ratio()
            score += similarity * 60
            
        # 2. Position Bias (10%) - Identities are usually at the top
        if index < total_cands * 0.3:
            score += 10
            
        # 3. Word Count / Layout Bias (20%)
        wc = len(name.split())
        if wc == 2: score += 20
        elif wc == 3: score += 10
        elif wc > 4: score -= 20 # Penalize long address lines
        
        # 4. Word Overlap Bonus (Match stability)
        c_words = set(self._get_words(name))
        e_words = set(self._get_words(expected_name))
        score += len(c_words & e_words) * 10
        
        return score

    # =========================================================================
    # 2. EXTRACTION ENGINES
    # =========================================================================

    def extract_text(self, file_path: str, *, lang: str = "eng", psm: int = 3) -> str:
        """High-resolution multi-pass OCR gateway switched to PaddleOCR."""
        if not file_path or not os.path.exists(file_path):
            return ""

        try:
            # 🚀 Use lazy-loaded engine
            engine = self.get_engine()
            combined_text = engine.extract_text(file_path)
            
            # If Paddle fails or is empty, use pytesseract multi-pass as fallback (Step 10)
            if not combined_text:
                print("DEBUG: PaddleOCR empty, triggering Tesseract fallback pass...")
                from PIL import Image, ImageOps, ImageEnhance
                import pytesseract
                
                if os.path.exists(TESSERACT_CMD):
                    pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD
                
                source_image = Image.open(file_path).convert("L")
                source_image = ImageOps.exif_transpose(source_image)
                source_image = ImageOps.autocontrast(source_image)
                
                enhancer = ImageEnhance.Sharpness(source_image)
                source_image = enhancer.enhance(2.0)
                
                # Smart Resize for 300DPI equivalent
                width, height = source_image.size
                if width < 1800:
                    scale = 1800 / width
                    source_image = source_image.resize((int(width * scale), int(height * scale)), Image.Resampling.LANCZOS)
                
                pass1 = pytesseract.image_to_string(source_image, lang=lang, config=f"--psm {psm}")
                pass2 = pytesseract.image_to_string(source_image, lang=lang, config="--psm 6")
                pass3 = pytesseract.image_to_string(source_image, lang=lang, config="--psm 11")
                
                combined_text = f"{pass1}\n{pass2}\n{pass3}"
            
            print(f"DEBUG: OCR Aggregate Length: {len(combined_text)}")
            return combined_text.strip()
        except Exception as e:
            logger.error(f"OCR Pipeline Error: {str(e)}")
            # Last ditch effort using compat wrapper
            try:
                from ai_features.services.ocr_engine import extract_text_compat
                return extract_text_compat(file_path)
            except:
                return ""

    def _extract_aadhaar_name(self, text: str, expected_name: str) -> Optional[str]:
        """Aadhaar-specific name prioritization with label-aware scrubbing."""
        def normalize_line(l):
            l = l.upper()
            # Reject relative/guardian lines
            guardians = ["S/O", "D/O", "W/O", "SON OF", "DAUGHTER OF", "WIFE OF", "SO ", "DO ", "WO "]
            if any(l.startswith(p) for p in guardians): return ""
            
            # Strip standard labels
            for p in ["NAME", "UNIVERSAL", "UNIQUE", "AUTHORITY", "GOVERNMENT", "INDIA"]:
                if l.startswith(p):
                    l = l[len(p):].lstrip(":").lstrip("-").lstrip()
            
            l = re.sub(r'[^A-Z ]', '', l)
            return re.sub(r'\s+', ' ', l).strip()

        # Gather and scrub candidates
        lines = [normalize_line(l) for l in text.splitlines() if normalize_line(l)]
        candidates = list(set(lines))
        # Add bigram candidates (multi-line names)
        for i in range(len(lines)-1):
            candidates.append(f"{lines[i]} {lines[i+1]}")
            
        best_cand = None
        best_score = -1.0
        total = len(candidates)
        
        for i, cand in enumerate(candidates):
            if not self._has_word_overlap(cand, expected_name): continue
            if not self._is_valid_aadhaar_name(cand): continue
            
            score = self._score_aadhaar_name_candidate(cand, expected_name, i, total)
            if score > best_score:
                best_score = score
                best_cand = cand
                
        return best_cand

    def _extract_aadhaar_numbers(self, text: str) -> list[str]:
        """
        Dual-Strategy Aadhaar Extraction: Alphanumeric block repair + Numeric patterns.
        """
        raw = text.upper()
        candidates = []

        # Strategy 1: Find alphanumeric blocks (potential misreads) and repair them
        blocks = re.findall(r'[A-Z0-9]{4}[\s\-]?[A-Z0-9]{4}[\s\-]?[A-Z0-9]{4}', raw)

        rep = {
            'O': '0', 'I': '1', 'L': '1', 'Z': '2', 'E': '3',
            'A': '4', 'S': '5', 'G': '6', 'T': '7', 'B': '8'
        }

        for block in blocks:
            fixed = ""
            for ch in block:
                fixed += rep.get(ch, ch)
            
            # Extract only digits from the repaired block
            fixed_digits = re.sub(r'\D', '', fixed)
            if len(fixed_digits) == 12:
                candidates.append(fixed_digits)

        # Strategy 2: Standard pure digit grouped patterns (XXXX XXXX XXXX)
        pure = re.findall(r'\d{4}\s?\d{4}\s?\d{4}', raw)
        for p in pure:
            candidates.append(re.sub(r'\D', '', p))

        # Strategy 3: Dense stream search (No spaces/hyphens)
        stream = re.sub(r'[^0-9A-Z]', '', raw)
        # Apply repair to stream first
        fixed_stream = ""
        for ch in stream:
            fixed_stream += rep.get(ch, ch)
        
        candidates.extend(re.findall(r'\d{12}', fixed_stream))

        return list(dict.fromkeys(candidates)) # Deduplicate

    # (Previous financial and detail extractors maintained)
    def _extract_facility_name(self, text: str) -> Optional[str]:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        kw = ["HOSPITAL", "MEDICAL", "CLINIC", "MOTORS", "GARAGE", "SERVICE"]
        for line in lines[:7]:
            if any(k in line.upper() for k in kw):
                return re.sub(r"(INV|DATE|BILL|#|:).*", "", line, flags=re.IGNORECASE).strip()
        return None

    def _extract_vehicle_number(self, text: str) -> Optional[str]:
        pattern = r"[A-Z]{2}\s?\d{2}\s?[A-Z]{1,2}\s?\d{4}"
        match = re.search(pattern, text.upper())
        return re.sub(r"\s+", "", match.group(0)) if match else None

    def _extract_financial_amounts(self, line: str) -> list[float]:
        norm = re.sub(r"[\u20b9$€£]", " ", line or "")
        matches = re.findall(r"(?<![A-Za-z])(?:\d{1,3}(?:[,\s]\d{3})+|\d+)(?:\.\d{2})?", norm)
        return [float(m.replace(" ", "").replace(",", "")) for m in matches if m]

    def _extract_financial_amount(self, line: str, *, prefer: str = "last") -> float:
        amts = self._extract_financial_amounts(line)
        if not amts: return 0.0
        return max(amts) if prefer == "max" else amts[-1]

    def extract_claim_details(self, text: str) -> dict:
        """
        Unified details extraction for claims.
        Extracts: Hospital/Garage, Amounts, Vehicle No, Names, etc.
        """
        text_upper = text.upper()
        res = {
            "hospital_name": self._extract_facility_name(text),
            "garage_name": self._extract_facility_name(text), 
            "total_amount": 0.0,
            "subtotal_amount": 0.0,
            "vehicle_number": self._extract_vehicle_number(text),
            "deceased_name": None,
            "nominee_name": None,
            "spare_parts_cost": 0.0,
            "labor_cost": 0.0,
            "medical_cost": 0.0,
            "review_flag": False,
            "confidence": "HIGH"
        }

        # 1. Names Extraction (Heuristics)
        lines = text.splitlines()
        for i, line in enumerate(lines):
            l = line.upper()
            if "DECEASED" in l or "PERSON" in l:
                res["deceased_name"] = re.sub(r"(DECEASED|NAME|:)", "", l).strip()
            if "NOMINEE" in l or "BENEFICIARY" in l:
                res["nominee_name"] = re.sub(r"(NOMINEE|NAME|:)", "", l).strip()

        # 2. Financial Breakdown (Labor vs Parts vs Medical)
        detected_amounts = []

        # 🛑 NON-FINANCIAL IDENTIFIER NOISE FILTER KEYWORDS
        # Lines containing these are IDs, serial numbers, or metadata — NOT monetary values.
        NOISE_KEYWORDS = [
            "REGISTRATION", "PATIENT ID", "POLICY NO", "UUID", "DATE:",
            "CHASSIS", "ENGINE NUMBER", "ENGINE NO", "CLAIM ID",
            "AADHAAR", "AADHAR", "UID", "PAN", "PASSPORT",
            "DOB", "DATE OF BIRTH", "GENDER", "MOBILE", "PHONE",
            "DUMMY", "TEST PURPOSE", "VERIFICATION", "SCAN FOR",
            "CLM20",  # Claim ID prefix pattern (CLM2026...)
        ]

        # Aadhaar number pattern: 4 digits, space, 4 digits, space, 4 digits
        aadhaar_pattern = re.compile(r'^\s*\d{4}\s+\d{4}\s+\d{4}\s*$')
        # Alphanumeric serial/ID pattern (e.g., MBLHA12987456321, HA11E4587214)
        serial_pattern = re.compile(r'[A-Z]+\d+[A-Z0-9]*|\d+[A-Z]+[A-Z0-9]*', re.IGNORECASE)

        # Maximum credible single-line amount (₹1 crore = 10 million)
        MAX_CREDIBLE_AMOUNT = 10_000_000.0

        for line in lines:
            l = line.upper()

            # Skip noise lines
            if any(k in l for k in NOISE_KEYWORDS):
                continue

            # Skip lines that look like standalone Aadhaar numbers
            if aadhaar_pattern.match(line.strip()):
                continue

            # Skip lines that are purely alphanumeric serial/ID strings (no financial context)
            stripped = line.strip()
            if stripped and serial_pattern.fullmatch(stripped):
                continue

            amt = self._extract_financial_amount(l)
            if amt > 0 and amt <= MAX_CREDIBLE_AMOUNT:
                detected_amounts.append(amt)
                
                # Classify expenditure
                is_medical = any(k in l for k in ["BED", "ROOM", "CONSULTATION", "LAB", "TEST", "MEDICINE", "NURSING", "GST", "HOSPITAL"])
                is_motor = any(k in l for k in ["PART", "SPARE", "BUMPER", "HEADLIGHT", "WHEEL", "LABOR", "SERVICE", "PAINTING", "WORK"])
                
                if is_motor:
                    if any(k in l for k in ["PART", "SPARE", "BUMPER", "HEADLIGHT", "WHEEL"]):
                        res["spare_parts_cost"] += amt
                    else:
                        res["labor_cost"] += amt
                elif is_medical:
                    res["medical_cost"] += amt

                # 🎯 Total Detection Logic
                if any(k in l for k in ["TOTAL AMOUNT PAYABLE", "FINAL PAYABLE", "NET PAYABLE"]):
                    res["total_amount"] = amt # High confidence match
                elif any(k in l for k in ["APPROVED AMOUNT", "APPROVED"]):
                    res["total_amount"] = amt  # Claim bill receipt pattern
                elif "TOTAL" in l and "SUBTOTAL" not in l and res["total_amount"] == 0:
                    res["total_amount"] = amt
                elif "SUBTOTAL" in l:
                    res["subtotal_amount"] = amt

        # 3. Validation & Fallback
        # If no explicit "Total Payable" was found, take the largest detected amount
        if res["total_amount"] == 0 and detected_amounts:
            res["total_amount"] = max(detected_amounts)
            res["confidence"] = "MEDIUM"

        # Integrity Check (Sum vs Total)
        sum_components = res["spare_parts_cost"] + res["labor_cost"] + res["medical_cost"]
        # Note: medical_cost usually includes Subtotal + GST, so we don't sum it simply if we found a subtotal
        
        if res["total_amount"] > 0 and sum_components > 0:
            # If total is way larger than any component sum, flag it
            if res["total_amount"] > sum_components * 1.5:
                res["review_flag"] = True
                res["confidence"] = "LOW"

        # Global confidence based on text length
        if len(text) < 50:
            res["confidence"] = "LOW"

        return res

    # =========================================================================
    # 3. VERIFICATION INTERFACE
    # =========================================================================

    def _names_match(self, ext: str, exp: str) -> bool:
        """Adaptive fuzzy identity matching."""
        if not ext or not exp: return False
        n_ext, n_exp = self._normalize_final(ext), self._normalize_final(exp)
        if n_ext == n_exp: return True
        sim = SequenceMatcher(None, n_ext, n_exp).ratio() * 100
        return sim >= (82 if len(n_exp) <= 10 else 85)

    def verify_aadhaar(self, file_path: str, name: str, number: str) -> dict:
        """
        Master identity verification entry point.
        Delegates to Enterprise KYC Service.
        """
        try:
            from ai_features.services.kyc_verification_service import verify_aadhaar_document
            return verify_aadhaar_document(file_path, name, number)
        except Exception as e:
            import traceback; traceback.print_exc()
            return {"verified": False, "error": f"Diagnostic Failure: {str(e)}"}

# Top-level bridges
def perform_ocr(path): return OCRService().extract_text(path)
def extract_details(text): return OCRService().extract_claim_details(text)
def verify_identity(path, name, num): return OCRService().verify_aadhaar(path, name, num)
def verify_aadhaar(path, name, num): return OCRService().verify_aadhaar(path, name, num)

# ✅ Global OCR Engine Access for Lazy Loading (Enterprise Standard)
def get_ocr_engine():
    from ai_features.services.ocr_engine import get_ocr
    return get_ocr()
