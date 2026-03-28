import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'insurance_claim_system.settings')
django.setup()

from claims.models import Claim
from policy.models import UserPolicy

def run_migration():
    claims = Claim.objects.all()
    updated_count = 0
    not_found_count = 0
    
    print(f"Starting migration for {claims.count()} claims...")
    
    for claim in claims:
        if not claim.user_policy:
            try:
                # Find matching UserPolicy for the user and policy plan
                user_policy = UserPolicy.objects.get(user=claim.created_by, policy=claim.policy)
                claim.user_policy = user_policy
                claim.save()
                updated_count += 1
                print(f"✅ Updated Claim {claim.claim_number} -> UserPolicy {user_policy.certificate_number}")
            except UserPolicy.DoesNotExist:
                not_found_count += 1
                print(f"❌ No matching UserPolicy found for Claim {claim.claim_number} (User: {claim.created_by}, Policy Plan: {claim.policy})")
            except UserPolicy.MultipleObjectsReturned:
                # Use the most recent if multiple exist
                user_policy = UserPolicy.objects.filter(user=claim.created_by, policy=claim.policy).latest('assigned_at')
                claim.user_policy = user_policy
                claim.save()
                updated_count += 1
                print(f"⚠️ Multiple matches for Claim {claim.claim_number}, used latest: {user_policy.certificate_number}")
        else:
            print(f"ℹ️ Claim {claim.claim_number} already linked.")
            
    print(f"\nMigration complete. Updated: {updated_count}, Not Found: {not_found_count}")

if __name__ == "__main__":
    run_migration()
