import os
import re
import logging
import tempfile
from PIL import Image, ImageOps, ImageEnhance
from django.conf import settings
from ai_features.services.ocr_service import OCRService as BaseOCRService
from claims.utils import compare_vehicle_numbers

logger = logging.getLogger(__name__)

class RCOCRService:
    """
    Service to handle RC Document OCR extraction, preprocessing, and validation.
    """

    def preprocess_image(self, file_path: str) -> str:
        """
        Enhances the uploaded image for better OCR accuracy.
        Saves the preprocessed image to a temporary file and returns its path.
        """
        try:
            print("[RC-OCR-DEBUG] Preprocessing image for OCR accuracy enhancement...")
            img = Image.open(file_path)
            
            # Ensure RGB format
            if img.mode != 'RGB':
                img = img.convert('RGB')
            
            # Autocontrast to make text stand out
            img = ImageOps.autocontrast(img)
            
            # Mild sharpening
            enhancer = ImageEnhance.Sharpness(img)
            img = enhancer.enhance(1.5)
            
            # Standardize resolution/resize if small
            width, height = img.size
            if width < 1500:
                scale = 1500 / width
                img = img.resize((1500, int(height * scale)), Image.Resampling.LANCZOS)
            
            # Save to temporary file
            temp_suffix = os.path.splitext(file_path)[1] or '.png'
            tf = tempfile.NamedTemporaryFile(delete=False, suffix=temp_suffix)
            img.save(tf.name)
            tf.close()
            
            print(f"[RC-OCR-DEBUG] Preprocessed image saved to: {tf.name}")
            return tf.name
        except Exception as e:
            print(f"[RC-OCR-DEBUG] Error during preprocessing, falling back to original: {e}")
            return file_path

    def extract_text_from_rc(self, file_path: str) -> str:
        """
        Runs OCR on the RC image using PaddleOCR with Pytesseract fallback.
        """
        base_service = BaseOCRService()
        
        # Preprocess first
        preprocessed_path = self.preprocess_image(file_path)
        
        try:
            print(f"[RC-OCR-DEBUG] Extracting text from: {preprocessed_path}")
            # Use base OCR extraction
            text = base_service.extract_text(preprocessed_path)
            
            print(f"[RC-OCR-DEBUG] OCR Extraction Completed. Text Length: {len(text)}")
            return text
        finally:
            # Clean up the preprocessed temp file if it's different from the original
            if preprocessed_path != file_path and os.path.exists(preprocessed_path):
                try:
                    os.remove(preprocessed_path)
                    print(f"[RC-OCR-DEBUG] Cleaned up temporary preprocessed image: {preprocessed_path}")
                except Exception as e:
                    print(f"[RC-OCR-DEBUG] Failed to remove temp preprocessed file: {e}")

    def extract_vehicle_number(self, text: str) -> str:
        """
        Extracts vehicle registration number from OCR text using regex.
        Supports: TN09BX4587, TN 09 BX 4587, MH12AB1234, etc.
        """
        if not text:
            return ""
        
        # Pattern to match standard Indian vehicle formats
        # e.g., TN 09 BX 4587, TN09BX4587, MH12AB1234, TN-10-AB-1234
        pattern = r"[A-Z]{2}[-\s]?\d{2}[-\s]?[A-Z]{1,2}[-\s]?\d{4}"
        match = re.search(pattern, text.upper())
        if match:
            extracted = match.group(0)
            print(f"[RC-OCR-DEBUG] Regex Matched Vehicle Number: {extracted}")
            return extracted
        
        print("[RC-OCR-DEBUG] Regex failed to extract vehicle number from OCR text.")
        return ""

    def normalize_vehicle_number(self, vnum: str) -> str:
        """
        Normalize vehicle number by removing spaces, hyphens, special characters, and converting to uppercase.
        """
        if not vnum:
            return ""
        # Remove spaces, hyphens, dots, and any non-alphanumeric character
        normalized = re.sub(r"[^A-Z0-9]", "", vnum.upper())
        return normalized

    def canonicalize_vnum(self, vnum: str) -> str:
        """
        Convert to uppercase, strip non-alphanumeric, and replace common OCR ambiguities
        so that letters and numbers confused by OCR are normalized to the same canonical character.
        """
        if not vnum:
            return ""
        cleaned = re.sub(r"[^A-Z0-9]", "", vnum.upper())
        replacements = {
            'O': '0',
            'I': '1',
            'L': '1',
            'Z': '2',
            'S': '5',
            'B': '8',
            'G': '6',
            'T': '7',
            'A': '4'
        }
        return "".join(replacements.get(c, c) for c in cleaned)

    def validate_rc(self, file_path: str, manual_vnum: str) -> bool:
        """
        Validates the RC document against the manual vehicle number.
        Returns True if matched, False otherwise.
        """
        print(f"[RC-OCR-DEBUG] Starting RC Document Validation. Manual vehicle number: {manual_vnum}")
        
        ocr_text = self.extract_text_from_rc(file_path)
        extracted_vnum = self.extract_vehicle_number(ocr_text)
        
        normalized_manual = self.normalize_vehicle_number(manual_vnum)
        
        # 1. Compare extracted number with manual number
        if extracted_vnum:
            normalized_extracted = self.normalize_vehicle_number(extracted_vnum)
            print(f"[RC-OCR-DEBUG] Comparing normalized manual: '{normalized_manual}' with normalized extracted: '{normalized_extracted}'")
            if normalized_extracted == normalized_manual:
                print("[RC-OCR-DEBUG] Validation SUCCESS: Exact normalized match found.")
                return True
            
            # Using existing compare_vehicle_numbers utility which allows fuzzy match
            match_found, similarity, _, _ = compare_vehicle_numbers(normalized_extracted, normalized_manual)
            print(f"[RC-OCR-DEBUG] compare_vehicle_numbers match: {match_found} (Similarity: {similarity:.2%})")
            if match_found:
                print("[RC-OCR-DEBUG] Validation SUCCESS: Fuzzy match found.")
                return True
        
        # 2. Fallback logic: If regex extraction fails or doesn't match, check if normalized manual number exists in normalized OCR text
        if ocr_text:
            normalized_ocr_text = self.normalize_vehicle_number(ocr_text)
            print(f"[RC-OCR-DEBUG] Running Fallback Check: Is manual number '{normalized_manual}' present in OCR text?")
            if normalized_manual in normalized_ocr_text:
                print("[RC-OCR-DEBUG] Validation SUCCESS: Fallback substring check passed.")
                return True

        # 3. OCR-error-tolerant validation (using canonicalized matching)
        if ocr_text:
            print("[RC-OCR-DEBUG] Running OCR-error-tolerant validation...")
            canonical_manual = self.canonicalize_vnum(manual_vnum)
            
            # Extract all potential vehicle-like patterns to check matches against
            # e.g., XX-XX-XX-XXXX with flexible characters
            pattern = r"[A-Z0-9]{2}[-\s]?[A-Z0-9]{2}[-\s]?[A-Z0-9]{1,2}[-\s]?[A-Z0-9]{4}"
            candidates = re.findall(pattern, ocr_text.upper())
            for cand in candidates:
                canonical_cand = self.canonicalize_vnum(cand)
                if canonical_cand == canonical_manual:
                    print(f"[RC-OCR-DEBUG] Validation SUCCESS: OCR-error-tolerant exact match found for candidate '{cand}'.")
                    return True
            
            # Canonical substring fallback
            canonical_text = self.canonicalize_vnum(ocr_text)
            if canonical_manual in canonical_text:
                print("[RC-OCR-DEBUG] Validation SUCCESS: OCR-error-tolerant substring fallback passed.")
                return True
        
        print("[RC-OCR-DEBUG] Validation FAILED: No match found.")
        return False
