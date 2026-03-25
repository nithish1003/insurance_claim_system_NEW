import os
import django
import sys

# Setup Django
sys.path.append(os.getcwd())
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'insurance_claim_system.settings')
django.setup()

from claims.models import Claim
from django.db.models import Count, Sum

def test_reports_logic():
    print("🧪 Testing Reports Analytics Queries...")
    
    try:
        # 1. Status Counts
        print("   - Fetching Status Counts...")
        status_counts = Claim.objects.values('status').annotate(total=Count('id'))
        print(f"     ✅ Found {len(status_counts)} status categories.")
        
        # 2. Financials
        print("   - Fetching Financial Summary...")
        results = Claim.objects.aggregate(t=Sum('claimed_amount')) # Simple version
        print(f"     ✅ Total Claimed: {results['t']}")
        
        # 3. High Value
        print("   - Fetching High Value Claims...")
        high_value = Claim.objects.filter(claimed_amount__gt=500000).order_by('-claimed_amount')[:5]
        print(f"     ✅ Fetched {high_value.count()} high value claims.")
        
        # 4. Attempting to select ALL fields (like select_related case)
        print("   - Attempting full table fetch (Select *)...")
        sample_claim = Claim.objects.first()
        if sample_claim:
             print(f"     ✅ Claim #ID={sample_claim.id}: Age={sample_claim.patient_age}")
             
        print("\n🎉 ALL QUERIES PASSED IN SHELL!")
    except Exception as e:
        print(f"\n❌ FAILED: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_reports_logic()
