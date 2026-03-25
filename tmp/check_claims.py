import os
import sys
import django
sys.path.append(os.getcwd())
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'insurance_claim_system.settings')
django.setup()
from claims.models import Claim
print(f'Total Claims: {Claim.objects.count()}')
print(f'Claims with Final Type: {Claim.objects.exclude(final_claim_type__isnull=True).exclude(final_claim_type="").count()}')
for claim in Claim.objects.exclude(final_claim_type__isnull=True).exclude(final_claim_type="")[:5]:
    print(f"ID: {claim.id} | Desc: {claim.description[:30]} | Type: {claim.final_claim_type}")
