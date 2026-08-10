import os
import sys
import django

sys.path.append(os.getcwd())
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'insurance_claim_system.settings')
django.setup()

from accounts.models import AadhaarKYCVerification
from django.utils import timezone
from django.db.models import Count

today = timezone.now().date()
print(f"Current Date: {today}")
print("-" * 30)

all_kyc = AadhaarKYCVerification.objects.all()
print(f"Total KYC Records: {all_kyc.count()}")

today_kyc = all_kyc.filter(created_at__date=today)
print(f"\nRecords Created Today ({today_kyc.count()}):")
for kyc in today_kyc.order_by('-created_at'):
    print(f"  ID: {kyc.public_id} | Name: {kyc.submitted_full_name} | Status: '{kyc.status}' | User: {kyc.user}")

print("\nDistinct Statuses in DB:")
for s in all_kyc.values('status').annotate(c=Count('id')):
    print(f"  '{s['status']}': {s['c']}")

print("\nRecent Records:")
for kyc in all_kyc.order_by('-created_at')[:5]:
    print(f"  ID: {kyc.id} | Name: {kyc.submitted_full_name} | Status: {kyc.status} | Created: {kyc.created_at}")
