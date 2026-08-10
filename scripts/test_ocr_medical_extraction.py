import sys
import os
from unittest.mock import MagicMock

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ai_features.services.ocr_service import OCRService

def test_ocr_extraction():
    ocr = OCRService()
    
    print("[START] Starting Medical OCR Unit Tests...")

    # Case 1: Standard printed bill (All fields present)
    clean_bill_text = """
    APOLLO MULTISPECIALITY HOSPITAL
    STREET 12, NEW DELHI
    INV # 4521 | DATE: 12/04/2026
    
    PATIENT NAME
    RAVI KUMAR
    
    DESCRIPTION             AMOUNT
    ------------------------------
    General Ward Room Rent  18,000.00
    Knee Surgery Charges    85,000.00
    Lab Diagnostics         4,500.00
    ------------------------------
    TOTAL DUE               107,500.00
    """
    
    res1 = ocr.extract_claim_details(clean_bill_text)
    with open("FINAL_TEST_DEBUG.txt", "w") as f:
        f.write(f"TEST 1: {res1}\n")
    
    print("\n[TEST 1] Clean Bill Extraction:")
    for k,v in res1.items():
        print(f"  - {k}: {v}")
    
    # Precise Assertions with Error Messaging
    checks = [
        ('hospital_name', "APOLLO MULTISPECIALITY HOSPITAL"),
        ('patient_name', "RAVI KUMAR"),
        ('room_charges', 18000.0),
        ('surgery_cost', 85000.0),
        ('diagnostics_cost', 4500.0),
        ('total_amount', 107500.0),
        ('confidence', 'HIGH'),
        ('review_flag', False)
    ]
    
    for field, expected in checks:
        val = res1.get(field)
        if val != expected:
            print(f"[FAIL] {field} mismatch. Expected '{expected}' ({type(expected)}), got '{val}' ({type(val)})")
            assert val == expected
    print("[OK] Test 1 Passed!")

    # Case 2: Partial Bill (Missing Surgery)
    partial_bill = """
    MIOT INTERNATIONAL HOSPITAL
    PATIENT: SNEHA SHARMA
    
    WARD CHARGES            12000
    BLOOD TEST              1500
    
    TOTAL                   13500
    """
    res2 = ocr.extract_claim_details(partial_bill)
    print("\n[TEST 2] Partial Bill Extraction:")
    print(res2)
    assert res2['hospital_name'] == "MIOT INTERNATIONAL HOSPITAL"
    assert res2['room_charges'] == 12000.0
    assert res2['surgery_cost'] == 0.0
    assert res2['total_amount'] == 13500.0
    print("[OK] Test 2 Passed!")

    # Case 3: Integrity Failure (Sum != Total)
    fraud_bill = """
    FORTIS HEALTHCARE
    PATIENT: RAKESH SINGH
    
    ROOM                    10000
    SURGERY                 50000
    LAB                     5000
    
    TOTAL                   45000
    """
    res3 = ocr.extract_claim_details(fraud_bill)
    print("\n[TEST 3] Integrity Failure Check:")
    print(res3)
    # Sum is 65000 vs reported Total 45000
    assert res3['review_flag'] == True
    print("[OK] Test 3 Passed! Audit alarm triggered correctly.")

    print("\n[PASSED] ALL OCR EXTRACTION TESTS PASSED!")

if __name__ == "__main__":
    test_ocr_extraction()
