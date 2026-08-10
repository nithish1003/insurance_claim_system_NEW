import os
import sys
import django

# Add current directory to path
sys.path.append(os.getcwd())

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "insurance_claim_system.settings")
django.setup()

from policy.models import Policy

p = Policy.objects.get(policy_number='POL-BZLY49')
print(f"Policy: {p.policy_number}, Type: {p.policy_type}, Sum Insured: {p.sum_insured}, Vehicle: {p.vehicle_number}")
