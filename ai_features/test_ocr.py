import os
import sys
import django

# Add current directory to path
sys.path.append(os.getcwd())

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'insurance_claim_system.settings')
django.setup()

from claims.models import Claim, ClaimDocument
from ai_features.services.ocr_service import perform_ocr, extract_details
import re
from decimal import Decimal

def log(msg):
    print(msg)
    sys.stdout.flush()

log("\n[OCR ENHANCEMENT TEST]\n")

# Find the specific medical receipt
doc = ClaimDocument.objects.filter(file__icontains='BqgYoVB.53.10_AM').first()

if not doc:
    log("Error: Could not find medical receipt")
    exit()

claim = doc.claim
log(f"Processing Claim: {claim.claim_number}")

file_path = doc.file.path
log(f"File: {file_path}")

# 1. OCR text extraction
log("Performing OCR...")
text = perform_ocr(file_path)
log(f"Extracted Length: {len(text)}")
# log(f"Raw Text Preview:\n{text[:300]}")

# 2. Enhanced Extraction Logic (Centralized in OCRService)
log("Running Enhanced Extraction Pipeline...")
extracted = extract_details(text)

patient_name = extracted.get('patient_name')
total_amount = extracted.get('total_amount', 0.0)

log("\n=== AI EXTRACTION RESULT ===")
log(f"PATIENT NAME: {patient_name}")
log(f"TOTAL AMOUNT: {total_amount}")
log("============================\n")

# 3. Verification vs Database
claimed_amount = getattr(claim, 'claim_amount', 0.0) or getattr(claim, 'claimed_amount', 0.0)
if float(total_amount) == float(claimed_amount):
    log("✅ Financial Audit Passed (Matching Amounts)")
else:
    log(f"⚠️ Financial Audit Alert: OCR({total_amount}) != DB({claimed_amount})")

print("\n[TEST COMPLETED]\n")