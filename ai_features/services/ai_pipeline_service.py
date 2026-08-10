import logging
import json
from decimal import Decimal
from django.utils import timezone
from typing import Dict, Any

from claims.models import Claim, ClaimDocument, ClaimAIHistory

from .fraud_service import FraudDetectionService
from claims.ai_calculation_engine import AICalculationEngine
from claims.utils import safe_money

logger = logging.getLogger(__name__)

class AIClaimIntelligencePipeline:
    """
    Enterprise-Grade AI Claim Intelligence Pipeline v4
    Implements 5 layers of governance (Phase 4):
    1. OCR Identity Validation
    2. Versioned Risk Scoring (Phase 1 & 2)
    3. Explainable AI & Narrative (Phase 3)
    4. Decision Orchestration Rules (Phase 4)
    5. Immutable Audit Ledger (Phase 9)
    """

    def __init__(self, claim: Claim):
        self.claim = claim
        self.engine = AICalculationEngine(claim)
        self.results = {}

    def execute(self) -> Dict[str, Any]:
        """Runs the full enterprise decision pipeline."""
        try:
            logger.info(f"🚀 Initializing Enterprise Intelligence Pipeline for {self.claim.claim_number}")

            # ── LAYER 1: IDENTITY & DOSSIER GATING ──
            # (Now handled inside get_full_decision via OCR and VerifyIdentity)
            audit_trail = self.engine.get_audit_trail()
            
            # ── LAYER 2, 3 & 4: RISK, EXPLAINABILITY & ORCHESTRATION ──
            # (Logic split across ClaimAIService and DecisionOrchestrator)
            # The get_audit_trail() call already executed the full decision cycle.
            
            self.results = audit_trail
            
            # Use version from audit_trail or engine default
            model_info = audit_trail.get('model_info', {})
            self.results['model_version'] = model_info.get('version', 'v3.6-Certified-Ratios')
            
            # ── LAYER 5: IMMUTABLE AUDIT LEDGERING (Phase 9) ──
            self._persist_results(self.results)
            
            logger.info(f"✅ Enterprise Intelligence successful for {self.claim.claim_number}")
            return self.results

        except Exception as e:
            logger.error(f"🛑 Critical Pipeline Failure: {str(e)}", exc_info=True)
            return {"error": "SYSTEM_CRASH", "message": str(e)}

    def _persist_results(self, res: dict):
        """
        Hardened persistence with Immutable Ledger support (Phase 9).
        """
        from claims.models import ImmutableAuditLedger, ClaimModelVersion
        
        previous = self.claim.final_ai_recommendation
        
        # 1. Update Claim with AI Data
        self.claim.risk_score = res['risk_analysis']['risk_score'] * 100
        self.claim.fraud_probability = res['risk_analysis']['multi_risk']['fraud_risk']
        
        # Phase 1: Multi-Risk
        multi = res['risk_analysis']['multi_risk']
        self.claim.fraud_risk_score = multi['fraud_risk']
        self.claim.leakage_risk_score = multi['leakage_risk']
        self.claim.documentation_risk_score = multi['doc_risk']
        self.claim.payout_uncertainty_score = multi['uncertainty']
        
        # Phase 3: Explainability
        self.claim.shap_narrative = res['explainability']['narrative']
        self.claim.top_features = res['risk_analysis']['feature_contributions']
        
        # Phase 2: Registry
        model_ver = ClaimModelVersion.objects.filter(version_id=res['model_version']).first()
        self.claim.model_version = model_ver
        
        # 2. Financial Update
        from claims.services import ClaimPayoutService
        
        # Calculate the authoritative risk amount for this probability
        # Prob (0.0801) * Baseline (32,200) = 2579.22 (if 8.01%)
        # The user's example: ₹4.76
        # We'll calculate it based on the baseline.
        basis = float(safe_money(self.claim.payout_basis_amount or self.claim.claimed_amount))
        room_excess = float(ClaimPayoutService.calculate_room_excess(self.claim))
        deductible = float(safe_money(self.claim.deductible_amount or 0))
        baseline = max(0, basis - room_excess - deductible)
        
        # Set the monetary risk reserve
        self.claim.risk_amount = Decimal(str(baseline * float(res['risk_analysis']['risk_score']))).quantize(Decimal('0.01'))
        
        # Single Source of Truth Update via Authoritative Payload
        payout_payload = ClaimPayoutService.compute_authoritative_payout(self.claim)
        
        ClaimPayoutService.record_pipeline_result(
            self.claim, 
            payout_payload, 
            res['model_version']
        )
        
        # 3. Decision Orchestration Results
        # (Already set status and priorities via DecisionOrchestrator called in Service)
        
        # 4. ⚖️ IMMUTABLE LEDGERING (Phase 9)
        prev_amt = previous
        final_amt = self.claim.final_ai_recommendation
        
        ImmutableAuditLedger.objects.create(
            claim=self.claim,
            event_type="AI_PIPELINE_FINALIZATION",
            previous_value=str(prev_amt),
            new_value=str(final_amt),
            change_reason=f"Enterprise Pipeline v4 Decision: {self.claim.ai_decision}",
            model_version=model_ver,
            shap_snapshot=self.claim.top_features,
            risk_snapshot=multi
        )

        # ── LAYER 6: AI HISTORY LEDGER (Phase 3) ──
        # Create a historical record for model retraining and audit
        ClaimAIHistory.objects.create(
            claim=self.claim,
            version=res['model_version'],
            ai_claim_type=self.claim.ai_claim_type or "unknown",
            ai_recommendation=final_amt,
            ai_risk_score=float(res['risk_analysis']['risk_score']),
            ai_decision=self.claim.ai_decision or "REVIEW",
            ai_confidence=float(self.claim.confidence_score or 0),
            shap_values=self.claim.top_features,
            feature_vector=res.get('risk_analysis', {}).get('feature_contributions', {}),
            shadow_decision=res.get('decision_engine', {}).get('shadow_verdict'),
            shadow_predicted_amount=final_amt # Simplified for now
        )

        self.claim.save()

        # 🔔 Notify Auditors
        try:
            from notifications.utils import create_notification
            from django.contrib.auth import get_user_model
            User = get_user_model()
            auditor_users = User.objects.filter(role__in=['admin', 'staff'])
            
            for auditor in auditor_users:
                verdict_str = (self.claim.decision_engine_verdict or "PENDING").upper()
                create_notification(
                    user=auditor,
                    title="Enterprise AI Audit: SUCCESS",
                    message=f"Dossier {self.claim.claim_number} audit complete. Risk: {(self.claim.risk_score or 0):.1f}%, Verdict: {verdict_str}",
                    notification_type='warning' if (self.claim.risk_score or 0) > 30 else 'info',
                    related_entity_id=self.claim.public_id
                )
        except Exception as e:
            logger.error(f"Failed to send AI audit notification: {str(e)}")

    def _exit_with_error(self, code: str, meta: dict) -> dict:
        return {
            "error": code,
            "metadata": meta,
            "status": "REJECTED_BY_AI_GOVERNANCE"
        }

def run_intelligence_pipeline(claim: Claim) -> Dict[str, Any]:
    """Entry point for the 5-layer AI Intelligence Pipeline"""
    pipeline = AIClaimIntelligencePipeline(claim)
    return pipeline.execute()
