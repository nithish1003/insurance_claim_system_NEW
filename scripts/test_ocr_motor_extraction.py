import sys
import os

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ai_features.services.ocr_service import OCRService

def test_motor_ocr_extraction():
    ocr = OCRService()
    
    print("[START] Starting Motor Claim OCR Unit Tests...")

    # Case 1: Standard repair bill (Parts + Labor)
    motor_bill_text = """
    GOEL AUTOMOBILES & SERVICE CENTER
    AUTHORISED MARUTI WORKSHOP
    DATE: 14/04/2026 | JOB CARD: 5542
    
    VEHICLE NO: TN 10 AB 1234
    OWNER: RAJESH KHANNA
    
    PART DESCRIPTION        AMOUNT
    ------------------------------
    FRONT BUMPER ASSEMBLY   4,500.00
    HEADLIGHT (RIGHT)       2,800.00
    SPARE WHEEL COVER       1,200.00
    ------------------------------
    LABOR: REPLACEMENT      1,500.00
    LABOR: BUMPER PAINTING  2,500.00
    ------------------------------
    GRAND TOTAL             12,500.00
    """
    
    res1 = ocr.extract_claim_details(motor_bill_text)
    with open("MOTOR_TEST_DEBUG.txt", "w") as f:
        f.write(f"TEST 1: {res1}\n")
    
    print("\n[TEST 1] Valid Motor Bill:")
    for k,v in res1.items():
        if v: print(f"  - {k}: {v}")
    
    expected_garage = "GOEL AUTOMOBILES & SERVICE CENTER"
    if res1['garage_name'] != expected_garage:
        print(f"[FAIL] Garage Name Error: Expected '{expected_garage}', got '{res1['garage_name']}'")
    
    assert res1['garage_name'] == "GOEL AUTOMOBILES & SERVICE CENTER"
    assert res1['vehicle_number'] == "TN10AB1234"
    assert res1['spare_parts_cost'] == 8500.0 # 4500 + 2800 + 1200
    assert res1['labor_cost'] == 4000.0 # 1500 + 2500
    assert res1['total_amount'] == 12500.0
    assert res1['review_flag'] == False
    print("[OK] Test 1 Passed!")

    # Case 2: Vehicle Number Mismatch (RC Extraction)
    rc_text = """
    GOVERNMENT OF INDIA
    REGISTRATION CERTIFICATE
    
    REGN NO: MH12XY9876
    CHASSIS: 4452147852
    MODEL: SWIFT VXI
    """
    res2 = ocr.extract_claim_details(rc_text)
    print("\n[TEST 2] RC Vehicle Extraction:")
    print(f"  - Extracted Number: {res2['vehicle_number']}")
    assert res2['vehicle_number'] == "MH12XY9876"
    print("[OK] Test 2 Passed!")

    # Case 3: Financial Mismatch (Arithmetic Error)
    fraud_bill = """
    SHREE MOTORS GARAGE
    VEHICLE: DL 3C AY 5541
    
    BUMPER SPARE            5000
    LABOR CHARGES           3000
    
    TOTAL DUE               15000
    """
    res3 = ocr.extract_claim_details(fraud_bill)
    print("\n[TEST 3] Financial Integrity Check:")
    # Sum is 8000 vs reported Total 15000
    print(f"  - Review Flag: {res3['review_flag']}")
    assert res3['review_flag'] == True
    print("[OK] Test 3 Passed! Audit alarm triggered correctly.")

    print("\n[PASSED] ALL MOTOR OCR EXTRACTION TESTS PASSED!")

if __name__ == "__main__":
    test_motor_ocr_extraction()
