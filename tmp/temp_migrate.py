from claims.models import Claim
from policy.models import UserPolicy

def run():
    updated = 0
    not_found = 0
    claims = Claim.objects.filter(user_policy__isnull=True)
    print(f"Migrating {claims.count()} claims...")
    
    for c in claims:
        try:
            # Find matching UserPolicy for the user who created the claim and the policy plan
            up = UserPolicy.objects.get(user=c.created_by, policy=c.policy)
            c.user_policy = up
            c.save()
            updated += 1
            print(f"✓ Claim {c.claim_number} linked to UserPolicy {up.certificate_number}")
        except UserPolicy.DoesNotExist:
            not_found += 1
            print(f"✗ Claim {c.claim_number} - No matching UserPolicy found")
        except UserPolicy.MultipleObjectsReturned:
            up = UserPolicy.objects.filter(user=c.created_by, policy=c.policy).latest('assigned_at')
            c.user_policy = up
            c.save()
            updated += 1
            print(f"! Claim {c.claim_number} - Multiple matches, linked to latest")
            
    print(f"Migration complete. Updated: {updated}, Missing: {not_found}")

run()
