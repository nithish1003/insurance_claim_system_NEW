import os
import sys
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'insurance_claim_system.settings')
django.setup()

try:
    from ai_features.services.ocr_engine import OCREngine
    print("\n--- OCR ENGINE INITIALIZATION TEST ---")
    engine = OCREngine()
    print(f"Engine Instance: {engine}")
    if engine.reader:
        print("✅ SUCCESS: PaddleOCR reader initialized successfully.")
    else:
        print("⚠️ WARNING: PaddleOCR reader is None. Fallback will be used.")
except Exception as e:
    print(f"❌ ERROR: Failed to initialize OCR Engine: {e}")
    import traceback
    traceback.print_exc()
