import os
import django
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.append(BASE_DIR)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'insurance_claim_system.settings')
django.setup()

from accounts.models import User, UserProfile, AadhaarKYCVerification
from policy.models import PolicyApplication, UserPolicy

print("=== CHECKING RAHUL SHARMA ===")
u = User.objects.filter(username__icontains='Rahul').first()
if not u:
    print("User 'Rahul_Sharma' not found in database.")
    sys.exit(0)

print(f"Username: {u.username}")
print(f"Legal Name: {u.full_name}")
print(f"Email: {u.email}")
print(f"Role: {u.role}")
print(f"Is Verified (User Model): {u.is_verified}")

# Profile
profile = getattr(u, 'profile', None)
if profile:
    print(f"Has Profile: Yes")
    print(f"Profile Name: {profile.full_name}")
    print(f"Profile Aadhaar: {profile.aadhaar_number}")
    print(f"Profile Verification Status: {profile.verification_status}")
    print(f"Profile Is Verified: {profile.is_verified}")
else:
    print("Has Profile: No")

# KYC Verifications
kyc = AadhaarKYCVerification.objects.filter(user=u).first()
if kyc:
    print(f"KYC Record Found: Yes")
    print(f"KYC Verification Status: {kyc.status}")
    print(f"KYC Extracted Name: {kyc.extracted_name}")
    print(f"KYC Extracted Number: {kyc.extracted_number}")
else:
    print("KYC Record Found: No")

# Policy Applications
apps = PolicyApplication.objects.filter(user=u)
print(f"Policy Applications Count: {apps.count()}")
for app in apps:
    print(f"  - Policy: {app.policy.policy_number}, Status: {app.status}, Created: {app.created_at}")

# Active/Awaiting Policies
ups = UserPolicy.objects.filter(user=u)
print(f"User Policies Count: {ups.count()}")
for up in ups:
    print(f"  - UserPolicy Certificate: {up.certificate_number}, Status: {up.status}, Paid: {up.is_paid}")
