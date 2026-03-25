import os
import sys
import django

# Setup Django environment
sys.path.append('.')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'insurance_claim_system.settings')
django.setup()

from policy.models import Payment

def fix_ledger_directions():
    print("Fixing ledger directions...")
    # Settlements should be DEBIT
    count = Payment.objects.filter(payment_type='CLAIM_SETTLEMENT').update(direction='DEBIT')
    print(f"Updated {count} settlement records to DEBIT.")

    # Premiums are CREDIT (default is CREDIT, but just to be sure)
    count = Payment.objects.filter(payment_type='PREMIUM_PAYMENT').update(direction='CREDIT')
    print(f"Verified {count} premium records as CREDIT.")

if __name__ == "__main__":
    fix_ledger_directions()
