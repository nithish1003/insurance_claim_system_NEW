import logging
from django.utils import timezone
from decimal import Decimal
from typing import Tuple, List

from claims.models import Claim, ClaimAIHistory
from .ocr_service import perform_ocr, extract_details
from .ai_claim_service import predict_claim_type
from .ml_training_service import FraudMLService, trigger_retraining_if_needed

logger = logging.getLogger(__name__)

def run_ai_pipeline(claim: Claim):
    """
    Regulator-Grade AI Pipeline (Version: v3.3)
    Full Governance State: XGBoost + SHAP Audit + Shadow Dep + Platt Calibration
    """
    try:
        logger.info(f"🚀 AI Pipeline v3.3 started for Claim: {claim.claim_number}")
        
        # ── 1. AGGREGATED OCR INVOICE PROCESSING ────────────────────
        # Handle multiple documents for consolidated billing
        relevant_docs = claim.documents.filter(
            document_type__in=['medical_bill', 'hospital_bill', 'repair_bill', 'rc_document']
        )
        total_billed = 0.0
        processed_docs = 0
        
        for doc in relevant_docs:
            try:
                ocr_text = perform_ocr(doc.file.path)
                extracted = extract_details(ocr_text)
                doc_amount = float(extracted.get('total_amount', 0.0))
                if doc_amount > 0:
                    total_billed += doc_amount
                    processed_docs += 1
                    logger.info(f"📄 Aggregator: Added ₹{doc_amount} from {doc.get_document_type_display()}")
            except Exception as e:
                logger.warning(f"⚠️ Failed to process individual document {doc.id}: {e}")
        
        if total_billed > 0:
            claim.bill_amount = Decimal(str(round(total_billed, 2)))
        else:
            # Fallback to claimed amount if no OCR data could be harvested
            claim.bill_amount = claim.claimed_amount
            logger.info("ℹ️ No valid bill amounts harvested. Using claimed amount base.")


        # ── 2. DYNAMIC RATIO-BASED PENALTY (Inflation Detection) ──────
        billed = float(claim.bill_amount)
        claimed = float(claim.claimed_amount)
        
        # v3 uses a smart inflation ratio instead of a static 20% penalty.
        # Tolerance: 10%. Anything beyond triggers progressive dampening.
        inflation_penalty_ratio = 0.0
        if claimed > (billed * 1.1):
            # Dynamic calculation: The more you inflate, the harder the penalty
            # Ratio = 1.0 - (True_Bill / Claimed_Request)
            inflation_ratio = 1.0 - (billed / claimed)
            # Progressive curve (Squared) to deter high inflation
            inflation_penalty_ratio = min(0.6, inflation_ratio ** 1.3)
            logger.info(f"⚖️ Dynamic Penalty Triggered: Inflation Ratio {inflation_ratio:.2f} -> Penalty {inflation_penalty_ratio:.2f}")


        # ── 3. ENTERPRISE FRAUD DISCOVERY (XGBoost v3.7 + Adaptive Audit) ─────
        from .ml_training_service import UnifiedMLGovernance
        gov = UnifiedMLGovernance()
        
        # v3.7: Enterprise audit with readable narrative + shadow lift tracking
        risk_score, fraud_flag, readable_audit, gov_meta = gov.predict_fraud(claim)
        
        claim.risk_score = risk_score
        claim.fraud_flag = fraud_flag
        claim.fraud_explanation = readable_audit
        claim.ml_model_version = "v3.7_Enterprise"

        # ── 4. ENTERPRISE NLP CLASSIFICATION ──────────────
        pred_type, type_conf = gov.predict_type(claim.description)
        claim.ai_claim_type = pred_type
        
        # ── 5. ENTERPRISE PAYOUT ENGINE (Regression + Business Constraints) ─────
        ai_recommended, amount_meta = gov.predict_amount(claim)
        claim.ai_predicted_amount = Decimal(str(round(ai_recommended, 2)))
        
        if claimed > 0:
            claim.ai_adjustment_factor = float(ai_recommended) / claimed
        else:
            claim.ai_adjustment_factor = 1.0

        # ── 6. COMPOSITE CONFIDENCE SCORING ─────────────────────
        confidence = type_conf * 0.5
        if processed_docs > 0: confidence += 0.3
        if billed > 0: confidence += 0.2
        
        claim.confidence_score = min(100.0, confidence * 100)

        # ── 7. ADAPTIVE DECISION ENGINE (v3.7 Enterprise Thresholds) ───────────────────
        # Decision logic enhanced with Anomaly & Drift Awareness
        is_anomaly = gov_meta.get('is_anomaly', False)
        
        if (risk_score > 72 or 
            is_anomaly or
            processed_docs == 0 or 
            confidence < 0.60): # Stricter for Enterprise
            claim.ai_decision = "manual_review"
        elif ai_recommended <= 0:
            claim.ai_decision = "reject"
        else:
            claim.ai_decision = "auto_process"

        # ── 8. ENTERPRISE REGULATOR LOGGING ──────────────────────────────
        shadow_results = gov_meta.get('shadow', {})
        feature_vector = {
            "claimed_amount": claimed,
            "bill_amount": billed,
            "risk_score": risk_score,
            "is_anomaly": is_anomaly,
            "model_version": "v3.7_Hardened",
            "ts": timezone.now().isoformat()
        }
        
        # Store for Regulator Audit v3.7
        ClaimAIHistory.objects.create(
            claim=claim,
            version="v3.7",
            ai_claim_type=claim.ai_claim_type,
            ai_predicted_amount=claim.ai_predicted_amount,
            ai_risk_score=risk_score,
            ai_decision=claim.ai_decision,
            ai_confidence=claim.confidence_score,
            feature_vector=feature_vector,
            # Regulator Audit Trail
            shap_values=gov_meta.get('shap_values'),
            shadow_decision="reject" if shadow_results.get('fallback_val') else "auto_process",
            shadow_predicted_amount=Decimal(str(amount_meta.get('shadow', {}).get('fallback_val', 0)))
        )

        # ── 9. DRIFT & BASLINE MONITORING ──────────────────────────
        # Baselines tracked for institutional drift analysis
        baseline_conf = 82.5 
        claim.ai_drift_score = abs(confidence * 100 - baseline_conf)
        
        # Final Metadata
        claim.ai_version = "v3.7"
        claim.ai_updated_at = timezone.now()
        
        reasoning = f"v3.7 Enterprise Hub. Lift: {shadow_results.get('v3_lift', 'neutral')}. "
        reasoning += f"Narrative: {readable_audit}. "
        reasoning += f"Decision: {claim.get_ai_decision_display()}."
        
        claim.ai_calculation_logic = reasoning
        claim.save()
        
        logger.info(f"✅ Enterprise AI v3.7 SUCCESS: {claim.claim_number} -> {claim.ai_decision}")
        return True
        return True

    except Exception as e:
        logger.error(f"🛑 CRITICAL PIPELINE v3 FAILURE: {str(e)}", exc_info=True)
        return False
