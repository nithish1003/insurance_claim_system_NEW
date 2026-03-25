import os
import django
import sys
from decimal import Decimal

# Setup Django
sys.path.append(os.getcwd())
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'insurance_claim_system.settings')
django.setup()

from claims.models import Claim
from policy.models import UserPolicy, Policy
from ai_features.services.amount_service import predict_recommended_amount

def test_ai_recommendation():
    print("🧪 Testing Advanced AI Payout Model...")
    
    # 1. Get a sample claim or create one
    claim = Claim.objects.first()
    if not claim:
        print("❌ No claims found in database to test.")
        return

    # 2. Inject realistic domain data for a "Network Hospital" scenario
    claim.patient_age = 45
    claim.hospital_type = 'network'
    claim.admission_days = 5
    claim.diagnosis_severity = 4
    claim.number_of_tests = 8
    claim.medication_cost = Decimal('25000.00')
    claim.room_rent_cost = Decimal('15000.00')
    claim.claimed_amount = Decimal('120000.00')
    claim.deductible_amount = Decimal('5000.00')
    claim.save()

    print(f"\n📝 Claim Scenario:")
    print(f"   - Claimed Amount: ₹{claim.claimed_amount:,.2f}")
    print(f"   - Hospital: {claim.hospital_type.title()}")
    print(f"   - Severity: {claim.diagnosis_severity}/5")
    print(f"   - Age: {claim.patient_age}")

    # 3. Run Prediction
    try:
        # Set status to something non-draft to simulate realistic claim
        claim.status = 'submitted'
        claim.save()
        
        print("   - Calling AI Prediction Service...")
        prediction = predict_recommended_amount(claim)
        
        # Save updates to AI fields made in-memory by the service
        claim.save()
        
        # Now refresh to see what's in DB
        claim.refresh_from_db()
    except Exception as e:
        import traceback
        print(f"❌ Prediction Failed: {e}")
        traceback.print_exc()
        return

    print(f"\n🤖 AI RESULTS:")
    print(f"   - Recommended Amount: ₹{prediction:,.2f}")
    print(f"   - Confidence Score: {claim.confidence_score:.1f}%")
    print(f"   - Adjustment Factor: {claim.ai_adjustment_factor*100:.1f}%")
    
    print(f"\n🔍 EXPLAINABILITY (SHAP Trace):")
    for part in claim.ai_calculation_logic.split(' | '):
        print(f"   - {part}")

if __name__ == "__main__":
    test_ai_recommendation()
