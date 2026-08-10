import os
import sys
import django

sys.path.append('D:\\insurance_claim_system_NEW')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'insurance_claim_system.settings')
django.setup()

from claims.models import Claim
from notifications.models import Notification

print("Do we have a Claim with public_id='2f037186-3d80-4901-bfbe-8326674e1d83'?")
print(Claim.objects.filter(public_id='2f037186-3d80-4901-bfbe-8326674e1d83').exists())

print("Do we have ANY Claim with public_id cf030d55-c672-438f-ac8f-e12a3bb4f028?")
print(Claim.objects.filter(public_id='cf030d55-c672-438f-ac8f-e12a3bb4f028').exists())

print("Let's look at all claims starting with CLM-SEED-0014:")
for c in Claim.objects.filter(claim_number__icontains='0014'):
    print(f"Number: {c.claim_number} | Public ID: {c.public_id} | Created: {c.created_at}")

print("Let's see if there are other notifications for CLM-SEED-0014:")
for n in Notification.objects.filter(message__icontains='CLM-SEED-0014'):
    print(f"User: {n.user.username} | Title: {n.title} | Claim ID: {n.related_claim_id}")
