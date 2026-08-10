import os
import sys
import django

# Setup Django settings
sys.path.append(os.getcwd())
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'insurance_claim_system.settings')
django.setup()

from claims.models import Claim

def main():
    claims = Claim.objects.all().order_by('-id')
    print(f"Total Claims in DB: {claims.count()}")
    
    print("\nLast 10 claims:")
    for c in claims[:10]:
        print(f"ID: {c.id}")
        print(f"  Claim Identifier: {c.claim_number}")
        print(f"  Description: '{c.description[:80]}...'")
        print(f"  Claim Type (User Entered / Policy): {c.claim_type}")
        print(f"  AI Claim Type: {c.ai_claim_type}")
        print(f"  Final Claim Type: {c.final_claim_type}")
        print(f"  Confidence Score: {c.confidence_score}")
        print(f"  Status: {c.status}")
        print(f"  Triage Status: {c.triage_status if hasattr(c, 'triage_status') else 'N/A'}")
        print("-" * 40)

if __name__ == '__main__':
    main()
