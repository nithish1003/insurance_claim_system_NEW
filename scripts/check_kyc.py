import os
import django
import sys

sys.path.append(r'd:\insurance_claim_system_NEW')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'insurance_claim_system.settings')
django.setup()
from accounts.models import User, AadhaarKYCVerification
print(f"Total Users: {User.objects.count()}")
print(f"Users with role 'user': {User.objects.filter(role='user').count()}")
print(f"KYC Records: {AadhaarKYCVerification.objects.count()}")
for kyc in AadhaarKYCVerification.objects.all():
    print(f"KYC ID: {kyc.id}, User: {kyc.user.username if kyc.user else kyc.profile.user.username}, Status: {kyc.status}")
