import os
import json
import logging
from django.db.models import Q
from decimal import Decimal, InvalidOperation

def calculate_text_similarity(text1, text2):
    """
    Calculates simple character-based overlap similarity between two strings.
    Useful for comparing claim descriptions or invoice text.
    """
    if not text1 or not text2:
        return 0.0
    
    s1 = set(str(text1).lower().split())
    s2 = set(str(text2).lower().split())
    
    if not s1 or not s2:
        return 0.0
        
    intersection = s1.intersection(s2)
    union = s1.union(s2)
    
    return len(intersection) / len(union)

import difflib

def compare_vehicle_numbers(v1, v2):
    """Normalized comparison for vehicle numbers (removes spaces and hyphens)."""
    n1 = str(v1 or "").replace(" ", "").replace("-", "").upper()
    n2 = str(v2 or "").replace(" ", "").replace("-", "").upper()
    
    if not n1 or not n2:
        return False, 0.0, n1, n2
        
    similarity = difflib.SequenceMatcher(None, n1, n2).ratio()
    match_found = (n1 == n2) or (similarity >= 0.85)
    
    return match_found, similarity, n1, n2

def generate_assessment_remark(claim, decision=None, mode='detailed'):
    """
    Auto-generates professional, regulator-grade staff assessment remarks based on real-time claim intelligence.
    
    Data Source priority:
    1. Explicit decision passed from UI (Approve/Review/Reject)
    2. Fallback to claim.staff_recommendation or claim.status
    """
    from decimal import Decimal
    from django.contrib.humanize.templatetags.humanize import intcomma
    from claims.services.claim_review_service import ClaimReviewService

    # 1. Fetch Authoritative SSoT Payload
    try:
        payload = ClaimReviewService.get_review_payload(claim)
    except Exception as e:
        # Emergency Fallback if service fails
        print(f"REMARK GENERATION FALLBACK: {str(e)}")
        risk_score_fb = float(getattr(claim, 'risk_score', 0) or 0)
        policyholder_name = (
            getattr(claim.created_by, "full_name_display", None)
            or claim.created_by.get_full_name()
            or claim.created_by.username
        ) if claim.created_by else "Internal"
        payload = {
            "risk_score": risk_score_fb,
            "risk_label": "LOW" if risk_score_fb < 20 else "MEDIUM" if risk_score_fb < 50 else "HIGH",
            "final_amount": float(claim.final_ai_recommendation or claim.claimed_amount or 0),
            "policyholder_name": policyholder_name,
            "verified_bill": float(getattr(claim, 'ocr_verified_bill_total', 0) or 0),
            "declared_amount": float(claim.claimed_amount or 0)
        }

    # Debug Logging for Governance Audit
    print("REMARK PAYLOAD:", payload)

    # 2. Resolve authoritative decision context
    if not decision:
        decision = getattr(claim, 'staff_recommendation', None) or str(claim.status).upper()
    
    decision = str(decision).upper()
    is_approve = decision in ["APPROVE", "APPROVED", "SETTLED", "SETTLEMENT", "SETTLE"]
    is_reject = decision in ["REJECT", "REJECTED"]
    # Default everything else to REVIEW
    is_review = not is_approve and not is_reject

    # 3. Gather Intelligence Metadata from SSoT
    claim_type = claim.get_claim_type_display() if hasattr(claim, 'get_claim_type_display') else str(claim.claim_type)
    declared = payload.get("declared_amount", 0.0)
    verified = payload.get("verified_bill", 0.0)
    risk_score = payload.get("risk_score", 0.0)
    risk_band = payload.get("risk_label", "UNKNOWN")
    final_amount = payload.get("final_amount", 0.0)
    
    kyc_status = "VERIFIED" if (claim.created_by and claim.created_by.identity_verified) else "PENDING"
    variance_abs = abs(declared - verified)

    # 4. Decision-Based Logic Blocks
    sentences = []
    
    # 💎 Executive Settlement Path
    if decision == "SETTLEMENT" or decision == "SETTLE":
        sentences.append(f"Financial disbursement authorized for {claim_type} dossier.")
        if mode == 'detailed':
            sentences.append(f"Final audited payout: ₹{intcomma(round(final_amount,2))}.")
            sentences.append(f"Governance review confirmed risk profile is {risk_band} ({risk_score:.2f}).")
            sentences.append(f"Identity verification ({kyc_status}) and document audit complete. Execution dispatched to treasury.")
        else:
            sentences.append(f"Executive authorization granted for ₹{intcomma(round(final_amount,2))} settlement.")

    elif is_approve:
        sentences.append(f"Audit confirms {claim_type} dossier is compliant.")
        if mode == 'detailed':
            sentences.append(f"Verified financial breakdown: Declared ₹{intcomma(round(declared,2))} vs OCR ₹{intcomma(round(verified,2))}. { 'Full alignment detected.' if variance_abs < 100 else f'Minor variance of ₹{intcomma(round(variance_abs,2))} addressed.' }")
            sentences.append(f"Risk profile is {risk_band} ({risk_score:.2f} score).")
            sentences.append(f"KYC status is {kyc_status}. Recommended settlement: ₹{intcomma(round(final_amount,2))}.")
        else:
            sentences.append(f"Low risk profile ({risk_score:.1f}). Approved payout: ₹{intcomma(round(final_amount,2))}.")

    elif is_reject:
        sentences.append(f"Critical governance failure identified for this {claim_type} request.")
        if mode == 'detailed':
            if risk_score > 50:
                sentences.append(f"High-confidence risk flags detected (Score: {risk_score:.2f}).")
            sentences.append(f"Dossier fails regulatory threshold for automated or manual approval.")
        else:
            sentences.append(f"Rejected due to high risk profile ({risk_score:.1f}) and integrity concerns.")

    else: # REVIEW
        sentences.append(f"Manual investigation required for {claim_type} dossier.")
        if mode == 'detailed':
            if variance_abs > (declared * 0.15):
                sentences.append(f"Flagged for financial reconciliation: ₹{intcomma(round(variance_abs,2))} variance requires manual receipt validation.")
            sentences.append(f"Risk parameters: {risk_band} ({risk_score:.2f}).")
            sentences.append(f"Verification of {kyc_status} KYC and hospital artifacts is mandatory before final settlement.")
        else:
            sentences.append(f"Review required due to financial variance and {risk_band} risk profile.")

    remark = " ".join(sentences)
    return remark

