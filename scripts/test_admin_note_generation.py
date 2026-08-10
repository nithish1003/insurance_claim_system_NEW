import sys
import os
from unittest.mock import MagicMock

# Standard Django Setup
import django
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'insurance_claim_system.settings')
django.setup()

from ai_features.services.admin_note_service import admin_note_engine

def test_note_generation():
    print("[START] Starting Deterministic AI Admin Note Unit Tests (3-Step Pipeline)...")

    # Scenario 1: Fraud (Should override everything)
    data1 = {
        "verification_status": "PASSED",
        "document_status": "VERIFIED",
        "risk_score": 0.05,
        "fraud_flag": "IDENTITY_MISMATCH"
    }
    note1 = admin_note_engine.generate(data1)
    print(f"\n[TEST 1] Fraud Conflict Scenario:\n  - Input: Fraud Present, Low Risk\n  - Note: {note1}")
    assert "investigation" in note1.lower()
    assert "identity_mismatch" in note1.lower()

    # Scenario 2: Invalid Documents (Should trigger Rejection)
    data2 = {
        "verification_status": "PASSED",
        "document_status": "INVALID",
        "risk_score": 0.2,
        "fraud_flag": None
    }
    note2 = admin_note_engine.generate(data2)
    print(f"\n[TEST 2] Invalid Document Scenario:\n  - Input: Invalid Docs\n  - Note: {note2}")
    assert "rejected" in note2.lower()
    assert "policy guidelines" in note2.lower()

    # Scenario 3: Passed & Low Risk (Perfect Dossier)
    data3 = {
        "verification_status": "PASSED",
        "document_status": "VERIFIED",
        "risk_score": 0.04,
        "fraud_flag": None
    }
    note3 = admin_note_engine.generate(data3)
    print(f"\n[TEST 3] Perfect Approval Scenario:\n  - Input: Passed, Clean, 0.04 Risk\n  - Note: {note3}")
    assert "successfully verified" in note3.lower()
    assert "standard terms" in note3.lower()

    # Scenario 4: Middle Ground (Moderate Risk)
    data4 = {
        "verification_status": "PASSED",
        "document_status": "VERIFIED",
        "risk_score": 0.35,
        "fraud_flag": None,
        "review_flag": "Standard audit threshold reached"
    }
    note4 = admin_note_engine.generate(data4)
    print(f"\n[TEST 4] Moderate Risk Scenario:\n  - Input: Moderate Risk (0.35)\n  - Note: {note4}")
    assert "on hold" in note4.lower()
    assert "additional verification" in note4.lower()

    print("\n[PASSED] ALL ADMIN NOTE GENERATION TESTS PASSED!")

if __name__ == "__main__":
    test_note_generation()
