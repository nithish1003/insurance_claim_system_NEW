import os
import sys
import django

# Set stdout to UTF-8
sys.stdout.reconfigure(encoding='utf-8')

# Add current directory to path
sys.path.append(os.getcwd())

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "insurance_claim_system.settings")
django.setup()

from policy.models import Policy, PolicyAuditLog, PolicyApplication, UserPolicy
from reports.models import ActivityLog

print("--- Policy Audit Logs ---")
for log in PolicyAuditLog.objects.filter(policy__policy_number='POL-BZLY49'):
    print(f"Action: {log.action}, Performed by: {log.performed_by.username if log.performed_by else 'None'}, Description: {log.description}, Created at: {log.created_at}")

print("\n--- Activity Logs ---")
for log in ActivityLog.objects.all():
    print(f"Title: {log.title}, User: {log.user.username if log.user else 'None'}, Details: {log.description}, Created at: {log.created_at}")
