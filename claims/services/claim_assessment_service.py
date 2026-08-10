from decimal import Decimal
from django.utils import timezone
from .claim_payout_service import ClaimPayoutService

class ClaimAssessmentService:
    """
    Service layer for claim financial assessment and logic hardening.
    Explicitly handles net claimable calculations and AI recommendation triggers.
    """

    @staticmethod
    def evaluate(claim):
        """
        Hardened assessment logic called during model save or explicit audit.
        
        1. Synchronizes net_claimable (claimed - deductible)
        2. Ensures authoritative AI recommendation is populated
        3. Validates financial integrity
        """
        # 🛡️ 1. Core Financial Sync (Net Claimable)
        claimed = Decimal(str(claim.claimed_amount or 0))
        deductible = Decimal(str(claim.deductible_amount or 0))
        claim.net_claimable = max(Decimal('0'), claimed - deductible)

        # 🛡️ 2. Default Initial Prediction (if missing)
        # If this is a fresh submission and we don't have a prediction yet,
        # we compute it using the current engine.
        if not claim.initial_ai_prediction:
            computed = ClaimPayoutService.get_authoritative_payout(claim)
            claim.initial_ai_prediction = computed
            
        # 🛡️ 3. Authoritative Recommendation Sync
        # Ensure final_ai_recommendation is at least as fresh as the initial one
        if not claim.final_ai_recommendation:
            claim.final_ai_recommendation = claim.initial_ai_prediction
            claim.ai_engine_version = "v2.0-auto"
            claim.prediction_generated_at = timezone.now()

        return claim
