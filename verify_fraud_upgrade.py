import os
import sys
import django
import logging
from datetime import date, timedelta

# Setup Django
sys.path.append(os.getcwd())
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'insurance_claim_system.settings')
django.setup()

from ai_features.services.fraud_service import predict_fraud_risk
from claims.models import Claim
from policy.models import Policy, UserPolicy

# Set logging
logging.basicConfig(level=logging.INFO)

def test_fraud_upgrade():
    # Mock a claim with some high risk features
    # amount=500,000, frequency=5, age=1 month, weekend=True
    
    # In a real test we'd create objects, but here I'll just check if the logic runs
    print("\n--- Testing Upgraded Fraud Model (Threshold: 0.35) ---")
    
    # We need a real claim object for the service
    claim = Claim.objects.first()
    if not claim:
        print("No claims found in DB to test with.")
        return

    # Update claim to be high risk for testing
    claim.claimed_amount = 500000
    claim.incident_date = date(2024, 3, 22) # a Saturday
    
    # Ensure policy exists and is young
    if claim.policy:
        claim.policy.start_date = date(2024, 3, 1) # ~3 weeks before incident
        claim.policy.save()

    score, flag, level, explanation = predict_fraud_risk(claim)
    print(f"Risk Score: {score:.1f}%")
    print(f"Fraud Flag: {flag}")
    print(f"Risk Level: {level}")
    print(f"Explanation: {explanation}")

if __name__ == "__main__":
    test_fraud_upgrade()
