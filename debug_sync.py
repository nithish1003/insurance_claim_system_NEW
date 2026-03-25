from claims.models import Claim, ClaimSettlement
from policy.models import UserPolicy, Payment
from django.contrib.auth import get_user_model
from django.utils import timezone
from decimal import Decimal

User = get_user_model()
admin = User.objects.get(role='admin') # or is_superuser

# 1. SETTLE APPROVED CLAIM
claim = Claim.objects.filter(status='approved').first()
if claim:
    if not claim.approved_amount:
        claim.approved_amount = Decimal('19000.00')
    claim.status = 'settled'
    claim.settled_amount = claim.approved_amount
    claim.save()
    ClaimSettlement.objects.get_or_create(
        claim=claim,
        defaults={
            'settled_amount': claim.settled_amount,
            'payee_name': claim.created_by.get_full_name() or claim.created_by.username,
            'processed_by': admin,
            'payment_mode': 'neft',
            'settlement_date': timezone.now().date()
        }
    )
    print("Settled claim CLM-XXXX")

# 2. CREATE SUCCESSFUL PAYMENT
up = UserPolicy.objects.filter(status='active').first()
if up:
    Payment.objects.get_or_create(
        user_policy=up,
        payment_status='completed',
        defaults={
            'amount': Decimal('5000.00'),
            'payment_method': 'upi',
            'description': 'Policy activation premium'
        }
    )
    print("Created payment for POL-XXXX")
