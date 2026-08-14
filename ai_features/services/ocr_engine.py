import logging
import os
import tempfile
import numpy as np
from PIL import Image as PILImage, ImageOps, ImageEnhance
from django.core.files.uploadedfile import UploadedFile

import threading

# Global thread-safe singleton for PaddleOCR
_ocr_lock = threading.Lock()
_ocr_reader = None

def get_ocr():
    """
    Lazy loader for PaddleOCR.
    Only initializes the engine when first called.
    """
    global _ocr_reader
    
    # 🛡️ Requirement 7: Environment Protection
    import os
    os.environ['PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK'] = 'True'
    
    with _ocr_lock:
        if _ocr_reader is None:
            try:
                # 🚀 Requirement 8: Initialization Logging
                print("\n[AI-OCR] Initializing PaddleOCR Engine for the first time...")
                from paddleocr import PaddleOCR
                _ocr_reader = PaddleOCR(
                    use_angle_cls=True,
                    lang='en'
                )
                print("[AI-OCR] Engine Loaded Successfully (PaddleOCR)")
            except ImportError:
                print("[AI-OCR] PaddleOCR not installed. Using fallback.")
            except Exception as e:
                print(f"[AI-OCR] Failed to initialize PaddleOCR: {e}")
    return _ocr_reader

logger = logging.getLogger(__name__)

