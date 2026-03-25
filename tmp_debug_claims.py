import os
import django
import sys

# Ensure current dir is in sys.path
sys.path.append('d:\\insurance_claim_system_NEW')

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'insurance_claim_system.settings')
django.setup()

from claims.models import Claim

claims = Claim.objects.all().order_by('-created_at')[:10]
print("Claim List Check:")
for c in claims:
    print(f"ID: {c.id}, Num: {c.claim_number}, Claimed: {c.claimed_amount}, AI Pred: {c.ai_predicted_amount}, AI Recom: {c.recommended_amount}")
