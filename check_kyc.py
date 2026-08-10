import os
import django
import sys

# Set up Django environment
sys.path.append(os.getcwd())
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'insurance_claim_system.settings')
django.setup()

from accounts.models import User, UserProfile

def check_user_data(username):
    try:
        user = User.objects.get(username=username)
        print(f"--- User Model: {username} ---")
        print(f"Role: {user.role}")
        print(f"Aadhaar Number: {user.aadhaar_number}")
        print(f"ID Proof: {user.id_proof}")
        print(f"Is Verified: {user.is_verified}")
        
        try:
            profile = user.profile
            print(f"--- UserProfile Model ---")
            print(f"Full Name: {profile.full_name}")
            print(f"Aadhaar Number: {profile.aadhaar_number}")
            print(f"ID Proof: {profile.id_proof}")
            print(f"Verification Status: {profile.verification_status}")
            print(f"Is Verified: {profile.is_verified}")
        except UserProfile.DoesNotExist:
            print("--- UserProfile DOES NOT EXIST ---")
            
    except User.DoesNotExist:
        print(f"User {username} not found.")

if __name__ == "__main__":
    check_user_data("ravi_kumar")
