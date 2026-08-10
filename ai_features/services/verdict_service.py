import logging

logger = logging.getLogger(__name__)

def generate_admin_note(data):
    """
    Generates professional, audit-ready admin verdict notes based on AI risk assessment
    and identity verification status.
    
    Rules:
    - Never call documents valid if UNVERIFIED.
    - Mention passed checks if VERIFIED.
    - Professional underwriting tone.
    - Append clear recommended action.
    """
    decision = data.get("decision", "ON_HOLD").upper()
    risk = data.get("risk_score", 0.0)
    verif = data.get("verification_status", "PENDING").upper()
    doc_status = data.get("document_status", "UNVERIFIED").upper()
    fraud = data.get("fraud_flag", False)

    try:
        remarks = []
        
        # 1. Identity Verification Context
        if verif == "PASSED" or verif == "VERIFIED":
            remarks.append(f"Identity verification has successfully PASSED system checks.")
        else:
            remarks.append(f"Identity verification is currently {verif}; pending final bio-metric confirmation.")

        # 2. Document Integrity Context
        if doc_status == "VALID" or doc_status == "PASSED":
            remarks.append(f"Submitted documentation is validated and consistent with policy requirements.")
        else:
            remarks.append(f"Primary documentation remains {doc_status}; further forensic review of uploaded attachments is required.")

        # 3. Risk Intelligence
        risk_level = "LOW" if risk < 0.15 else "MODERATE" if risk < 0.3 else "HIGH"
        remarks.append(f"AI Risk Engine reports a {risk_level} score ({risk:.2f}).")
        
        if fraud:
            remarks.append("CRITICAL: High-confidence fraud indicators detected in submission pattern.")

        # 4. Synthesize Final Professional Note
        final_note = " ".join(remarks)
        
        # 5. Append Recommended Action
        recommended_action = "HOLD"
        if decision == "APPROVED" and doc_status == "VALID" and risk < 0.2:
            recommended_action = "APPROVE & ACTIVATE"
        elif decision == "REJECTED" or risk > 0.4 or fraud:
            recommended_action = "REJECT"
        elif doc_status == "UNVERIFIED":
            recommended_action = "REQUEST DOCUMENTS"

        return f"{final_note}\n\nRECOMMENDED ACTION: {recommended_action}"

    except Exception as e:
        logger.error(f"Error generating verdict note: {str(e)}")
        return f"Decision: {decision}. Risk Score: {risk:.2f}. Manual audit required due to generation error.\n\nRECOMMENDED ACTION: HOLD"
