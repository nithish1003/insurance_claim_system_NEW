
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'insurance_claim_system.settings')
django.setup()

from policy.models import Payment
from claims.models import Claim

def synchronize_ledger():
    print("--- Synchronizing Unified Ledger Amounts ---")
    
    # 1. Update existing payments tied to claims
    settlement_payments = Payment.objects.filter(payment_type='CLAIM_SETTLEMENT').select_related('claim')
    
    count = 0
    for p in settlement_payments:
        if p.claim and p.claim.settled_amount is not None:
             if p.amount != p.claim.settled_amount:
                 print(f"Syncing TXN {p.transaction_id}: ₹{p.amount} -> ₹{p.claim.settled_amount}")
                 p.amount = p.claim.settled_amount
                 p.save()
                 count += 1
    
    print(f"Update complete. {count} records synchronized.")

if __name__ == "__main__":
    synchronize_ledger()
