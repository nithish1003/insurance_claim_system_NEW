import os
import sys

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ai_features.services.ocr_engine import OCREngine, extract_text_compat
from PIL import Image, ImageDraw

def test_ocr_engine():
    print("OCR SYSTEM DIAGNOSTICS")
    print("-" * 30)
    
    try:
        engine = OCREngine()
        print(f"Engine Instance Created: {engine is not None}")
        
        from ai_features.services.ocr_engine import get_ocr
        reader = get_ocr()
        print(f"Lazy Reader Loaded: {reader is not None}")
        
        # Create a test image with text
        img = Image.new('RGB', (200, 60), color = (255, 255, 255))
        d = ImageDraw.Draw(img)
        d.text((20,20), "PADDLE OCR TEST", fill=(0,0,0))
        
        temp_img = "test_ocr_debug.png"
        img.save(temp_img)
        
        print("\nTesting extract_text...")
        text = engine.extract_text(temp_img)
        print(f"Extracted: '{text}'")
        
        print("\nTesting extract_with_boxes...")
        boxes = engine.extract_with_boxes(temp_img)
        for b in boxes:
            print(f" - Text: {b['text']} (Conf: {b['confidence']:.2f})")
        
        print("\nTesting extract_text_compat...")
        compat_text = extract_text_compat(img)
        print(f"Compat Extracted: '{compat_text}'")
        
        if os.path.exists(temp_img):
            os.remove(temp_img)
            
        print("\nDIAGNOSTIC COMPLETE.")
        
    except Exception as e:
        print(f"ERROR: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_ocr_engine()
