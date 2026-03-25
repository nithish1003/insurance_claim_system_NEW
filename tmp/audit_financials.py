from claims.models import ClaimSettlement
from policy.models import Payment
from decimal import Decimal

def check_financials():
    print("--- 💸 All Settlements (DEBITS) ---")
    ss = ClaimSettlement.objects.all().order_by('-created_at')
    if not ss.exists():
        print("Empty.")
    for s in ss:
        print(f"ID: {s.id} | CLAIM: {s.claim.claim_number} | AMOUNT: {s.settled_amount} | CREATED: {s.created_at}")

    print("\n--- 💰 All Payments (CREDITS) ---")
    pp = Payment.objects.all().order_by('-created_at')
    if not pp.exists():
        print("Empty.")
    for p in pp:
        name = p.user_policy.user.username if p.user_policy and p.user_policy.user else "Anon"
        print(f"ID: {p.id} | USER: {name} | AMOUNT: {p.amount} | STATUS: {p.payment_status} | REF: {p.transaction_id}")

if __name__ == "__main__":
    import django
    import os
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'insurance_claim_system.settings')
    django.setup()
    check_financials()
