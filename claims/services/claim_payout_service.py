"""
ClaimPayoutService — Single Source of Truth for all payout computations.

This service replaces all scattered references to the deprecated
`claim.ai_predicted_amount` field with a clean, centralized computation
layer that enforces the authoritative display priority:

    1. human_override_amount  (manual auditor override — highest priority)
    2. final_ai_recommendation (latest pipeline/engine output)
    3. computed runtime value   (formula-based fallback)
    4. initial_ai_prediction    (frozen submission-time estimate)
"""

import logging
from decimal import Decimal, InvalidOperation
from django.utils import timezone
from claims.utils import safe_money

logger = logging.getLogger(__name__)


class ClaimPayoutService:
    """
    Centralized payout computation and persistence service.
    
    Usage:
        from claims.services import ClaimPayoutService
        
        # Get the authoritative amount for display
        amount = ClaimPayoutService.get_authoritative_payout(claim)
        
        # Record a new AI pipeline result
        ClaimPayoutService.record_pipeline_result(claim, amount, "v3.6", user=request.user)
        
        # Record a human override
        ClaimPayoutService.record_human_override(claim, amount, user, "Adjusted per medical review")
    """

    # ── CORE COMPUTATION (Regulator-Grade SSoT) ──────────────────────────

    @staticmethod
    def calculate_room_excess(claim) -> Decimal:
        """Centralized Room Rent Excess logic."""
        is_health = "health" in (claim.claim_type or "").lower() or "medical" in (claim.claim_type or "").lower()
        if not is_health:
            return Decimal('0.00')
        
        stay_days = max(1, claim.admission_days or 1)
        room_cost = safe_money(claim.room_rent_cost or 0)
        per_day_charge = room_cost / Decimal(str(stay_days))
        limit = safe_money(claim.allowed_room_rent or 0)
        
        if per_day_charge > limit and limit > 0:
            excess = (per_day_charge - limit) * Decimal(str(stay_days))
            return excess.quantize(Decimal('0.01'))
        return Decimal('0.00')

    @staticmethod
    def compute_authoritative_payout(claim) -> dict:
        """
        The SINGLE SOURCE OF TRUTH for all settlement amounts.
        No other module may compute settlement independently.
        """
        # 1. Authoritative Basis (OCR > Declared)
        verified_bill = safe_money(claim.ocr_verified_bill_total or 0)
        declared_amount = safe_money(claim.declared_claim_amount or claim.claimed_amount or 0)
        
        # 🛡️ OCR Sanity Guard: If OCR extracted amount is wildly implausible
        # (>10x the declared amount), it's almost certainly a misread
        # (e.g., chassis number, Aadhaar, claim ID parsed as monetary value).
        if verified_bill > 0 and declared_amount > 0:
            if verified_bill > declared_amount * 10:
                import logging
                logger = logging.getLogger(__name__)
                logger.warning(
                    f"⚠️ OCR amount ₹{verified_bill:,.2f} exceeds 10x declared ₹{declared_amount:,.2f}. "
                    f"Likely misread. Falling back to declared amount."
                )
                verified_bill = Decimal('0')  # Discard bogus OCR value

        # Payout Basis logic (SSoT Selection) - Fix 4 Basis Used
        if claim.payout_basis_source == 'OCR' and verified_bill > 0:
            basis = verified_bill
            basis_label = "OCR Verified"
        elif claim.payout_basis_source == 'MANUAL' and claim.payout_basis_amount:
            basis = safe_money(claim.payout_basis_amount)
            basis_label = "Manual Override"
        elif verified_bill > 0:
            basis = verified_bill
            basis_label = "OCR Verified"
        else:
            basis = declared_amount
            basis_label = "Declared Amount"

        # 2. Deductions (Sequential)
        room_excess = ClaimPayoutService.calculate_room_excess(claim)
        deductible = safe_money(claim.deductible_amount or 0)
        
        # 3. Policy Baseline
        policy_baseline = max(Decimal('0'), basis - room_excess - deductible)
        
        # 4. AI Risk Reserve (Monetary value, not direct percentage)
        risk_amount = safe_money(claim.risk_amount or 0)
        
        # 5. Final Settlement
        final_amount = max(Decimal('0'), policy_baseline - risk_amount)
        
        # 🛡️ Policy Hard Cap: Final payout can NEVER exceed policy sum_insured
        try:
            policy_limit = safe_money(claim.policy.sum_insured)
            if final_amount > policy_limit:
                final_amount = policy_limit
        except Exception:
            pass  # If policy limit unavailable, skip cap
        
        return {
            "declared_amount": declared_amount,
            "verified_bill": verified_bill,
            "basis_label": basis_label,
            "room_excess": room_excess,
            "deductible": deductible,
            "policy_baseline": policy_baseline,
            "risk_score": float(claim.fraud_probability or 0) * 100,
            "composite_risk_score": float(claim.fraud_probability or 0) * 100,
            "risk_amount": risk_amount,
            "final_amount": final_amount,
            "model_version": claim.model_version.version_id if claim.model_version else "V3.6_SHA256"
        }

    @staticmethod
    def get_authoritative_payout(claim) -> Decimal:
        """Returns the single authoritative payout amount for display (Decimal)."""
        # 1. If the claim is already approved or settled, the approved_amount is the absolute SSoT
        if claim.status in ['approved', 'settled'] and claim.approved_amount is not None:
            return safe_money(claim.approved_amount)

        # 2. Human override takes priority for claims still in progress
        if claim.manual_override and claim.human_override_amount:
             return safe_money(claim.human_override_amount)

        # 3. Otherwise, use the compute_authoritative_payout SSoT
        payload = ClaimPayoutService.compute_authoritative_payout(claim)
        return payload["final_amount"]

    @staticmethod
    def get_payout_label(claim) -> str:
        """Returns a human-readable label indicating the source of the displayed amount."""
        if claim.manual_override:
            return "Manual Override"
        return "System Recommended Settlement"

    # ── PERSISTENCE ──────────────────────────────────────────────────────

    @staticmethod
    def record_pipeline_result(claim, payload, engine_version, user=None):
        """
        Persist a new AI pipeline recommendation with full audit trail.
        
        Args:
            claim: Claim instance
            payload: dict from compute_authoritative_payout
            engine_version: str — version of the engine (e.g., "v3.6-Certified")
            user: Optional User — who triggered the pipeline
        """
        from claims.models import PayoutRecommendationLog

        # ── DEFENSIVE SCHEMA MAPPING (SSoT Migration) ─────────────────────
        print("PIPELINE PAYLOAD (DEBUG):", payload)
        
        amount = safe_money(payload.get("final_amount", payload.get("recommended_amount", 0)))
        previous = claim.final_ai_recommendation

        # Freeze initial prediction on first run only
        if not claim.initial_ai_prediction:
            claim.initial_ai_prediction = amount

        claim.final_ai_recommendation = amount
        claim.recommended_amount = amount # Parallel sync for backward compatibility
        claim.ai_engine_version = engine_version
        claim.prediction_generated_at = timezone.now()

        # Sync specific financial fields
        claim.risk_score = payload.get("risk_score", 
                           payload.get("composite_risk_score", 
                           payload.get("risk_indicator_percent", 0)))
        claim.risk_amount = payload.get("risk_amount", 0)
        claim.ai_decision = payload.get("decision", payload.get("ai_decision", "REVIEW"))

        print(f"PIPELINE PERSISTED: Score={claim.risk_score} | Recommended={claim.recommended_amount} | Final={claim.final_ai_recommendation}")

        claim.save(update_fields=[
            'initial_ai_prediction',
            'final_ai_recommendation',
            'recommended_amount',
            'ai_engine_version',
            'prediction_generated_at',
            'risk_score',
            'risk_amount',
            'ai_decision'
        ])

        # Audit trail
        PayoutRecommendationLog.objects.create(
            claim=claim,
            previous_amount=previous,
            new_amount=amount,
            changed_by=user,
            change_reason=f"AI Pipeline ({engine_version}) recommendation",
            engine_version=engine_version,
        )

        logger.info(
            f"[PayoutService] Claim {claim.claim_number}: "
            f"Settlement updated to ₹{amount:,.2f} (engine: {engine_version})"
        )

    @staticmethod
    def record_human_override(claim, amount, user, reason="Manual override"):
        """Record a manual auditor override with governance audit trail."""
        from claims.models import PayoutRecommendationLog

        amount = Decimal(str(amount)).quantize(Decimal('0.01'))
        previous = claim.human_override_amount or claim.final_ai_recommendation

        claim.human_override_amount = amount
        claim.manual_override = True
        claim.override_reason = reason
        claim.save(update_fields=[
            'human_override_amount',
            'manual_override',
            'override_reason',
        ])

        # Audit trail
        PayoutRecommendationLog.objects.create(
            claim=claim,
            previous_amount=previous,
            new_amount=amount,
            changed_by=user,
            change_reason=f"Human Override: {reason}",
            engine_version="MANUAL",
        )

    # ── CONTEXT HELPERS (for views) ───────────────────────────────────────

    @staticmethod
    def get_breakdown_context(claim) -> dict:
        """
        Returns a complete financial breakdown dict for template rendering.
        Enforces Authoritative SSoT logic.
        """
        payload = ClaimPayoutService.compute_authoritative_payout(claim)
        
        # ── CONSTRUCT STEP-BY-STEP RECONSTRUCTION ───────────────────────────
        steps = [
            {
                "label": f"Verified Bill Amount", 
                "value": float(payload["verified_bill"]), 
                "icon": "bi-receipt"
            }
        ]

        if payload["room_excess"] > 0:
            steps.append({
                "label": "Room Rent Excess", 
                "value": -float(payload["room_excess"]), 
                "icon": "bi-hospital",
                "formula": f"Limit: ₹{claim.allowed_room_rent}/day | Actual: ₹{float(claim.room_rent_cost)/max(1, claim.admission_days):.0f}/day"
            })

        steps.append({
            "label": "Policy Deductible", 
            "value": -float(payload["deductible"]), 
            "icon": "bi-dash-circle"
        })

        steps.append({
            "label": "Policy Baseline", 
            "value": float(payload["policy_baseline"]), 
            "icon": "bi-calculator"
        })

        if payload["risk_amount"] > 0:
            steps.append({
                "label": f"Risk Reserve ({payload['composite_risk_score']:.2f})", 
                "value": -float(payload["risk_amount"]), 
                "icon": "bi-shield-exclamation"
            })

        # Final Payout Step
        final_val = float(payload["final_amount"])
        final_label = "System Recommended Settlement"

        if claim.status in ['approved', 'settled'] and claim.approved_amount is not None:
            final_val = float(claim.approved_amount)
            final_label = "Approved Settlement Amount"

        steps.append({
            "label": final_label, 
            "value": final_val, 
            "icon": "bi-check-circle-fill", 
            "is_total": True
        })

        return {
            'steps': steps,
            'declared_amount': float(payload['declared_amount']),
            'verified_bill': float(payload['verified_bill']),
            'room_excess': float(payload['room_excess']),
            'deductible_amount': float(payload['deductible']),
            'policy_baseline': float(payload['policy_baseline']),
            'composite_risk_score': payload['composite_risk_score'],
            'risk_amount': float(payload['risk_amount']),
            'final_amount': final_val,
            'payout_label': final_label if claim.status in ['approved', 'settled'] else ClaimPayoutService.get_payout_label(claim),
            'engine_version': payload['model_version'],
            'generated_at': claim.prediction_generated_at or timezone.now(),
        }
