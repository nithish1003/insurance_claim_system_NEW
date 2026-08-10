import sys
import os
from unittest.mock import MagicMock
from decimal import Decimal
from datetime import date, timedelta

# Standard Django Setup
import django
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'insurance_claim_system.settings')
django.setup()

from ai_features.services.claim_ai_service import ClaimAIService

def test_multi_domain_triage():
    print("[START] Starting Intelligent Triage Advanced Unit Tests...")

    def create_mock_claim(claim_type, admission_type='routine', fraud_in_ocr=False, early_claim=False):
        claim = MagicMock()
        claim.claim_type = claim_type
        claim.admission_type = admission_type
        claim.claimed_amount = Decimal('100000.00')
        claim.deductible_amount = Decimal('5000.00')
        claim.hospital_risk_score = 0.1
        claim.created_by.profile.claim_frequency = 1
        
        # Mocking OCR response via textual injection
        claim.ocr_text = "Standard dossier"
        if fraud_in_ocr:
            claim.ocr_text = "DEATH CERTIFICATE\nCAUSE: SUICIDE"
        
        # Policy Setup
        mock_policy = MagicMock()
        mock_policy.sum_insured = Decimal('500000.00')
        
        mock_up = MagicMock()
        mock_up.policy = mock_policy
        mock_up.nominee_name = "NOMINEE"
        mock_up.user.get_full_name.return_value = "OWNER"
        
        if early_claim:
             mock_up.start_date = date.today() - timedelta(days=100) # Early
        else:
             mock_up.start_date = date.today() - timedelta(days=1000) # Mature
             
        claim.user_policy = mock_up
        return claim

    # SCENARIO 1: Standard Medical (Routine)
    c1 = create_mock_claim('medical', 'routine')
    res1 = ClaimAIService.get_full_decision(c1)
    print(f"\n[TEST 1] Medical Routine Case: Priority={res1['governance']['priority']}")
    assert res1['governance']['priority'] == 'medium'

    # SCENARIO 2: Emergency Hospitalization
    c2 = create_mock_claim('medical', 'emergency')
    res2 = ClaimAIService.get_full_decision(c2)
    print(f"\n[TEST 2] Emergency Hospital Case: Priority={res2['governance']['priority']}")
    assert res2['governance']['priority'] == 'high'
    assert "Emergency" in res2['governance']['priority_reason']

    # SCENARIO 3: Motor Fraud (Identity Mismatch simulated via flag)
    # Note: In real logic, OCR detection of fraud triggers Critical.
    # We'll simulate a Fraud Override.
    c3 = create_mock_claim('motor')
    # Force high risk to trigger fraud logic
    c3.hospital_risk_score = 0.95 
    res3 = ClaimAIService.get_full_decision(c3)
    print(f"\n[TEST 3] High Risk Fraud Case: Priority={res3['governance']['priority']}")
    assert res3['governance']['priority'] == 'critical'
    assert res3['governance']['fraud_flag'] == True

    # SCENARIO 4: Life Contestability (Early Claim)
    c4 = create_mock_claim('death', early_claim=True)
    res4 = ClaimAIService.get_full_decision(c4)
    print(f"\n[TEST 4] Early Life Claim: Priority={res4['governance']['priority']}")
    assert res4['governance']['priority'] == 'critical'
    assert "Early Claim" in res4['governance']['priority_reason']

    # SCENARIO 5: Critical Illness
    c5 = create_mock_claim('critical_illness')
    res5 = ClaimAIService.get_full_decision(c5)
    print(f"\n[TEST 5] Critical Illness: Priority={res5['governance']['priority']}")
    assert res5['governance']['priority'] == 'high'

    print("\n[PASSED] ALL MULTI-DOMAIN TRIAGE TESTS PASSED!")

if __name__ == "__main__":
    test_multi_domain_triage()