def get_claim_subject_user_policy(claim):
    """
    Resolve the exact user-owned policy for a claim.
    Prefer the explicit foreign key and only fall back to legacy data when needed.
    """
    from policy.models import UserPolicy

    if getattr(claim, "user_policy_id", None):
        return claim.user_policy

    if getattr(claim, "created_by_id", None):
        user_policy = UserPolicy.objects.filter(
            user=claim.created_by,
            policy=claim.policy,
        ).first()
        if user_policy:
            return user_policy

    if getattr(claim, "vehicle_number", None):
        return UserPolicy.objects.filter(
            policy=claim.policy,
            vehicle_number=claim.vehicle_number,
        ).first()

    return None

def get_visible_claims_q(user):
    """
    Restrict user-facing claim queries to the claimant or the exact owned UserPolicy.
    This prevents different policyholders on the same master policy plan from seeing each other's claims.
    """
    from policy.models import UserPolicy

    user_policy_ids = list(
        UserPolicy.objects.filter(user=user)
        .exclude(status__in=["rejected", "cancelled"])
        .values_list("id", flat=True)
    )

    visibility_q = Q(created_by=user)
    if user_policy_ids:
        visibility_q |= Q(user_policy_id__in=user_policy_ids)

    return visibility_q

def user_can_access_claim(user, claim):
    if user.is_superuser or getattr(user, "role", None) in ["admin", "staff"]:
        return True

    if getattr(claim, "created_by_id", None) == user.id:
        return True

    if getattr(claim, "user_policy_id", None):
        return claim.user_policy.user_id == user.id

    return False

def safe_money(value, fallback=0):
    if value is None:
        return Decimal(str(fallback))
    try:
        return Decimal(str(value))
    except (TypeError, ValueError, InvalidOperation):
        return Decimal(str(fallback))
