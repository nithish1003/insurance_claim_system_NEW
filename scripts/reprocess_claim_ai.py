import sys
import os
import django
from decimal import Decimal

# Setup Django
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'insurance_claim_system.settings')
django.setup()

from claims.models import Claim
from claims.ai_calculation_engine import AICalculationEngine

def reprocess_claim(public_id):
    try:
        claim = Claim.objects.get(public_id=public_id)
        print(f"[PROCESS] Reprocessing Claim: {claim.claim_number}")
        
        # Manually run the engine
        engine = AICalculationEngine(claim)
        audit = engine.get_audit_trail()
        
        print("\nGOVERNANCE DATA:")
        import pprint
        pprint.pprint(audit['governance'])
        
        # Trigger Save which will run the AI Calculation Engine again (internal)
        claim.save()
        
        # Refresh from DB
        claim.refresh_from_db()
        print(f"\n[FINAL DB STATE] Bill Amount: {claim.bill_amount}")
        
    except Claim.DoesNotExist:
        print(f"[ERROR] Claim {public_id} not found.")
    except Exception as e:
        print(f"[ERROR] Logic Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    if len(sys.argv) > 1:
        reprocess_claim(sys.argv[1])
    else:
        # Default to the one the provided in the error log
        reprocess_claim("32083357-dee6-469e-9cb6-c078e7812a14")
