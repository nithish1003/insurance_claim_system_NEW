import sys
import os
import django

# Add project root to sys.path
PROJECT_ROOT = r'd:\insurance_claim_system_NEW'
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'insurance_claim_system.settings')
django.setup()

from policy.models import UserPolicy, Policy
from premiums.models import PremiumSchedule

def detect_duplicates():
    results = []
    results.append("--- DUPLICATE SCHEDULES AUDIT ---")
    schedules = PremiumSchedule.objects.all().order_by('id')
    
    seen = {}
    for s in schedules:
        user_id = s.user_policy.user_id if s.user_policy else "N/A"
        policy_id = s.policy_id
        key = (user_id, policy_id)
        if key in seen:
            results.append(f"[DUPLICATE FOUND] ID: {s.id} | USER: {user_id} | POLICY: {s.policy.policy_number} | START: {s.start_date} | END: {s.end_date}")
            seen[key].append(s.id)
        else:
            seen[key] = [s.id]
            
    # List all for POL-MNNAM5
    results.append("\n--- ALL FOR POL-MNNAM5 ---")
    pol = Policy.objects.filter(policy_number='POL-MNNAM5').first()
    if pol:
        ss = PremiumSchedule.objects.filter(policy=pol).order_by('id')
        for s in ss:
            cert = s.user_policy.certificate_number if s.user_policy else "NONE"
            results.append(f"ID: {s.id} | CERT: {cert} | PERIOD: {s.start_date} -> {s.end_date} | GROSS: {s.gross_premium}")

    # Write to a persistent file location
    output_path = os.path.join(PROJECT_ROOT, 'tmp', 'duplicate_results.txt')
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(results))
    print(f"Report written to {output_path}")

if __name__ == "__main__":
    detect_duplicates()
