import os
import django

# Set up Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'insurance_claim_system.settings')
django.setup()

from policy.models import Policy

def backfill_policy_premiums():
    policies = Policy.objects.all()
    count = 0
    for policy in policies:
        # Trigger the save() method which performs the calculations
        policy.save()
        count += 1
        print(f"Updated Policy: {policy.policy_number}")
    print(f"Successfully backfilled {count} policies.")

if __name__ == "__main__":
    backfill_policy_premiums()
