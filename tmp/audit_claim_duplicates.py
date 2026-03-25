import sys
import os
import django
from decimal import Decimal
from datetime import timedelta

# Add project root to sys.path
PROJECT_ROOT = r'd:\insurance_claim_system_NEW'
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'insurance_claim_system.settings')
django.setup()

from claims.models import Claim

def cleanup_claim_duplicates():
    print("--- STARTING CLAIM REDUNDANCY AUDIT ---")
    all_claims = Claim.objects.all().order_by('incident_date')
    
    seen_groups = []
    
    for claim in all_claims:
        found_group = False
        for group in seen_groups:
            # Check if it fits an existing "incident group"
            # (Same policy, same amount, and within 10 days of another claim in the group)
            ref = group[0]
            if (claim.policy_id == ref.policy_id and 
                abs(claim.claimed_amount - ref.claimed_amount) < Decimal('0.01')):
                
                # Check date proximity to ANY item in the group
                time_diff = min([abs((claim.incident_date - item.incident_date).days) for item in group])
                if time_diff <= 10:
                    group.append(claim)
                    found_group = True
                    break
        
        if not found_group:
            seen_groups.append([claim])
            
    # Process groups with > 1 claim
    redundant_ids = []
    for group in seen_groups:
        if len(group) > 1:
            print(f"\n[POTENTIAL REDUNDANCY GROUP - {group[0].policy.policy_number} - ₹{group[0].claimed_amount}]")
            # Sort by created_at to keep the latest one (or the one with the most data if we could check)
            group.sort(key=lambda x: x.created_at, reverse=True)
            keep = group[0]
            others = group[1:]
            
            print(f"  KEEP:   ID: {keep.id} | CLAIM: {keep.claim_number} | INCIDENT: {keep.incident_date} | STATUS: {keep.status}")
            for other in others:
                print(f"  REMOVE: ID: {other.id} | CLAIM: {other.claim_number} | INCIDENT: {other.incident_date} | STATUS: {other.status}")
                redundant_ids.append(other.id)
                
    if redundant_ids:
        print(f"\nFound {len(redundant_ids)} redundant records.")
        # Perform deletion
        Claim.objects.filter(id__in=redundant_ids).delete()
        print("Execution: Redundant claims have been purged.")
    else:
        print("\nNo certain redundancies found with 10-day window.")

if __name__ == "__main__":
    cleanup_claim_duplicates()
