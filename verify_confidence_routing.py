import os
import sys
import django
import logging

# Setup Django
sys.path.append(os.getcwd())
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'insurance_claim_system.settings')
django.setup()

from ai_features.services.ai_claim_service import predict_claim_type

# Set logging to see the output
logging.basicConfig(level=logging.INFO)

def test_confidence_routing():
    test_cases = [
        "I was in a car accident on the highway", # High confidence accident
        "Hospital bill for surgery",             # High confidence medical
        "I lost my bag yesterday",               # Maybe low confidence
        "Something happened at my place",        # Very low confidence / ambiguous
    ]
    
    print("\n--- Testing Confidence-Based Routing (Threshold: 0.6) ---")
    for desc in test_cases:
        label, conf = predict_claim_type(desc)
        status = "✅ ACCEPTED" if label != "manual_review" else "⚠️ MANUAL REVIEW"
        print(f"Description: '{desc}'")
        print(f"Prediction: {label} | Confidence: {conf:.4f} | Status: {status}")
        print("-" * 50)

if __name__ == "__main__":
    test_confidence_routing()
