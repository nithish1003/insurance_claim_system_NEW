"""
OCR Document Processing Service
Uses pytesseract to extract text from claim documents
"""

import os
import pytesseract
from PIL import Image
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Note: In Windows, you might need to specify the tesseract executable path
TESSERACT_CMD = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
if os.path.exists(TESSERACT_CMD):
    pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD

class OCRService:
    """Singleton service for extracting text from images using Tesseract"""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def extract_text(self, file_path: str) -> str:
        """
        Extract text from an image file
        
        Args:
            file_path: Absolute path to the document file
            
        Returns:
            Extracted text content or empty string
        """
        if not file_path or not os.path.exists(file_path):
            logger.error(f"OCR Error: File not found at {file_path}")
            return ""
            
        try:
            logger.info(f"🔍 Starting real OCR extraction on: {os.path.basename(file_path)}")
            
            # 1. Open Image
            image = Image.open(file_path)
            
            # 2. Basic Preprocessing (Optional: convert to L for better contrast)
            # image = image.convert('L')
            
            # 3. Perform OCR
            text = pytesseract.image_to_string(image)
            
            # 4. Clean up results
            cleaned_text = text.strip()
            
            if not cleaned_text:
                logger.warning(f"⚠️ OCR completed but no text was found in {os.path.basename(file_path)}")
            else:
                word_count = len(cleaned_text.split())
                logger.info(f"✅ OCR successful: Extracted {word_count} words from {os.path.basename(file_path)}")
                
            return cleaned_text
            
        except Exception as e:
            logger.error(f"❌ OCR Extraction Failed: {str(e)}")
            return ""

    def extract_claim_details(self, text: str) -> dict:
        """
        Engineered entity extraction for insurance document auditing.
        Targets names and financial totals using prioritized regex patterns.
        """
        import re
        from typing import Any
        details: dict[str, Any] = {
            'patient_name': None,
            'total_amount': 0.0,
        }

        # 1. 🎯 REGEX-BASED PATIENT NAME EXTRACTION
        # Target "PATIENT" keyword and extract the following uppercase line
        # This prevents picking up doctor names or hospital headers
        name_match = re.search(r'PATIENT.*\n([A-Z ]+)', text)
        if name_match:
            candidate = name_match.group(1).strip()
            # Safety check: ensure it's not a generic header or too short
            if len(candidate.split()) >= 2:
                details['patient_name'] = candidate
                logger.info(f"✅ High-confidence name extracted (Regex): {details['patient_name']}")

        # 2. 🛡️ HEURISTIC FALLBACK (Legacy Engine)
        if not details['patient_name']:
            for line in text.split('\n'):
                clean = line.strip()
                # Profile: Uppercase, 2-4 words, no numbers, no emails
                if (clean.isupper() and 
                    "@" not in clean and 
                    not any(c.isdigit() for c in clean) and 
                    2 <= len(clean.split()) <= 4):
                    details['patient_name'] = str(clean)
                    logger.info(f"ℹ️ Fallback name extracted (Heuristic): {details['patient_name']}")
                    break

        # 3. 💰 FINANCIAL TOTAL EXTRACTION
        amount_match = re.search(r'TOTAL\s*\$?(\d+)', text)
        if amount_match:
            details['total_amount'] = float(amount_match.group(1))
            logger.info(f"💰 Extracted Total: {details['total_amount']}")

        return details

    def verify_aadhaar(self, file_path: str, expected_name: str, expected_number: str) -> dict:
        # ... (unchanged) ...
        """
        Specialized OCR for Aadhaar Identity Verification
        Returns: { 'verified': bool, 'extracted_number': str, 'extracted_name': str, 'confidence': float }
        """
        text = self.extract_text(file_path)
        if not text:
            return {"verified": False, "error": "No text extracted from ID proof."}
            
        import re
        # 1. Extract 12-digit Aadhaar pattern (handle spaces/dashes)
        # Regex looks for 3 groups of 4 digits, or 12 contiguous digits
        clean_text = text.replace(" ", "").replace("-", "")
        aadhaar_match = re.search(r'\d{12}', clean_text)
        extracted_number = aadhaar_match.group(0) if aadhaar_match else None
        
        # 2. Extract Name (Heuristic: Look for lines without numbers near the top)
        lines = [l.strip() for l in text.split('\n') if len(l.strip()) > 5]
        extracted_name = None
        for line in lines[:8]:
            # Skip lines with high digit density (likely address or ID)
            digit_count = sum(c.isdigit() for c in line)
            if digit_count / len(line) < 0.2:
                # Basic check: skip lines that are obviously just "INDIA", "Government", etc.
                if any(word in line.upper() for word in ["GOVERNMENT", "INDIA", "UIDAI", "MALE", "FEMALE"]):
                    continue
                extracted_name = line
                break
        
        # 3. Compare with expected
        number_match = (extracted_number == expected_number) if extracted_number else False
        
        # Fuzzy name match (simplified for prototype: check if any parts overlap)
        name_match = False
        if extracted_name and expected_name:
            n1_parts = set(extracted_name.upper().split())
            n2_parts = set(expected_name.upper().split())
            if n1_parts.intersection(n2_parts):
                name_match = True
                
        is_verified = number_match # Number is the primary source of truth
        
        return {
            "verified": is_verified,
            "extracted_number": extracted_number,
            "extracted_name": extracted_name,
            "name_match": name_match,
            "number_match": number_match
        }

def perform_ocr(file_path: str) -> str:
    """Entry point for OCR processing"""
    return OCRService().extract_text(file_path)

def extract_details(text: str) -> dict:
    """Helper to extract entities from OCR text"""
    return OCRService().extract_claim_details(text)

def verify_identity(file_path: str, name: str, number: str) -> dict:
    """Specialized identity verification using OCR"""
    return OCRService().verify_aadhaar(file_path, name, number)
