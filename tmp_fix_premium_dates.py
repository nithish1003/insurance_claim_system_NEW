import os
import django
import calendar
from datetime import date

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'insurance_claim_system.settings')
django.setup()

from premiums.models import PremiumSchedule, PremiumPayment

def add_months(base_date, months):
    year = base_date.year + (base_date.month - 1 + months) // 12
    month = (base_date.month - 1 + months) % 12 + 1
    day = min(base_date.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)

schedules = PremiumSchedule.objects.filter(user_policy__isnull=False)
print(f"Checking {schedules.count()} UserPolicy-linked schedules...")

for ps in schedules:
    up = ps.user_policy
    print(f"Found schedule for {up.certificate_number} Plan: {ps.policy.policy_number}")
    print(f"Current Date Range: {ps.start_date} -> {ps.end_date}")
    print(f"UserPolicy Coverage: {up.start_date} -> {up.end_date}")
    
    # Update dates to 2026 range if they differ
    if ps.start_date != up.start_date:
        ps.start_date = up.start_date
        ps.end_date = up.end_date
        ps.save()
        print(f"Updated schedule dates to {ps.start_date}")
        
        step = {'monthly': 1, 'quarterly': 3, 'yearly': 12}.get(ps.payment_frequency, 1)
        for p in ps.payments.all():
            p.due_date = add_months(up.start_date, (p.installment_number - 1) * step)
            p.save()
            print(f"Updated installment #{p.installment_number} due_date to {p.due_date}")
        print(f"Successfully fixed all installments for {up.certificate_number}")
    else:
        print(f"Dates are already synchronized for {up.certificate_number}")
