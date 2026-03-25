
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'insurance_claim_system.settings')
django.setup()

from accounts.models import User, UserProfile

def check_users():
    for u in User.objects.all():
        p = getattr(u, 'profile', None)
        aadhaar = p.aadhaar_number if p else 'NONE'
        print(f"Username: {u.username} | Role: {u.role} | Aadhaar: {aadhaar}")

if __name__ == "__main__":
    check_users()
