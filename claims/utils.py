import re
from difflib import SequenceMatcher

def normalize_vehicle_number(num):
    """
    Normalizes vehicle number by:
    - Removing hyphens and spaces
    - Converting to uppercase
    - Trimming extra spaces
    - Swapping common OCR mistakes (B/8, O/0) for comparison stability
    """
    if not num:
        return ""
    
    # Basic normalization: Remove non-alphanumeric and uppercase
    num = re.sub(r'[^A-Z0-9]', '', str(num).upper())
    return num.strip()

def compare_vehicle_numbers(num1, num2):
    """
    Compares two vehicle numbers with high tolerance for OCR and formatting errors.
    Returns (match_found, similarity_score, normalized1, normalized2)
    """
    norm1 = normalize_vehicle_number(num1)
    norm2 = normalize_vehicle_number(num2)
    
    # 1. Exact match after basic normalization
    if norm1 == norm2:
        return True, 1.0, norm1, norm2
    
    # 2. OCR Character Swap normalization
    # Map common OCR confusion characters to a unified version
    def ocr_unify(n):
        return n.replace('8', 'B').replace('0', 'O').replace('I', '1').replace('L', '1')
    
    if ocr_unify(norm1) == ocr_unify(norm2):
        return True, 0.95, norm1, norm2
        
    # 3. Fuzzy matching using SequenceMatcher
    similarity = SequenceMatcher(None, norm1, norm2).ratio()
    
    if similarity >= 0.9:
        return True, similarity, norm1, norm2
        
    return False, similarity, norm1, norm2
