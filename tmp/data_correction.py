
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'insurance_claim_system.settings')
django.setup()

from policy.models import Payment, UserPolicy
from claims.models import Claim, ClaimSettlement

def fix_data():
    print("--- Starting Data Correction ---")
    
    # 1. Find all settled claims
    settled_claims = Claim.objects.filter(status='settled')
    for claim in settled_claims:
        settlement = getattr(claim, 'settlement', None)
        if not settlement:
            print(f"Claim {claim.claim_number} is settled but has no settlement record? Skipping.")
            continue
            
        print(f"Syncing Claim {claim.claim_number} | Settled Amount: ₹{settlement.settled_amount}")
        
        # Determine the user policy
        # A claim should be linked to the user policy that was active for that user/policy
        user_policy = UserPolicy.objects.filter(user=claim.created_by, policy=claim.policy).first()
        
        if not user_policy:
             print(f"Could not find UserPolicy for {claim.created_by.username} and {claim.policy.policy_number}. Using fallback.")
             user_policy = UserPolicy.objects.filter(policy=claim.policy).first()

        # Update or Create Payment record in the unified ledger
        payment, created = Payment.objects.update_or_create(
            transaction_id=settlement.transaction_reference,
            defaults={
                'user_policy': user_policy,
                'claim': claim,
                'amount': settlement.settled_amount,
                'payment_status': 'completed',
                'payment_type': 'CLAIM_SETTLEMENT',
                'description': f"Claim Payout Settlement - {claim.claim_number}",
                'notes': f"Auto-synced from ClaimSettlement ID: {settlement.id}"
            }
        )
        
        if created:
            print(f"  ✓ Created new Payment record {payment.transaction_id}")
        else:
            print(f"  ✓ Updated existing Payment record {payment.transaction_id}")

    print("\n--- Data Correction Complete ---")

if __name__ == "__main__":
    fix_data()
