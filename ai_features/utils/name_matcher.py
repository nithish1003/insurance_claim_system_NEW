import re
import logging
from typing import Dict, Any

try:
    from rapidfuzz import fuzz
except ImportError:
    # Fallback if rapidfuzz is not installed (though we will install it)
    from difflib import SequenceMatcher
    class fuzz:
        @staticmethod
        def token_sort_ratio(s1, s2):
            return SequenceMatcher(None, s1, s2).ratio() * 100

logger = logging.getLogger(__name__)

def normalize_name(name: str) -> str:
    """
    Strict normalization for identity verification:
    1. Convert to uppercase
    2. Strip ALL non-alphabetic characters (including spaces/symbols)
    """
    if not name:
        return ""
    
    # Step 1: Uppercase
    name = str(name).upper()
    
    # Step 2: Remove everything except A-Z (removes spaces, symbols, and dots)
    name = re.sub(r'[^A-Z]', '', name)
    
    return name.strip()

def calculate_similarity(name1: str, name2: str) -> float:
    """
    Compare two names using RapidFuzz and return a similarity score (0-100).
    Now uses strict normalization (no spaces) for direct comparison.
    """
    norm1 = normalize_name(name1)
    norm2 = normalize_name(name2)
    
    if not norm1 or not norm2:
        return 0.0
    
    # token_sort_ratio is overkill if we remove spaces, but still robust
    return fuzz.ratio(norm1, norm2)

def validate_name_match(ocr_name: str, user_input: str, threshold: float = 88.0) -> Dict[str, Any]:
    """
    Finalized name validation: 
    Strict equality + length safety + similarity fallback.
    """
    # 🔥 Step 3: MANDATORY PRODUCTION LOGS
    print(f"RAW INPUT: {user_input}")
    print(f"RAW OCR: {ocr_name}")
    
    user_clean = normalize_name(user_input)
    ocr_clean = normalize_name(ocr_name)
    
    print(f"USER CLEAN: {user_clean}")
    print(f"OCR CLEAN: {ocr_clean}")
    print(f"LENGTH: USER={len(user_clean)}, OCR={len(ocr_clean)}")

    # Step 1 & 4 & 6: Compare metrics before safety check for full log visibility
    from difflib import SequenceMatcher
    similarity = SequenceMatcher(None, user_clean, ocr_clean).ratio()
    print(f"SIMILARITY: {round(similarity, 4)}")
    
    # Step 5: Length Safety Check (Preventing fragments/empty extractions)
    if len(user_clean) < 5 or len(ocr_clean) < 5:
        logger.warning(f"Safety Failure: Name length too short. User={len(user_clean)}, OCR={len(ocr_clean)}")
        return {
            "is_match": False,
            "error": "Invalid name extraction: Name is too short or unclear.",
            "is_length_failure": True
        }

    # Exact Match (Zero-Space)
    is_exact_match = (user_clean == ocr_clean)
    
    # Fallback Similarity (e.g., 0.88)
    is_sim_match = (similarity >= (threshold / 100.0))
    
    final_match = is_exact_match or is_sim_match
    
    result = {
        "is_match": final_match,
        "is_exact_match": is_exact_match,
        "similarity": round(similarity, 4),
        "threshold": threshold / 100.0,
        "normalized_ocr": ocr_clean,
        "normalized_user": user_clean,
        "algorithm": "Strict Stripped Equality + SequenceMatcher"
    }
    
    logger.info(f"Final Identity Audit: Match={final_match} | Exact={is_exact_match} | Score={round(similarity, 2)}")
    
    return result
