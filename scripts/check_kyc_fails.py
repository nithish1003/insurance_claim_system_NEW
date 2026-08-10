import os
import django
import json

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'insurance_claim_system.settings')
django.setup()

from accounts.models import AadhaarKYCVerification

latest_fails = AadhaarKYCVerification.objects.filter(status='failed').order_by('-created_at')[:5]

for kyc in latest_fails:
    print(f"ID: {kyc.id}")
    print(f"Submitted Name: {kyc.submitted_full_name}")
    print(f"Extracted Name: {kyc.extracted_name}")
    print(f"OCR Text Sample: {kyc.details.get('error', 'N/A')}")
    # If the details have the full OCR text, it would be helpful.
    # verify_aadhaar doesn't seem to store the full OCR text in details yet.
    print(f"Details: {json.dumps(kyc.details, indent=2)}")
    print("-" * 40)
