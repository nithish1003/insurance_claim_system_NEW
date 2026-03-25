from policy.models import UserPolicy, Policy
from premiums.models import PremiumSchedule

def detect_duplicates():
    print("--- DUPLICATE SCHEDULES AUDIT ---")
    schedules = PremiumSchedule.objects.all().order_by('id')
    
    # Simple map of (user_id, policy_id) -> count
    seen = {}
    for s in schedules:
        key = (s.user_policy.user_id if s.user_policy else "N/A", s.policy_id)
        if key in seen:
            print(f"[DUPLICATE FOUND] ID: {s.id} | USER: {key[0]} | POLICY: {s.policy.policy_number} | START: {s.start_date} | END: {s.end_date}")
            seen[key].append(s.id)
        else:
            seen[key] = [s.id]
            
    # List all for POL-MNNAM5
    print("\n--- ALL FOR POL-MNNAM5 ---")
    pol = Policy.objects.filter(policy_number='POL-MNNAM5').first()
    if pol:
        ss = PremiumSchedule.objects.filter(policy=pol)
        for s in ss:
            cert = s.user_policy.certificate_number if s.user_policy else "NONE"
            print(f"ID: {s.id} | CERT: {cert} | PERIOD: {s.start_date} -> {s.end_date} | GROSS: {s.gross_premium}")

if __name__ == "__main__":
    import django
    import os
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'insurance_claim_system.settings')
    django.setup()
    detect_duplicates()
