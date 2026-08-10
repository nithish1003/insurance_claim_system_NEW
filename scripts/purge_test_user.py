import os
import django
import sys

# Setup Django
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'insurance_claim_system.settings')
django.setup()

from django.contrib.auth import get_user_model
from claims.models import Claim

def purge_test_data(username):
    User = get_user_model()
    try:
        user = User.objects.filter(username=username).first()
        if not user:
            print(f"[ERROR] User {username} not found.")
            return

        # Explicitly delete claims associated with user
        claims = Claim.objects.filter(user_policy__user=user)
        count = claims.count()
        print(f"[PROCESS] Found {count} claims for {username}. Deleting...")
        claims.delete()

        # Delete User
        user.delete()
        print(f"[SUCCESS] User {username} and associated dossier data purged.")

    except Exception as e:
        print(f"[FATAL ERROR] {e}")

if __name__ == "__main__":
    purge_test_data("ocr_test_user")
