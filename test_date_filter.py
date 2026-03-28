import os
import django
from datetime import date

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'insurance_claim_system.settings')
django.setup()

from claims.models import Claim

print("Testing date filter...")
try:
    d = date(2026, 3, 23)
    count = Claim.objects.filter(incident_date__gte=d).count()
    print(f"Success! Count: {count}")
except Exception as e:
    print(f"Failed! Error: {e}")
    import traceback
    traceback.print_exc()
