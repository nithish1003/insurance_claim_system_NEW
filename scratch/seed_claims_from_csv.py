import os
import sys
import django
import csv
from decimal import Decimal
from django.utils import timezone

# Setup Django settings
sys.path.append(os.getcwd())
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'insurance_claim_system.settings')
django.setup()

from claims.models import Claim
from policy.models import Policy, UserPolicy
from django.contrib.auth import get_user_model
from django.db.models.signals import post_save
from django.db import transaction

# Import the signal functions to disconnect them
from ai_features.signals import trigger_ai_predictions
from notifications.signals import claim_status_notification

def main():
    # Disconnect signals to avoid slow processing, notifications, and prediction runs during seeding
    post_save.disconnect(trigger_ai_predictions, sender=Claim)
    post_save.disconnect(claim_status_notification, sender=Claim)
    
    csv_path = "datasets/claim_type_dataset.csv"
    if not os.path.exists(csv_path):
        print(f"Error: CSV file not found at {csv_path}")
        sys.stdout.flush()
        return
        
    User = get_user_model()
    user = User.objects.first()
    policy = Policy.objects.first()
    user_policy = UserPolicy.objects.first()
    
    if not user or not policy:
        print("Error: Ensure you have at least one User and one Policy in the database.")
        sys.stdout.flush()
        return

    # Delete existing seeded claims to make it clean & idempotent
    seeded_claims = Claim.objects.filter(claim_number__startswith="CLM-SEED-")
    seeded_claim_ids = list(seeded_claims.values_list('public_id', flat=True))
    
    deleted_count, _ = seeded_claims.delete()
    if deleted_count > 0:
        print(f"Cleaned up {deleted_count} existing seeded claims.")
        sys.stdout.flush()
        
        # Clean up notifications associated with these deleted seeded claims
        from notifications.models import Notification
        deleted_notifs, _ = Notification.objects.filter(related_claim_id__in=seeded_claim_ids).delete()
        if deleted_notifs > 0:
            print(f"Cleaned up {deleted_notifs} orphaned notifications associated with seeded claims.")
            sys.stdout.flush()

    print("Seeding claims from claim_type_dataset.csv in a single transaction...")
    sys.stdout.flush()
    created_count = 0
    
    with open(csv_path, mode='r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        with transaction.atomic():
            for i, row in enumerate(reader):
                desc = row['description'].strip()
                ctype = row['claim_type'].strip()
                
                # Map standard claim types (if needed)
                if ctype not in ['accident', 'medical', 'theft', 'death', 'disability', 'other']:
                    ctype = 'other'
                    
                claim_num = f"CLM-SEED-{i:04d}"
                
                # Keep dataset rows archived so they don't flood live staff workflow queues.
                Claim.objects.create(
                    claim_number=claim_num,
                    claim_type=ctype,
                    final_claim_type=ctype,
                    description=desc,
                    incident_date=timezone.now().date(),
                    claimed_amount=Decimal("1000.00"),
                    policy=policy,
                    user_policy=user_policy,
                    created_by=user,
                    status="closed"
                )
                created_count += 1
            
    print(f"Successfully seeded {created_count} verified claims into the database.")
    sys.stdout.flush()


if __name__ == '__main__':
    main()
