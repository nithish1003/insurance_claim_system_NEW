import logging
from claims.models import Claim

logger = logging.getLogger(__name__)

class PrioritizationService:
    """
    Assigns urgency and importance scores to claims for admin prioritization.
    """
    
    TYPE_WEIGHTS = {
        'medical': 40,
        'accident': 30,
        'property': 20,
        'life': 35,
        # Default to 15 if not specified
    }

    @classmethod
    def calculate_priority(cls, claim: Claim) -> float:
        """
        Compute priority_score and assign priority_level based on claim metadata.
        """
        try:
            # 1. Weights from Claim Type
            # Use AI predicted type if available, else standard type
            ctype = (claim.ai_claim_type or claim.claim_type or 'other').lower()
            type_weight = cls.TYPE_WEIGHTS.get(ctype, 15)
            
            # 2. Input Metrics
            severity = float(claim.diagnosis_severity or 1)
            fraud_risk = float(claim.risk_score or 0)
            amount_factor = float(claim.claimed_amount or 0) / 10000.0
            emergency_bonus = 50.0 if claim.emergency_flag else 0.0
            
            # 3. Final Formula
            # priority_score = type_weight + severity + fraud_risk + (amount/10000) + (50 if emergency)
            score = type_weight + severity + fraud_risk + amount_factor + emergency_bonus
            
            claim.priority_score = round(score, 2)
            
            # 4. Assign Level
            if score > 100:
                claim.priority_level = 'HIGH'
            elif score >= 50:
                claim.priority_level = 'MEDIUM'
            else:
                claim.priority_level = 'LOW'
                
            # 5. Generate Reasoning
            severity_label = "high severity" if severity >= 4 else "normal severity"
            risk_label = "high risk" if fraud_risk > 60 else "normal risk"
            
            reason = f"{ctype.title()} claim with {severity_label} and {risk_label} level"
            if claim.emergency_flag:
                reason = "EMERGENCY: " + reason
            
            claim.priority_reason = reason[:255]
            
            logger.info(f"Prioritization for {claim.claim_number}: score={score:.2f}, level={claim.priority_level}")
            return score
            
        except Exception as e:
            logger.error(f"Error calculating priority for claim {claim.id}: {e}")
            return 0.0

def update_claim_priority(claim: Claim):
    """EntryPoint for signal or manual triggering"""
    return PrioritizationService.calculate_priority(claim)
