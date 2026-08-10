import os
import sys
import django
from PIL import Image, ImageFilter, ImageDraw, ImageFont

# Setup Django settings
sys.path.append(os.getcwd())
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'insurance_claim_system.settings')
django.setup()

from claims.services.ocr_service import RCOCRService

def create_wrong_rc(output_path):
    print(f"Creating wrong RC image at {output_path}...")
    # Create a simple white image
    img = Image.new('RGB', (800, 400), color='white')
    draw = ImageDraw.Draw(img)
    # Write some mock text containing a wrong vehicle number
    text = "STATE ROAD TRANSPORT AUTHORITY\nREGISTRATION CERTIFICATE\nVEHICLE NUMBER: MH-12-XY-9999\nOWNER: JOHN DOE\nMODEL: MARUTI SWIFT"
    # Draw text using default font since system font path varies
    draw.text((50, 50), text, fill='black')
    img.save(output_path)

def create_blurred_rc(input_path, output_path):
    print(f"Creating blurred RC image at {output_path}...")
    img = Image.open(input_path)
    # Apply heavy blur to degrade OCR readability
    blurred = img.filter(ImageFilter.GaussianBlur(10))
    blurred.save(output_path)

def create_rotated_rc(input_path, output_path):
    print(f"Creating rotated RC image at {output_path}...")
    img = Image.open(input_path)
    # Rotate by 90 degrees which breaks typical horizontal line OCR
    rotated = img.rotate(90, expand=True)
    rotated.save(output_path)

def main():
    service = RCOCRService()
    valid_rc = "media/application_rc/Gemini_Generated_Image_ingshmingshmings.png"
    
    # Define paths
    wrong_rc = "scratch/wrong_rc.png"
    blurred_rc = "scratch/blurred_rc.png"
    rotated_rc = "scratch/rotated_rc.png"
    
    # Generate test images
    create_wrong_rc(wrong_rc)
    create_blurred_rc(valid_rc, blurred_rc)
    create_rotated_rc(valid_rc, rotated_rc)
    
    print("\n" + "="*50)
    print("RUNNING VEHICLE VALIDATION TESTS ON VARIOUS IMAGE TYPES")
    print("="*50)
    
    # 1. Test Valid RC with Correct Vehicle Number
    print("\n--- 1. Testing VALID RC Image with CORRECT vehicle number (TN-10-AB-1234) ---")
    res1 = service.validate_rc(valid_rc, "TN-10-AB-1234")
    print(f"Result (Expected True): {res1}")
    
    # 2. Test Wrong RC with Vehicle Number
    print("\n--- 2. Testing WRONG RC Image with vehicle number (TN-10-AB-1234) ---")
    res2 = service.validate_rc(wrong_rc, "TN-10-AB-1234")
    print(f"Result (Expected False): {res2}")
    
    # 3. Test Blurred RC with Vehicle Number
    print("\n--- 3. Testing BLURRED RC Image with vehicle number (TN-10-AB-1234) ---")
    res3 = service.validate_rc(blurred_rc, "TN-10-AB-1234")
    print(f"Result (Expected False due to readability/OCR fail): {res3}")
    
    # 4. Test Rotated RC with Vehicle Number
    print("\n--- 4. Testing ROTATED RC Image with vehicle number (TN-10-AB-1234) ---")
    res4 = service.validate_rc(rotated_rc, "TN-10-AB-1234")
    print(f"Result (Expected False due to orientation/OCR fail): {res4}")
    
    # Cleanup generated files
    for path in [wrong_rc, blurred_rc, rotated_rc]:
        if os.path.exists(path):
            os.remove(path)
            print(f"Cleaned up test file: {path}")

if __name__ == "__main__":
    main()
