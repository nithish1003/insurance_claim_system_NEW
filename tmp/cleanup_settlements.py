from claims.models import ClaimSettlement
from django.db.models import F

def cleanup_settlements():
    # Only fix settled claims where the payout record amount differs from the verified approved_amount
    mismatched = ClaimSettlement.objects.exclude(settled_amount=F('claim__approved_amount'))
    count = 0
    for s in mismatched:
        if s.claim and s.claim.approved_amount is not None:
             print(f"[RECONCILE] Settlement {s.id}: Correcting mismatch {s.settled_amount} -> {s.claim.approved_amount}")
             s.settled_amount = s.claim.approved_amount
             s.save()
             count += 1
    print(f"Data Cleanup Finished: Reconciled {count} settlement records with approve amounts.")

if __name__ == "__main__":
    import django
    import os
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'insurance_claim_system.settings')
    django.setup()
    cleanup_settlements()
