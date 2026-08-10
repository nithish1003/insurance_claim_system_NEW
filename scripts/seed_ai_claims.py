import os
import django
from decimal import Decimal
from django.utils import timezone
import uuid

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'insurance_claim_system.settings')
django.setup()

from claims.models import Claim
from policy.models import Policy, UserPolicy, PolicyPlan, PolicyType
from django.contrib.auth import get_user_model

User = get_user_model()

def seed_data():
    # 1. Get or create a user (SUPERUSER)
    user = User.objects.filter(is_superuser=True).first()
    if not user:
        print("Please create a superuser first.")
        return

    # 2. Create Policy Type
    pt, _ = PolicyType.objects.get_or_create(
        code="health",
        defaults={"name": "Health Insurance", "category_type": "medical"}
    )

    # 3. Create Policy Plan
    plan, _ = PolicyPlan.objects.get_or_create(
        name="AI Advanced Health Guard",
        defaults={
            "description": "Smart coverage powered by neural decisioning.",
            "policy_type": pt,
            "sum_insured": Decimal("5000000"),
            "premium": Decimal("50000")
        }
    )

    # 4. Create Policy
    # Note: Policy model requires start_date and end_date
    policy_params = {
        "plan": plan,
        "sum_insured": Decimal("5000000"),
        "base_premium": Decimal("50000"),
        "start_date": timezone.now().date(),
        "end_date": timezone.now().date() + timezone.timedelta(days=365),
    }
    policy, _ = Policy.objects.update_or_create(
        policy_number="AI-HEALTH-999",
        defaults=policy_params
    )

    # 5. Create User Policy
    up_params = {
        "user": user,
        "policy": policy,
        "start_date": timezone.now().date(),
        "sum_insured_remaining": Decimal("5000000")
    }
    user_policy, _ = UserPolicy.objects.update_or_create(
        certificate_number="UP-AI-001",
        defaults=up_params
    )

    # 6. Create Claim
    claim_data = {
        "claim_type": "medical",
        "incident_date": timezone.now().date(),
        "policy": policy,
        "user_policy": user_policy,
        "claimed_amount": Decimal("50000"),
        "deductible_amount": Decimal("2000"),
        "non_medical_cost": Decimal("5000"),
        "room_rent_cost": Decimal("8000"),
        "allowed_room_rent": Decimal("5000"),
        "diagnostics_cost": Decimal("15000"),
        "allowed_diagnostics": Decimal("10000"),
        "hospital_risk_score": 0.15,
        "user_risk_score": 0.05,
        "created_by": user,
        "description": "Post-surgical recovery with unexpected room upgrades.",
        "hospital_type": "private",
        "admission_days": 4,
        "ai_claim_type": "medical",
        "confidence_score": 98.4
    }
    
    # We use update_or_create to trigger the .save() logic including the AI calculation
    claim, created = Claim.objects.update_or_create(
        claim_number="CLM-AI-AUDIT-01",
        defaults=claim_data
    )

    if created:
        print(f"Created Test Claim: {claim.claim_number}")
    else:
        print(f"Updated Test Claim: {claim.claim_number}")
    
    print(f"AI Risk Score: {claim.risk_score}")
    print(f"AI Predicted Amount: {claim.ai_predicted_amount}")

if __name__ == "__main__":
    seed_data()
