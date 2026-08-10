import sys
import os
from unittest.mock import MagicMock
from decimal import Decimal
from datetime import date, timedelta

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'insurance_claim_system.settings')
django.setup()

from ai_features.services.ocr_service import OCRService
from ai_features.services.claim_ai_service import ClaimAIService

def test_life_ocr_extraction():
    ocr = OCRService()
    
    print("[START] Starting Life Claim OCR Unit Tests...")

    # Case 1: Standard Death Certificate
    life_cert = """
    GOVERNMENT OF TAMIL NADU
    REGISTRAR OF BIRTHS AND DEATHS
    DEATH CERTIFICATE
    
    NAME OF DECEASED: RAJESH KHANNA
    DATE OF DEATH: 12/04/2026
    AGE: 58 YEARS
    
    CAUSE OF DEATH: NATURAL CAUSES (CARDIAC ARREST)
    INFORMANT: SNEHA KHANNA (WIFE)
    """
    
    res1 = ocr.extract_claim_details(life_cert)
    with open("LIFE_TEST_DEBUG.txt", "w") as f:
        f.write(f"TEST 1: {res1}\n")
    
    print("\n[TEST 1] Death Certificate Extraction:")
    for k,v in res1.items():
        if v: print(f"  - {k}: {v}")
    
    assert res1['deceased_name'] == "RAJESH KHANNA"
    assert res1['date_of_death'] == "12/04/2026"
    assert res1['nominee_name'] == "SNEHA KHANNA"
    print("[OK] Test 1 Passed!")

    # Case 2: Exclusion Case (Suicide)
    exclusion_cert = """
    DEATH CERTIFICATE
    NAME: VIKRAM SINGH
    CAUSE OF DEATH: ASPECT OF SELF-INFLICTED INJURY (SUICIDE)
    """
    res2 = ocr.extract_claim_details(exclusion_cert)
    print("\n[TEST 2] Exclusion Detection:")
    print(f"  - Fraud Flag: {res2['fraud_flag']}")
    assert res2['fraud_flag'] == True
    assert "exclusion" in res2['log'][0].lower()
    print("[OK] Test 2 Passed!")

    # Case 3: Integrated AI Decision (Mocked)
    print("\n[TEST 3] Fixed Benefit AI Decision Mock:")
    
    # Mocking a Claim object
    mock_claim = MagicMock()
    mock_claim.claim_type = 'death'
    mock_claim.claimed_amount = 0 # Not used for death
    mock_claim.deductible_amount = 0
    mock_claim.ocr_text = life_cert
    
    # Mocking UserPolicy and Policy
    mock_policy = MagicMock()
    mock_policy.sum_insured = Decimal('1000000.00') # 10 Lakhs
    
    mock_up = MagicMock()
    mock_up.policy = mock_policy
    mock_up.nominee_name = "SNEHA KHANNA"
    mock_up.user.get_full_name.return_value = "RAJESH KHANNA"
    mock_up.start_date = date.today() - timedelta(days=1000) # > 2 years
    
    mock_claim.user_policy = mock_up
    
    # Execute AI decision
    decision = ClaimAIService.get_full_decision(mock_claim)
    print(f"  - Recommended Payout: {decision['financial_trace'][2]['result']}")
    print(f"  - Fraud Flag: {decision['governance']['fraud_flag']}")
    
    assert decision['financial_trace'][2]['result'] == 1050000.0 # 10L + 50k bonus
    assert decision['governance']['fraud_flag'] == False
    print("[OK] Test 3 Passed!")

    print("\n[PASSED] ALL LIFE OCR & AI TESTS PASSED!")

if __name__ == "__main__":
    test_life_ocr_extraction()
