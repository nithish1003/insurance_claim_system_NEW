import os
import django
from django.core.exceptions import ValidationError

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'insurance_claim_system.settings')
django.setup()

from claims.models import Claim
from policy.models import Policy

print("Testing status enforcement...")
try:
    p = Policy.objects.first()
    # Try creating a settled claim directly
    c = Claim.objects.create(
        policy=p,
        claim_number="TEST-FORCED-SETTLE",
        status="settled",
        incident_date="2026-03-23",
        claimed_amount=1000
    )
    print("Failure! Should have blocked settled creation.")
except ValidationError as e:
    print(f"Success! Blocked settled creation: {e}")
except Exception as e:
    print(f"Error: {e}")
