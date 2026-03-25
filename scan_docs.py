import os
import sys
import django

# Add current directory to path
sys.path.append(os.getcwd())

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'insurance_claim_system.settings')
django.setup()

from claims.models import ClaimDocument
from ai_features.services.ocr_service import perform_ocr

print("\nSCANNING DOCUMENTS for MEDICAL RECEIPT\n")

for d in ClaimDocument.objects.all():
    try:
        text = perform_ocr(d.file.path).upper()
        if 'MEDICAL' in text or 'PATIENT' in text:
            print(f"ID: {d.id} | FILE: {d.file.name}")
            print(f"PREVIEW: {text[:200]}")
            print("-" * 50)
    except Exception as e:
        print(f"Error on {d.id}: {e}")

print("\nSCAN COMPLETED\n")
