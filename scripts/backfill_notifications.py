import os
import django
from django.utils import timezone

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'insurance_claim_system.settings')
django.setup()

from notifications.models import Notification
from premiums.models import PremiumPayment
from notifications.utils import create_notification

def backfill_overdue_notifications():
    overdue_payments = PremiumPayment.objects.filter(status='overdue')
    count = 0
    for payment in overdue_payments:
        user = payment.schedule.user_policy.user
        if not user:
            continue
            
        # Check if notification already exists
        exists = Notification.objects.filter(
            user=user,
            related_payment_id=payment.public_id,
            title__icontains="Overdue"
        ).exists()
        
        if not exists:
            due_date_str = payment.due_date.strftime('%d %b, %Y')
            create_notification(
                user=user,
                title="Premium Overdue! 🚨",
                message=f"Premium overdue since {due_date_str}. Pay now to avoid interruption of coverage.",
                type='error',
                role_target='policyholder',
                related_payment_id=payment.public_id
            )
            count += 1
            print(f"Created notification for {user.username} - Payment {payment.public_id}")
    
    print(f"Backfill complete. Created {count} notifications.")

if __name__ == "__main__":
    backfill_overdue_notifications()
