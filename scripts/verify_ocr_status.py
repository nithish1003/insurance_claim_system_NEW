import os
import sys
import django

# Setup Django environment
sys.path.append(os.getcwd())
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'insurance_claim_system.settings')
django.setup()

from ai_features.services.ocr_service import OCRService

def run_diagnostic():
    print("=== OCR SYSTEM OPERATIONAL CHECK ===")
    service = OCRService()
    
    # Test details for Rahul Verma
    # Note: We don't have the absolute path to the user's uploaded file here,
    # but we can check if the service methods are callable and consistent.
    
    print(f"Service Class Loaded: {service.__class__.__name__}")
    
    # Mock text to verify extraction logic
    mock_text = """
    DIGITAL INDIA AUTHORITY
    GOVERNMENT OF INDIA
    NAME: RAHUL VERMA
    Aadhaar: 6234 5567 8890
    """
    
    print("\n--- Testing Name Extraction ---")
    ext_name = service._extract_aadhaar_name(mock_text, "Rahul Verma")
    print(f"Expected: Rahul Verma | Extracted: {ext_name}")
    
    print("\n--- Testing Number Extraction ---")
    ext_nums = service._extract_aadhaar_numbers(mock_text)
    print(f"Expected: ['623455678890'] | Extracted: {ext_nums}")
    
    # Functional Check
    is_working = (ext_name == "RAHUL VERMA" and "623455678890" in ext_nums)
    
    if is_working:
        print("\n✅ OCR LOGIC IS FULLY FUNCTIONAL")
    else:
        print("\n❌ OCR LOGIC HAS DISCREPANCIES")

if __name__ == "__main__":
    run_diagnostic()
