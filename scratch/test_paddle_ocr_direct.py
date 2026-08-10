import os
os.environ['PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK'] = 'True'
from paddleocr import PaddleOCR

def main():
    print("Initializing PaddleOCR...")
    reader = PaddleOCR(use_angle_cls=True, lang='en')
    image_path = "media/application_rc/Gemini_Generated_Image_ingshmingshmings.png"
    
    print("\n1. Testing with cls=True:")
    try:
        res = reader.ocr(image_path, cls=True)
        print("Success!", len(res))
    except Exception as e:
        print("Failed:", e)
        
    print("\n2. Testing with cls=False:")
    try:
        res = reader.ocr(image_path, cls=False)
        print("Success!", len(res))
    except Exception as e:
        print("Failed:", e)

    print("\n3. Testing without cls parameter:")
    try:
        res = reader.ocr(image_path)
        print("Success!", len(res))
        if res and res[0]:
            for line in res[0]:
                print(line)
    except Exception as e:
        print("Failed:", e)

if __name__ == "__main__":
    main()
