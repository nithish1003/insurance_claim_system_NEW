from policy.models import Payment
from claims.models import Claim, ClaimSettlement

def audit():
    print("--- RAVI AUDIT ---")
    ravi_claims = Claim.objects.all() # No name filter, just all for now
    for c in ravi_claims:
        print(f"CLAIM: {c.claim_number} | AMOUNT: {c.claimed_amount} | APPROVED: {c.approved_amount} | STATUS: {c.status}")
    
    ravi_payments = Payment.objects.all()
    for p in ravi_payments:
        user = p.user_policy.user.username if p.user_policy else "Unknown"
        print(f"PAYMENT ID: {p.id} | USER: {user} | AMOUNT: {p.amount} | STATUS: {p.payment_status} | REF: {p.transaction_id}")

    ravi_settlements = ClaimSettlement.objects.all()
    for s in ravi_settlements:
        print(f"SETTLEMENT ID: {s.id} | CLAIM: {s.claim.claim_number} | AMOUNT: {s.settled_amount}")

if __name__ == "__main__":
    import django
    import os
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'insurance_claim_system.settings')
    django.setup()
    audit()
