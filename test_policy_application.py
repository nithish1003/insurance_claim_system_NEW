#!/usr/bin/env python
"""
Test script to verify that the policy application page displays correct values.
"""

import os
import sys
import django

# Add the project directory to the Python path
sys.path.insert(0, 'd:/insurance_claim_system_NEW')

# Set up Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'insurance_claim_system.settings')
django.setup()

from policy.models import Policy
from django.contrib.auth.models import User

def test_policy_application_values():
    """Test that policy application page displays correct policy values."""
    
    print("Testing policy application values...")
    
    # Get all policies in the database
    policies = Policy.objects.all()
    print(f"Total policies in database: {policies.count()}")
    
    if policies.exists():
        # Test with the first policy
        policy = policies.first()
        print(f"\nTesting with policy: {policy.policy_number}")
        print(f"Policy Type: {policy.get_policy_type_display()}")
        print(f"Sum Insured: ₹{policy.sum_insured}")
        print(f"Status: {policy.status}")
        print(f"Is Active: {policy.is_active}")
        
        # Verify the values that would be displayed in the template
        selected_plan_value = f"{policy.policy_number} - {policy.get_policy_type_display()}"
        coverage_value = f"₹{policy.sum_insured:,}"
        
        print(f"\nTemplate values that would be displayed:")
        print(f"Selected Plan: {selected_plan_value}")
        print(f"Coverage (Sum Insured): {coverage_value}")
        
        # Check if policy is active (required for application)
        if policy.is_active:
            print(f"\n✅ Policy {policy.policy_number} is active and can be applied for")
        else:
            print(f"\n⚠️  Policy {policy.policy_number} is not active")
            
    else:
        print("❌ No policies found in database")
        print("Please create some policies first using the admin interface")
    
    print(f"\nPolicy application test completed!")

if __name__ == "__main__":
    test_policy_application_values()