import os
import sys
import django

# Add current directory to path
sys.path.append(os.getcwd())

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "insurance_claim_system.settings")
django.setup()

from django.contrib.auth import get_user_model
from policy.models import UserPolicy, PolicyApplication

User = get_user_model()
print("All users:")
for u in User.objects.all():
    print(f"ID: {u.id}, Username: {u.username}, Email: {u.email}, Full Name: {u.get_full_name()}")

print("\nAll UserPolicies:")
for up in UserPolicy.objects.all():
    policy_num = up.policy.policy_number if up.policy else 'None'
    print(f"ID: {up.id}, User: {up.user.username}, Policy: {policy_num}, Vehicle: '{up.vehicle_number}', Status: {up.status}")

print("\nAll PolicyApplications:")
for pa in PolicyApplication.objects.all():
    user_str = pa.user.username if pa.user else 'None'
    policy_num = pa.policy.policy_number if pa.policy else 'None'
    print(f"PA ID: {pa.id}, User: {user_str}, Policy: {policy_num}, Vehicle: '{pa.vehicle_number}', Status: {pa.status}")
