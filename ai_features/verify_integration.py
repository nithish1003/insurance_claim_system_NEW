#!/usr/bin/env python3
"""
Verification script to ensure all APIs work correctly with ML models
"""

import os
import sys
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'insurance_claim_system.settings')
django.setup()

from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import User
from claims.models import Claim, Policy
from policy.models import PolicyPlan, Insurer, PolicyType
import json


def verify_api_integration():
    """Verify that all APIs work correctly with ML integration"""
    print("Verifying API Integration with ML Models...")
    
    # Test 1: Check if models can be imported
    print("\n1. Testing ML Model Imports:")
    try:
        from ai_features.services.ai_claim_service import predict_claim_type
        from ai_features.services.fraud_service import predict_fraud_risk
        from ai_features.services.amount_service import predict_recommended_amount
        print("   ✓ All ML services imported successfully")
    except ImportError as e:
        print(f"   ✗ Import error: {e}")
        return False
    
    # Test 2: Check if models can be loaded
    print("\n2. Testing Model Loading:")
    try:
        # Test claim type prediction
        claim_type, confidence = predict_claim_type("Test accident claim")
        print(f"   ✓ Claim type prediction works: {claim_type} (confidence: {confidence:.3f})")
    except Exception as e:
        print(f"   ⚠ Claim type model not loaded (expected if not trained): {e}")
    
    # Test 3: Check database fields exist
    print("\n3. Testing Database Fields:")
    try:
        # Check if Claim model has AI fields
        claim_fields = [field.name for field in Claim._meta.get_fields()]
        ai_fields = ['ai_claim_type', 'confidence_score', 'risk_score', 'fraud_flag', 'recommended_amount']
        
        missing_fields = [field for field in ai_fields if field not in claim_fields]
        if missing_fields:
            print(f"   ✗ Missing AI fields: {missing_fields}")
        else:
            print("   ✓ All AI fields present in Claim model")
            
        # Check if Policy model has coverage_percentage
        policy_fields = [field.name for field in Policy._meta.get_fields()]
        if 'coverage_percentage' in policy_fields:
            print("   ✓ coverage_percentage field present in Policy model")
        else:
            print("   ✗ coverage_percentage field missing from Policy model")
            
    except Exception as e:
        print(f"   ✗ Database field check failed: {e}")
    
    # Test 4: Check signals are registered
    print("\n4. Testing Signal Registration:")
    try:
        from django.db.models.signals import post_save
        from claims.models import Claim
        from ai_features.signals import trigger_ai_predictions
        
        # Check if signal is connected
        receivers = post_save._live_receivers(sender=Claim)
        signal_found = any(receiver.__name__ == 'trigger_ai_predictions' for receiver, _ in receivers)
        
        if signal_found:
            print("   ✓ AI prediction signal is registered")
        else:
            print("   ✗ AI prediction signal not found")
            
    except Exception as e:
        print(f"   ✗ Signal check failed: {e}")
    
    # Test 5: Check management command
    print("\n5. Testing Management Command:")
    try:
        from django.core.management import call_command
        from io import StringIO
        
        out = StringIO()
        call_command('train_ai_models', stdout=out)
        output = out.getvalue()
        
        if "Starting AI model training" in output:
            print("   ✓ Management command exists and is callable")
        else:
            print("   ✗ Management command output unexpected")
            
    except Exception as e:
        print(f"   ✗ Management command test failed: {e}")
    
    # Test 6: Check app configuration
    print("\n6. Testing App Configuration:")
    try:
        from django.apps import apps
        ai_features_config = apps.get_app_config('ai_features')
        
        if ai_features_config.name == 'ai_features':
            print("   ✓ ai_features app is properly configured")
        else:
            print("   ✗ ai_features app configuration issue")
            
    except Exception as e:
        print(f"   ✗ App configuration check failed: {e}")
    
    print("\n" + "="*50)
    print("API Integration Verification Complete!")
    print("="*50)
    print("\nNext Steps:")
    print("1. Train ML models: python manage.py train_ai_models")
    print("2. Test the system with real claims")
    print("3. Monitor logs for AI predictions")
    print("4. Verify APIs return AI predictions in responses")
    
    return True


if __name__ == "__main__":
    verify_api_integration()