import logging

logger = logging.getLogger(__name__)

class DeterministicAdminNoteGenerator:
    """
    Intelligent Audit Note Generator with Validation & Normalization Layer.
    Ensures that every decision is logically derived before note generation.
    """

    def generate(self, raw_data: dict) -> str:
        """
        Main execution pipeline: Sanitize -> Normalize -> Generate.
        NEVER generates notes directly from raw input.
        """
        sanitized = self._sanitize_data(raw_data)
        decision = self._normalize_decision(sanitized)
        return self._build_note_from_decision(decision, sanitized)

    def _sanitize_data(self, data: dict) -> dict:
        """Step 2: Sanitization & Flagging (MANDATORY)."""
        return {
            "risk_score": round(data.get("risk_score", 0.0), 3),
            "fraud": data.get("fraud_flag"),
            "doc_valid": data.get("document_status") == "VERIFIED",
            "doc_status": data.get("document_status", "UNVERIFIED"),
            "verif_passed": data.get("verification_status") == "PASSED",
            "identity_passed": data.get("identity_status", "PASSED") == "PASSED"
        }

    def _normalize_decision(self, s: dict) -> str:
        """Step 3: Decision Normalization (CORE LOGIC)."""
        if s["fraud"]:
             return "INVESTIGATION"
        
        if s["doc_status"] == "INVALID":
             return "REJECTED"
        
        if s["doc_status"] == "UNVERIFIED":
             return "CONDITIONAL_APPROVAL"
        
        if s["verif_passed"] and s["risk_score"] < 0.1:
             return "APPROVED"
        
        if s["risk_score"] >= 0.3:
             return "ON_HOLD"
             
        return "REVIEW"

    def _build_note_from_decision(self, decision: str, s: dict) -> str:
        """Step 5: Note Generation (Based on Decision ONLY)."""
        risk = s["risk_score"]
        
        if decision == "INVESTIGATION":
            return (
                f"The application has been flagged for potential irregularities ({s['fraud']}). "
                f"Verification inconsistencies have been identified, and the case requires detailed investigation. "
                f"Processing has been suspended pending audit review."
            )

        if decision == "REJECTED":
            return (
                f"Application review identified critical issues in verification and/or documentation. "
                f"The AI risk score ({risk}) and validation checks do not meet underwriting criteria. "
                f"The application has been rejected as per policy guidelines."
            )

        if decision == "CONDITIONAL_APPROVAL":
            return (
                f"Policy application has been reviewed. Identity verification has been completed; however, "
                f"supporting documents are pending verification. AI-based risk assessment indicates a low "
                f"risk score ({risk}). Approval is granted conditionally, subject to final document validation."
            )

        if decision == "APPROVED":
            return (
                f"Policy application has been successfully verified. All submitted documents are valid and consistent "
                f"with the provided identity information. AI-based risk assessment indicates a low risk score ({risk}), "
                f"which falls within acceptable underwriting limits. The policy is approved and activated as per standard terms."
            )

        if decision == "ON_HOLD" or decision == "REVIEW":
            return (
                f"The application is currently under review due to pending validation requirements. While initial checks "
                f"are complete, additional verification is required. The AI risk score ({risk}) indicates moderate risk. "
                f"The case is placed on hold."
            )

        return "Internal state error: Decision could not be determined."

# Singleton instance for service usage
admin_note_engine = DeterministicAdminNoteGenerator()
