import os
import sys
import django

# Setup Django settings
sys.path.append(os.getcwd())
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'insurance_claim_system.settings')
django.setup()

from accounts.models import User, UserProfile, AadhaarKYCVerification

def main():
    username = "Rahul_Sharma"
    print(f"Checking data for user: {username}")
    
    try:
        user = User.objects.get(username=username)
        print(f"User: {user.username}, Role: {user.role}")
        try:
            profile = user.profile
            print(f"Profile Full Name: '{profile.full_name}'")
            print(f"Profile Aadhaar Number: '{profile.aadhaar_number}'")
            print(f"Profile Masked Aadhaar: '{profile.masked_aadhaar}'")
        except Exception as e:
            print(f"No profile or error: {e}")
            
        print("\n--- Aadhaar KYC Verification Records ---")
        records = AadhaarKYCVerification.objects.filter(submitted_full_name__icontains="rahul")
        if not records.exists():
            records = AadhaarKYCVerification.objects.all().order_by('-id')[:5]
            print("No explicit rahul records. Showing last 5 records:")
            
        for r in records:
            print(f"ID: {r.id}")
            print(f"Submitted Name: '{r.submitted_full_name}', Extracted Name: '{r.extracted_name}'")
            print(f"Submitted Aadhaar: '{r.submitted_aadhaar_number}', Extracted Aadhaar: '{r.extracted_number}'")
            print(f"Status: '{r.status}', Verified At: {r.verified_at}")
            print(f"Details: {r.details}")
            print("-" * 30)
            
    except User.DoesNotExist:
        print(f"User {username} not found.")

if __name__ == '__main__':
    main()