class OCREngine:
    """
    Production-grade OCR Adapter using PaddleOCR with Pytesseract fallback.
    Implements Image Preprocessing and Retry Strategy.
    """
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(OCREngine, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if not self._initialized:
            # We no longer load the reader here. 
            # It will be lazy-loaded in the extraction methods.
            self._initialized = True

    def preprocess_image(self, image_input):
        """
        Refined Preprocessing (Requirement 2): Avoid overprocessing text.
        """
        try:
            if isinstance(image_input, str):
                img = PILImage.open(image_input)
            else:
                img = image_input.copy()

            # Ensure RGB for consistent processing
            if img.mode != 'RGB':
                img = img.convert('RGB')

            # Mild sharpening only
            enhancer = ImageEnhance.Sharpness(img)
            img = enhancer.enhance(1.2) # Reduced from 2.0 to avoid artifacts
            
            # Autocontrast is usually safe
            img = ImageOps.autocontrast(img)
            
            # Resize if significantly small (Requirement 2)
            w, h = img.size
            if w < 1200:
                scale = 1200 / w
                img = img.resize((1200, int(h * scale)), PILImage.Resampling.LANCZOS)
            
            return img
        except Exception as e:
            logger.error(f"Image preprocessing failed: {e}")
            return image_input

    def extract_text(self, image_path):
        """
        Primary extraction with Retry Strategy and Mandatory Logging (Requirement 3 & 6).
        """
        # Pass 1: Original
        result_data = self.extract_lines_with_confidence(image_path)
        
        # Pass 2: Preprocessed if results are weak (Requirement 6)
        if not result_data or len("".join([r['text'] for r in result_data])) < 20:
            print("OCR ENGINE: Initial pass weak, retrying with normalized/preprocessed image...")
            pre_img = self.preprocess_image(image_path)
            
            temp_pre = None
            try:
                tf = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
                pre_img.save(tf.name, "PNG")
                tf.close()
                temp_pre = tf.name
                
                pass2_data = self.extract_lines_with_confidence(temp_pre)
                
                # Compare lengths to choose best pass
                len1 = len("".join([r['text'] for r in result_data]))
                len2 = len("".join([r['text'] for r in pass2_data]))
                
                if len2 > len1:
                    result_data = pass2_data
                    print(f"OCR ENGINE: Pass 2 selected (Better coverage: {len2} chars)")
            finally:
                if temp_pre and os.path.exists(temp_pre):
                    try: os.remove(temp_pre)
                    except: pass

        lines = [r['text'] for r in result_data]
        text = "\n".join(lines).strip()
        
        # MANDATORY LOGGING (Requirement 3)
        print("-" * 30)
        print("RAW OCR OUTPUT:")
        print(f"TEXT LENGTH: {len(text)}")
        print(f"LINES COUNT: {len(lines)}")
        if text:
            print(f"SAMPLE TEXT: {text[:200]}...")
        else:
            print("!!! WARNING: OCR RETURNED NO TEXT !!!")
        print("-" * 30)
            
        return text

    def extract_lines_with_confidence(self, image_path):
        """Helper for extraction with confidence tracking."""
        reader = get_ocr()
        if not reader:
            return []
        try:
            # Re-verify path exists
            if not os.path.exists(image_path):
                logger.error(f"OCR path does not exist: {image_path}")
                return []
                
            result = reader.ocr(image_path)
            if not result or not result[0]:
                return []
            
            extracted = []
            for line in result[0]:
                text = line[1][0]
                conf = float(line[1][1])
                extracted.append({"text": text, "confidence": conf})
            return extracted
        except Exception as e:
            logger.error(f"PaddleOCR line extraction failed: {e}")
            return []

    def get_confidence_summary(self, result_data):
        """Requirement 7: Return avg confidence score."""
        if not result_data:
            return 0.0
        confs = [r['confidence'] for r in result_data if 'confidence' in r]
        return sum(confs) / len(confs) if confs else 0.0

    def extract_with_boxes(self, image_path):
        """Detailed extraction with spatial data."""
        reader = get_ocr()
        if not reader:
            return []
        try:
            result = reader.ocr(image_path)
            if not result or not result[0]:
                return []
            
            extracted = []
            for line in result[0]:
                extracted.append({
                    "text": line[1][0],
                    "confidence": float(line[1][1]),
                    "box": line[0],
                    "low_quality": line[1][1] < 0.50 # Reduced threshold from 0.60
                })
            return extracted
        except Exception as e:
            logger.error(f"PaddleOCR box extraction failed: {e}")
            return []

def extract_text_compat(image):
    """
    Backward Compatibility Wrapper (Requirement 1 & 5).
    Converts any input to a safe PNG for OCR.
    """
    engine = OCREngine()
    temp_path = None
    text = ""

    try:
        # Determine path or handle upload object (Requirement 1)
        if isinstance(image, str):
            path = image
        elif isinstance(image, UploadedFile):
            # Safe conversion to disk
            tf = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
            try:
                img_obj = PILImage.open(image)
                if img_obj.mode != 'RGB':
                    img_obj = img_obj.convert('RGB')
                img_obj.save(tf.name, "PNG")
                tf.close()
                temp_path = tf.name
                path = temp_path
            except Exception as e:
                logger.error(f"Uploaded image conversion failed: {e}")
                # Simple write fallback
                image.seek(0)
                tf.write(image.read())
                tf.close()
                temp_path = tf.name
                path = temp_path
        elif isinstance(image, PILImage.Image):
            tf = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
            image.save(tf.name, "PNG")
            tf.close()
            temp_path = tf.name
            path = temp_path
        else:
            # Fallback pathing
            path = getattr(image, 'path', None)
            if not path:
                tf = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
                tf.write(image if isinstance(image, bytes) else str(image).encode())
                tf.close()
                temp_path = tf.name
                path = temp_path

        # PDF Handling
        if path.lower().endswith('.pdf'):
            pdf_img_path = None
            try:
                from pdf2image import convert_from_path
                pages = convert_from_path(path, first_page=1, last_page=1)
                if pages:
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as pdf_tf:
                        pages[0].save(pdf_tf.name, 'PNG')
                        pdf_img_path = pdf_tf.name
                    text = engine.extract_text(pdf_img_path)
            except Exception as e:
                logger.error(f"PDF handling failed: {e}")
            finally:
                if pdf_img_path and os.path.exists(pdf_img_path):
                    try: os.remove(pdf_img_path)
                    except: pass

        # Main OCR Pass
        if not text:
            text = engine.extract_text(path)

        # Tesseract Fallback
        if not text:
            try:
                import pytesseract
                TESSERACT_CMD = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
                if os.path.exists(TESSERACT_CMD):
                    pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD
                text = pytesseract.image_to_string(path, config="--oem 3 --psm 6")
                if text:
                    print("✅ [AI-OCR] Fallback: Tesseract extracted text successfully.")
            except Exception as e:
                logger.error(f"OCR Fallback failed: {e}")

        return text

    finally:
        # Cleanup
        if temp_path and os.path.exists(temp_path):
            try: os.remove(temp_path)
            except: pass
