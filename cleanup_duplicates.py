#!/usr/bin/env python
"""
Cleanup script to remove duplicate policy and claim records from the database.
This script should be run after implementing the duplicate prevention measures.
"""

import os
import sys
import django

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'insurance_claim_system.settings')
django.setup()

from django.db import transaction
from django.db.models import Count, Min
from policy.models import UserPolicy, PolicyApplication
from claims.models import Claim


def cleanup_user_policy_duplicates():
    """Remove duplicate UserPolicy records, keeping the most recent one."""
    print("Cleaning up UserPolicy duplicates...")
    
    # Find duplicates based on user + policy combination
    duplicates = UserPolicy.objects.values('user', 'policy').annotate(
        count=Count('id'),
        min_id=Min('id')
    ).filter(count__gt=1)
    
    total_removed = 0
    
    for duplicate in duplicates:
        user_id = duplicate['user']
        policy_id = duplicate['policy']
        min_id = duplicate['min_id']
        
        # Get all records except the first one (keep the oldest/first created)
        duplicate_records = UserPolicy.objects.filter(
            user_id=user_id, 
            policy_id=policy_id
        ).exclude(id=min_id)
        
        count = duplicate_records.count()
        if count > 0:
            print(f"  Removing {count} duplicate UserPolicy records for user {user_id}, policy {policy_id}")
            duplicate_records.delete()
            total_removed += count
    
    print(f"Total UserPolicy duplicates removed: {total_removed}")
    return total_removed


def cleanup_policy_application_duplicates():
    """Remove duplicate PolicyApplication records, keeping the most recent one."""
    print("Cleaning up PolicyApplication duplicates...")
    
    # Find duplicates based on user + policy combination
    duplicates = PolicyApplication.objects.values('user', 'policy').annotate(
        count=Count('id'),
        min_id=Min('id')
    ).filter(count__gt=1)
    
    total_removed = 0
    
    for duplicate in duplicates:
        user_id = duplicate['user']
        policy_id = duplicate['policy']
        min_id = duplicate['min_id']
        
        # Get all records except the first one (keep the oldest/first created)
        duplicate_records = PolicyApplication.objects.filter(
            user_id=user_id, 
            policy_id=policy_id
        ).exclude(id=min_id)
        
        count = duplicate_records.count()
        if count > 0:
            print(f"  Removing {count} duplicate PolicyApplication records for user {user_id}, policy {policy_id}")
            duplicate_records.delete()
            total_removed += count
    
    print(f"Total PolicyApplication duplicates removed: {total_removed}")
    return total_removed


def cleanup_claim_duplicates():
    """Remove duplicate Claim records based on claim_number."""
    print("Cleaning up Claim duplicates...")
    
    # Find duplicates based on claim_number
    duplicates = Claim.objects.values('claim_number').annotate(
        count=Count('id'),
        min_id=Min('id')
    ).filter(count__gt=1)
    
    total_removed = 0
    
    for duplicate in duplicates:
        claim_number = duplicate['claim_number']
        min_id = duplicate['min_id']
        
        # Get all records except the first one (keep the oldest/first created)
        duplicate_records = Claim.objects.filter(claim_number=claim_number).exclude(id=min_id)
        
        count = duplicate_records.count()
        if count > 0:
            print(f"  Removing {count} duplicate Claim records for claim number {claim_number}")
            duplicate_records.delete()
            total_removed += count
    
    print(f"Total Claim duplicates removed: {total_removed}")
    return total_removed


def verify_unique_constraints():
    """Verify that unique constraints are working properly."""
    print("\nVerifying unique constraints...")
    
    # Check UserPolicy uniqueness
    user_policy_duplicates = UserPolicy.objects.values('user', 'policy').annotate(
        count=Count('id')
    ).filter(count__gt=1)
    
    if user_policy_duplicates.exists():
        print("  ❌ UserPolicy duplicates still exist:")
        for dup in user_policy_duplicates:
            print(f"    User {dup['user']}, Policy {dup['policy']}: {dup['count']} records")
    else:
        print("  ✅ UserPolicy unique constraint working correctly")
    
    # Check PolicyApplication uniqueness
    app_duplicates = PolicyApplication.objects.values('user', 'policy').annotate(
        count=Count('id')
    ).filter(count__gt=1)
    
    if app_duplicates.exists():
        print("  ❌ PolicyApplication duplicates still exist:")
        for dup in app_duplicates:
            print(f"    User {dup['user']}, Policy {dup['policy']}: {dup['count']} records")
    else:
        print("  ✅ PolicyApplication unique constraint working correctly")
    
    # Check Claim uniqueness
    claim_duplicates = Claim.objects.values('claim_number').annotate(
        count=Count('id')
    ).filter(count__gt=1)
    
    if claim_duplicates.exists():
        print("  ❌ Claim duplicates still exist:")
        for dup in claim_duplicates:
            print(f"    Claim Number {dup['claim_number']}: {dup['count']} records")
    else:
        print("  ✅ Claim unique constraint working correctly")


def main():
    """Main cleanup function."""
    print("Starting duplicate record cleanup...\n")
    
    try:
        with transaction.atomic():
            total_removed = 0
            total_removed += cleanup_user_policy_duplicates()
            total_removed += cleanup_policy_application_duplicates()
            total_removed += cleanup_claim_duplicates()
            
            print(f"\nTotal records removed: {total_removed}")
            
            if total_removed > 0:
                print("\n⚠️  IMPORTANT: Remember to run this script in a transaction or backup your database first!")
                print("   These changes are now committed to the database.")
            else:
                print("\n✅ No duplicates found - database is clean!")
            
            verify_unique_constraints()
            
    except Exception as e:
        print(f"❌ Error during cleanup: {e}")
        print("Rolling back changes...")
        raise


if __name__ == "__main__":
    main()