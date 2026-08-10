import os
import django
import sys

# Setup Django
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'insurance_claim_system.settings')
django.setup()

from policy.models import Policy

def purge_sync_policies():
    try:
        policies = Policy.objects.filter(policy_number__startswith='SYNC-POL-')
        count = policies.count()
        
        if count == 0:
            print("[INFO] No SYNC-POL- dummy policies found.")
            return

        print(f"[PROCESS] Found {count} dummy policies. Purging...")
        
        # Deleting Policy will cascade to PolicyHolder, UserPolicy, Claim etc if set to CASCADE
        policies.delete()
        
        print(f"[SUCCESS] {count} dummy policies purged from the system.")

    except Exception as e:
        print(f"[ERROR] {e}")

if __name__ == "__main__":
    purge_sync_policies()
