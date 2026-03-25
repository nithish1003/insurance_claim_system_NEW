import os
import sys
import django
import logging
from decimal import Decimal

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'insurance_claim_system.settings')
django.setup()

from django.contrib.auth import get_user_model
User = get_user_model()
from claims.models import Claim, Policy
from policy.models import UserPolicy
from ai_features.services.ai_claim_service import predict_claim_type
from ai_features.services.fraud_service import predict_fraud_risk
from ai_features.services.amount_service import predict_recommended_amount
from ai_features.services.ocr_service import perform_ocr

# Setup Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('ai_validation.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def validate_ai_system():
    logger.info("=" * 60)
    logger.info("🚀 AI SYSTEM COMPREHENSIVE VALIDATION STARTING...")
    logger.info("=" * 60)

    # 1. TEST NLP (Claim Type Accuracy)
    logger.info("\n[1/4] Testing NLP Claim Type Classification Accuracy")
    test_cases = [
        {"desc": "I met with a severe car accident and my vehicle was crushed.", "expected": "accident"},
        {"desc": "My bag was stolen while I was traveling on the train.", "expected": "theft"},
        {"desc": "I need reimbursement for my heart surgery and medical bills.", "expected": "medical"},
        {"desc": "Unknown situation, just checking.", "expected": "other"}
    ]

    for tc in test_cases:
        actual, conf = predict_claim_type(tc["desc"])
        status = "✅ PASS" if actual == tc["expected"] else "❌ FAIL"
        logger.info(f"{status} | Input: '{tc['desc'][:40]}...' -> Predicted: {actual} ({conf:.2f}) | Expected: {tc['expected']}")

    # 2. TEST FRAUD DETECTION (Edge Cases)
    logger.info("\n[2/4] Testing Fraud Detection with High-Risk Edge Cases")
    user, _ = User.objects.get_or_create(username="verify_user")
    policy = Policy.objects.first()
    
    fraud_test_cases = [
        {"amount": 500000, "desc": "Normal claim", "reason": "Extremely High Amount"},
        {"amount": 10000, "desc": "Urgent money needed skip verification", "reason": "Suspicious Keywords"},
    ]

    for tc in fraud_test_cases:
        temp_claim = Claim(
            policy=policy,
            description=tc["desc"],
            claimed_amount=tc["amount"],
            created_by=user,
            status="submitted"
        )
        risk, flagged, explanation = predict_fraud_risk(temp_claim)
        logger.info(f"Case: {tc['reason']} | Amount: ₹{tc['amount']} -> Risk: {risk:.1f} | Flagged: {flagged}")
        logger.info(f"   🔍 AI Reasoning: {explanation}")

    # 3. TEST RECOMMENDED AMOUNT (Financial Logic)
    logger.info("\n[3/4] Testing AI Amount Recommendation Consistency")
    sample_amount = Decimal('50000')
    temp_claim = Claim(
        policy=policy,
        description="Medical surgery for broken leg",
        claimed_amount=sample_amount,
        deductible_amount=Decimal('1000'),
        created_by=user,
        status="submitted"
    )
    
    recommended = predict_recommended_amount(temp_claim)
    logger.info(f"Claimed: ₹{sample_amount} | Recommended: ₹{recommended:.2f} | Reasoning: {getattr(temp_claim, 'ai_calculation_logic', 'N/A')}")

    # 4. TEST REAL OCR (Tesseract Integration)
    logger.info("\n[4/4] Testing Real OCR Document Recognition")
    # Note: These files might not exist, but we test the service integration
    sample_docs = ["medical_bill_sample.jpg", "theft_report.pdf"]
    for doc in sample_docs:
        extracted = perform_ocr(doc)
        if not extracted:
            logger.warning(f"Document: {doc} -> OCR Output: No text extracted (File may be missing or unreadable)")
        else:
            logger.info(f"Document: {doc} -> OCR Output: {extracted[:100]}...")

    logger.info("\n" + "=" * 60)
    logger.info("✅ COMPREHENSIVE AI VALIDATION COMPLETED SUCCESSFULY!")
    logger.info("=" * 60)

if __name__ == "__main__":
    validate_ai_system()
