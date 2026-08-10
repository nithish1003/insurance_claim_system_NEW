import os
import django
import sys

# Ensure d:\insurance_claim_system_NEW is in sys.path
sys.path.append(r'd:\insurance_claim_system_NEW')

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'insurance_claim_system.settings')
django.setup()
from accounts.models import User
print(f"Total Users: {User.objects.count()}")
print(f"Users with role 'user': {User.objects.filter(role='user').count()}")
print(f"Users with role 'staff': {User.objects.filter(role='staff').count()}")
print(f"Users with role 'admin': {User.objects.filter(role='admin').count()}")
for u in User.objects.all():
    print(f"ID: {u.id}, Username: {u.username}, Role: {u.role}")
