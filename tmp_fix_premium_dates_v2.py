import os
import django
import calendar
from datetime import date

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'insurance_claim_system.settings')
django.setup()

from policy.models import UserPolicy, Policy
from premiums.models import PremiumSchedule, PremiumPayment

def add_months(base_date, months):
    year = base_date.year + (base_date.month - 1 + months) // 12
    month = (base_date.month - 1 + months) % 12 + 1
    day = min(base_date.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)

# 1. Find all UserPolicies that MISS their own dedicated PremiumSchedule
ups = UserPolicy.objects.filter(premium_schedule__isnull=True)
print(f"Found {ups.count()} UserPolicies without dedicated schedules.")

for up in ups:
    print(f"Checking {up.certificate_number} Plan: {up.policy.policy_number}...")
    
    # Check if the policy plan has a generic schedule template
    template = PremiumSchedule.objects.filter(policy=up.policy, user_policy__isnull=True).first()
    if template:
        print(f"Template found for {up.policy.policy_number} starting {template.start_date}")
        
        # Create NEW dedicated schedule
        new_ps = PremiumSchedule.objects.create(
            user_policy=up,
            policy=up.policy,
            base_premium=template.base_premium,
            gst_percentage=template.gst_percentage,
            gst_amount=template.gst_amount,
            gross_premium=template.gross_premium,
            payment_frequency=template.payment_frequency,
            total_installments=template.total_installments,
            installment_amount=template.installment_amount,
            auto_debit_enabled=template.auto_debit_enabled,
            start_date=up.start_date, # Correct 2026 range
            end_date=up.end_date,
        )
        print(f"Created NEW schedule starting {new_ps.start_date}")
        
        step = {'monthly': 1, 'quarterly': 3, 'yearly': 12}.get(new_ps.payment_frequency, 1)
        for i in range(new_ps.total_installments):
            PremiumPayment.objects.create(
                schedule=new_ps,
                installment_number=i + 1,
                due_date=add_months(up.start_date, i * step),
                amount=new_ps.installment_amount,
                status="upcoming"
            )
        print(f"Successfully generated {new_ps.total_installments} individual installments.")
    else:
        print(f"No template found for {up.policy.policy_number}. Skipping.")
