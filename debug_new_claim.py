from django.db import connection, reset_queries
from claims.models import Claim
from policy.models import UserPolicy
from django.contrib.auth import get_user_model
from django.utils import timezone
from decimal import Decimal
import random

reset_queries()
try:
    User = get_user_model()
    ph = User.objects.get(username='RAVI')
    up = UserPolicy.objects.filter(user=ph).first()
    Claim.objects.create(
        claim_number=f"CLM-{random.randint(100, 999)}",
        policy=up.policy,
        created_by=ph,
        status='submitted',
        claim_type='accident',
        incident_date=timezone.now().date(),
        claimed_amount=Decimal('500.00'),
        risk_score=10.0
    )
except Exception as e:
    print(f"ERROR: {e}")
    for q in connection.queries:
        print(q['sql'])
