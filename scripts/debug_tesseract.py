import os
import pytesseract
from PIL import Image

TESSERACT_CMD = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD

def test_tesseract():
    try:
        print(f"Tesseract Path: {TESSERACT_CMD}")
        print(f"Exists: {os.path.exists(TESSERACT_CMD)}")
        
        # Test with a blank image found in the system or create one
        img = Image.new('RGB', (100, 30), color = (255, 255, 255))
        from PIL import ImageDraw, ImageFont
        d = ImageDraw.Draw(img)
        d.text((10,10), "TEST", fill=(0,0,0))
        
        text = pytesseract.image_to_string(img).strip()
        print(f"Extracted Text: '{text}'")
        
        if "TEST" in text.upper():
            print("SUCCESS: Tesseract is functional.")
        else:
            print("FAILURE: Tesseract did not extract 'TEST'.")
            
    except Exception as e:
        print(f"ERROR: {str(e)}")

if __name__ == "__main__":
    test_tesseract()
