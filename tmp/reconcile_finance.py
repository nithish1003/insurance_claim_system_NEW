
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'insurance_claim_system.settings')
django.setup()

from policy.models import Payment, UserPolicy
from claims.models import Claim, ClaimSettlement
from decimal import Decimal

def restructure_financials():
    print("--- Starting Financial Reconciliation ---")
    
    # 🎯 TARGET: Actual claim in DB
    try:
        claim = Claim.objects.get(approved_amount=Decimal('2800.00'))
        print(f"  ✓ Found target claim: {claim.claim_number}")
        
        # If the claim was approved but settled_amount is missing, sync it
        if claim.settled_amount is None or claim.settled_amount == 0:
            claim.settled_amount = Decimal('2800.00')
            claim.status = 'settled'
            claim.save()
            print(f"  ✓ Claim {claim.claim_number} marked as settled with 2,800")
            
        # Find the mis-mapped transaction showing 11,800
        payment = Payment.objects.filter(amount=Decimal('11800.00')).first()
        if payment:
            print(f"  ✓ Found mis-mapped TXN {payment.transaction_id}. Fixing classification & amount.")
            payment.claim = claim
            payment.payment_type = 'CLAIM_SETTLEMENT'
            # Note: payment.amount will be auto-synced to 2,800 if save() is correct
            payment.amount = claim.settled_amount
            payment.save() 
            print(f"  ✓ TXN {payment.transaction_id} now linked to claim with amount {payment.amount}")
            
        # Ensure a ClaimSettlement record exists for the settlement table
        settlement, created = ClaimSettlement.objects.update_or_create(
            claim=claim,
            defaults={
                'transaction_reference': payment.transaction_id if payment else "SETL-MANUAL-001",
                'settled_amount': claim.settled_amount,
                'payment_mode': 'neft',
                'payee_name': claim.created_by.full_name if hasattr(claim.created_by, 'full_name') else claim.created_by.username,
                'processed_by': claim.assigned_to or claim.created_by # Admin fallback
            }
        )
        if created:
            print(f"  ✓ Created ClaimSettlement record for consistency.")
        else:
             print(f"  ✓ Updated ClaimSettlement record.")

    except Claim.DoesNotExist:
        print("  ! No claim with approved_amount=2800 found.")
    except Exception as e:
        import traceback
        print(f"  ! Error during reconciliation: {str(e)}")
        traceback.print_exc()

    print("--- Reconciliation Complete ---")

if __name__ == "__main__":
    restructure_financials()
