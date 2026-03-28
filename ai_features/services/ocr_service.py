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
            
            # 1. Open and Pre-process Image
            image = Image.open(file_path)
            
            # 🔥 ENHANCEMENT: Grayscale and Resizing for Higher Fidelity
            # Converting to grayscale reduces noise for Tesseract
            # Resizing ensures smaller text is readable
            image = image.convert('L')
            width, height = image.size
            image = image.resize((width * 2, height * 2), Image.Resampling.LANCZOS)
            
            # 2. Perform OCR with professional psm configuration
            # --psm 3: Fully automatic page segmentation (default) but more sensitive
            text = pytesseract.image_to_string(image, config='--psm 3')
            
            # 3. Clean up results
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
        """
        Specialized OCR for Aadhaar Identity Verification
        Returns: { 'verified': bool, 'extracted_number': str, 'extracted_name': str, 'confidence': float }
        """
        text = self.extract_text(file_path)
        if not text:
            return {"verified": False, "error": "No text extracted from ID proof."}
            
        import re
        # 1. 🔢 Robust Aadhaar Extraction (Date-Aware Engine)
        # 🆕 SECURITY FIX: Some OCR results merge DOB (14021995) with Aadhaar (4821)
        # We must protect the 12-digit identity string from demographic pollution.
        
        # A. Protect the raw text by masking common Date/Year patterns
        # Removes: DD/MM/YYYY, DD-MM-YYYY, and YYYY
        text_masked = re.sub(r'\b(\d{2}[/-]\d{2}[/-]\d{4}|\d{4})\b', ' #### ', text)
        
        # B. Strategy 1: Search for Standard Spaced Format (4-4-4)
        # Most Aadhaar cards print it with groups (e.g., 4821 7395 1264)
        grouped_match = re.search(r'\d{4}[\s-]\d{4}[\s-]\d{4}', text)
        if grouped_match:
            extracted_number = re.sub(r'\D', '', grouped_match.group(0))
            logger.info(f"🎯 High-precision grouped Aadhaar found: {extracted_number}")
        else:
            # Strategy 2: Clean Digit-Stream Extraction (Fallback)
            clean_text = re.sub(r'\D', '', text_masked)
            aadhaar_match = re.search(r'\d{12}', clean_text)
            extracted_number = aadhaar_match.group(0) if aadhaar_match else None
            logger.info(f"ℹ️ Fallback digit-stream extraction: {extracted_number}")

        
        # 2. 📛 Advanced Name Extraction (Context-Aware Architecture)
        lines = [l.strip() for l in text.split('\n') if len(l.strip()) > 3]
        extracted_name = None
        
        # Identity Stop-Words (Lines we know are NOT the name)
        stop_words = ["INDIA", "GOVERNMENT", "UIDAI", "MALE", "FEMALE", "DOB", "YEAR", "BIRTH", "ENROLLMENT", "ADDRESS"]
        
        # Search window: Look for 2-3 word uppercase/CamelCase lines at the top
        for i, line in enumerate(lines[:10]):
            u_line = line.upper()
            
            # Skip demographic headers and branding
            if any(word in u_line for word in stop_words):
                continue
                
            # Skip lines with numbers (addresses or IDs)
            if any(c.isdigit() for c in line):
                continue
                
            # Name Profile: Usually 2-4 words, capitalized or uppercase
            parts = line.split()
            if 2 <= len(parts) <= 4:
                extracted_name = line
                # Break on first high-probability candidate
                break
        
        # 3. 🔍 Fuzzy Comparison Engine
        # Normalize the expected number (remove spaces/dashes) to match the cleaned OCR extraction
        sanitized_expected_number = re.sub(r'\D', '', str(expected_number))
        
        # Number check is rigorous
        number_match = (extracted_number == sanitized_expected_number) if extracted_number else False

        
        # Name check (Tokenized intersection)
        name_match = False
        if extracted_name and expected_name:
            n1_parts = set(re.findall(r'\w+', extracted_name.upper()))
            n2_parts = set(re.findall(r'\w+', expected_name.upper()))
            # If at least two major tokens match, or the name is subset
            if len(n1_parts.intersection(n2_parts)) >= 2 or n2_parts.issubset(n1_parts):
                name_match = True
        
        # 4. 🚀 Verification Finalization
        # In a real environment, number is primary, name is supporting
        # We allow verification if number matches OR (name matches + number is identifiable)
        is_verified = number_match
        
        logger.info(f"[OCR Identity] Match Results: Number={number_match} | Name={name_match}")
        
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
