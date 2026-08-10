import os
import sys
import django

# Setup Django settings
sys.path.append(os.getcwd())
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'insurance_claim_system.settings')
django.setup()

from claims.services.ocr_service import RCOCRService

def main():
    service = RCOCRService()
    rc_image_path = r"media/application_rc/Gemini_Generated_Image_ingshmingshmings.png"
    
    if not os.path.exists(rc_image_path):
        print(f"File not found: {rc_image_path}")
        return

    print("Running OCR on RC image...")
    text = service.extract_text_from_rc(rc_image_path)
    print("\n--- OCR TEXT ---")
    print(text)
    print("----------------\n")
    
    extracted_num = service.extract_vehicle_number(text)
    print(f"Extracted Vehicle Number: {extracted_num}")
    
    # Try validation with correct, incorrect numbers
    test_numbers = ["TN-10-AB-1234", "TN 10 AB 1234", "TN 09 BX 4587", "TN09BX4587", "MH12AB1234"]
    for num in test_numbers:
        is_valid = service.validate_rc(rc_image_path, num)
        print(f"Validation for '{num}': {is_valid}")

if __name__ == '__main__':
    main()
