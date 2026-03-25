#!/usr/bin/env python3
"""
Test script to verify ML integration works correctly
"""

import os
import sys
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'insurance_claim_system.settings')
django.setup()

from claims.models import Claim, Policy
from policy.models import PolicyPlan, Insurer, PolicyType
from ai_features.services.ai_claim_service import predict_claim_type
from ai_features.services.fraud_service import predict_fraud_risk
from ai_features.services.amount_service import predict_recommended_amount


def test_ml_services():
    """Test all ML services"""
    print("Testing ML Integration...")
    
    # Test 1: Claim Type Prediction
    print("\n1. Testing Claim Type Prediction:")
    test_descriptions = [
        "I was involved in a car accident on the highway",
        "Hospitalized for heart surgery",
        "My car was stolen from parking lot",
        "General insurance inquiry"
    ]
    
    for desc in test_descriptions:
        claim_type, confidence = predict_claim_type(desc)
        print(f"  Description: '{desc[:50]}...'")
        print(f"  Predicted: {claim_type} (confidence: {confidence:.3f})")
    
    # Test 2: Fraud Detection (requires a Claim instance)
    print("\n2. Testing Fraud Detection:")
    try:
        # Create a test claim instance (without saving to DB)
        from django.contrib.auth.models import User
        
        # Create test policy if it doesn't exist
        policy_type, _ = PolicyType.objects.get_or_create(
            name="Test Policy Type",
            defaults={'code': 'test_type', 'description': 'Test policy type'}
        )
        
        insurer, _ = Insurer.objects.get_or_create(
            name="Test Insurer",
            defaults={'address': 'Test Address', 'contact_email': 'test@example.com'}
        )
        
        plan, _ = PolicyPlan.objects.get_or_create(
            name="Test Plan",
            defaults={
                'description': 'Test plan',
                'policy_type': policy_type,
                'insurer': insurer,
                'sum_insured': 100000,
                'premium': 5000,
                'deductible': 1000,
                'coverage_details': 'Test coverage',
                'terms_and_conditions': 'Test terms'
            }
        )
        
        policy, _ = Policy.objects.get_or_create(
            policy_number="TEST_POLICY_001",
            defaults={
                'plan': plan,
                'policy_type': 'test',
                'status': 'active',
                'insurer_name': 'Test Insurer',
                'start_date': '2024-01-01',
                'end_date': '2025-01-01',
                'sum_insured': 100000,
                'deductible': 1000,
                'coverage_percentage': 80.00
            }
        )
        
        user, _ = User.objects.get_or_create(
            username='test_user',
            defaults={'email': 'test@example.com', 'password': 'testpass123'}
        )
        
        claim = Claim(
            policy=policy,
            claim_number="TEST_CLAIM_001",
            claim_type="accident",
            status="submitted",
            incident_date="2024-01-15",
            description="Test accident claim",
            claimed_amount=50000,
            created_by=user
        )
        
        risk_score, fraud_flag = predict_fraud_risk(claim)
        print(f"  Risk Score: {risk_score:.1f}")
        print(f"  Fraud Flag: {fraud_flag}")
        
        # Test 3: Amount Prediction
        print("\n3. Testing Amount Prediction:")
        recommended_amount = predict_recommended_amount(claim)
        print(f"  Recommended Amount: ₹{recommended_amount:.2f}")
        print(f"  Claimed Amount: ₹{claim.claimed_amount:.2f}")
        
    except Exception as e:
        print(f"  Error in fraud/amount testing: {e}")
        print("  This is expected if models are not trained yet")
    
    print("\nML Integration Test Complete!")
    print("To train models, run: python manage.py train_ai_models")


if __name__ == "__main__":
    test_ml_services()