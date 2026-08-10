import logging
from django.utils import timezone
from decimal import Decimal

logger = logging.getLogger(__name__)

class DecisionOrchestrator:
    """
    Requirement Phase 4: Decision Orchestration Engine.
    Replaces simple thresholds with a complex rule-based triage system.
    """

    @staticmethod
    def orchestrate(claim, audit_data):
        """
        Main entry point for decision logic.
        Analyzes multi-dimensional risk scores and governs the final triage status.
        """
        risk_analysis = audit_data.get("risk_analysis", {})
        fraud_risk = risk_analysis.get("fraud_risk", 0.0)
        leakage_risk = risk_analysis.get("leakage_risk", 0.0)
        doc_risk = risk_analysis.get("doc_risk", 0.0)
        uncertainty = risk_analysis.get("uncertainty", 0.0)
        
        governance = audit_data.get("governance", {})
        fraud_flag = governance.get("fraud_flag", False)
        
        # 1. Hard Rules (Phase 5: Fraud Network & Blacklists)
        blacklisted_hit = governance.get("blacklisted_entity", False)
        duplicate_docs = governance.get("duplicate_docs_detected", False)
        identity_mismatch = governance.get("identity_mismatch", False)
        
        # ── STATUS TRIAGE GOVERNANCE ──────────────────────────────────────
        # Requirement: Do not downgrade a dossier that has already passed 
        # initial staff audit (SSoT: Human judgment takes precedence).
        POST_STAFF_REVIEW_STATES = ['staff_reviewed', 'approved', 'rejected', 'settled', 'closed']
        
        if claim.status not in POST_STAFF_REVIEW_STATES:
            # ── INVESTIGATION TRIGGER 🚨 ──────────────────────────────────────
            if (fraud_risk > 0.45 or 
                fraud_flag or 
                blacklisted_hit or 
                duplicate_docs or 
                identity_mismatch):
                
                claim.decision_engine_verdict = "investigation"
                claim.status = "investigation"
                reason = []
                if fraud_risk > 0.45: reason.append(f"High Fraud Risk ({fraud_risk})")
                if duplicate_docs: reason.append("Duplicate Document Hash detected")
                if identity_mismatch: reason.append("Aadhaar/Identity Mismatch")
                if blacklisted_hit: reason.append("Blacklisted Provider Hit")
                
                # Phase 6: Life Insurance Early Death escalation
                if claim.claim_type == 'death' and governance.get('early_death_claim'):
                    reason.append("Early Death Claim Escalation")
                
                claim.priority_level = "critical"
                claim.priority_reason = " | ".join(reason) if reason else "General Investigation Flag"
                
            # ── AUTO APPROVAL PATHWAY ✅ ──────────────────────────────────────
            elif (fraud_risk < 0.08 and 
                doc_risk < 0.10 and 
                uncertainty < 0.15 and 
                leakage_risk < 0.20):
                
                claim.decision_engine_verdict = "auto_approve"
                # We don't auto-set status to 'approved' here; 
                # we let the service layer decide based on business rules.
                claim.priority_level = "low"
                claim.priority_reason = "Low risk multi-factor assessment. Eligible for Green Channel."

            # ── MANUAL REVIEW 🔍 ──────────────────────────────────────────────
            else:
                claim.decision_engine_verdict = "manual_review"
                claim.status = "under_review"
                claim.priority_level = "medium"
                claim.priority_reason = "Risk profiles in medium band. Requires human audit."
        else:
            # Even if we don't change status, we still update the verdict for analytics
            if fraud_risk > 0.45:
                claim.decision_engine_verdict = "investigation"
            elif (fraud_risk < 0.08 and doc_risk < 0.10):
                claim.decision_engine_verdict = "auto_approve"
            else:
                claim.decision_engine_verdict = "manual_review"

        claim.decision_orchestration_at = timezone.now()
        return claim
