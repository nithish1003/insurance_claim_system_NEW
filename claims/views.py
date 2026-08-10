import datetime
import mimetypes
import os
import json
from decimal import Decimal, InvalidOperation
from django.utils.crypto import get_random_string
import logging
from django.http import JsonResponse
from .ai_calculation_engine import AICalculationEngine

# 🛡️ Initialize Auditor logging
logger = logging.getLogger(__name__)


from django.db import transaction
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.conf import settings
from django.http import FileResponse, Http404
from django.core.paginator import Paginator
from accounts.decorators import role_required, admin_only, staff_or_admin
from django.views.decorators.csrf import csrf_exempt
import datetime
import mimetypes
import os
import json
from decimal import Decimal, InvalidOperation
from django.utils.crypto import get_random_string
import logging
from django.http import JsonResponse
from .ai_calculation_engine import AICalculationEngine

# 🛡️ Initialize Auditor logging
logger = logging.getLogger(__name__)


from django.db import transaction
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.conf import settings
from django.http import FileResponse, Http404
from django.core.paginator import Paginator
from accounts.decorators import role_required, admin_only, staff_or_admin
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from policy.models import PolicyHolder, Policy, UserPolicy, Payment
from reports.models import ActivityLog
from accounts.utils import mask_phone, mask_email
from notifications.utils import create_notification
from django.db.models import Q, Sum
from .models import (
    Claim,
    ClaimDocument,
    ClaimNote,
    ClaimAssessment,
    ClaimSettlement,
    ClaimAuditLog,
    AuditorReview,
    DOCUMENT_EXTENSION_VALIDATOR
)

from .forms import StaffNoteForm, ClaimAssessmentForm, ClaimFilterForm
from .utils import (
    compare_vehicle_numbers,
    get_claim_subject_user_policy,
    get_visible_claims_q,
    user_can_access_claim,
    safe_money,
)

# 🔥 AI IMPORTS
from ai_features.services.ai_claim_service import predict_claim_type
from ai_features.services.amount_service import predict_recommended_amount
from ai_features.services.fraud_service import predict_fraud_risk
from ai_features.services.ai_pipeline_service import run_intelligence_pipeline

GRACE_PERIOD_DAYS = 7


# =====================================
# HELPER
# =====================================

def user_has_policy(user, policy):
    """Check if a user owns a policy via UserPolicy (approved) OR legacy PolicyHolder."""
    return (
        UserPolicy.objects.filter(user=user, policy=policy).exists()
        or PolicyHolder.objects.filter(user=user, policy=policy).exists()
    )


def _get_claim_by_public_id_or_404(public_id):
    return get_object_or_404(Claim, public_id=public_id)


def _get_claim_document_by_public_id_or_404(public_id):
    return get_object_or_404(ClaimDocument, public_id=public_id)


def _serialize_claim_integrity_state(claim):
    declared_amount = safe_money(claim.declared_claim_amount or claim.claimed_amount or 0)
    verified_amount = safe_money(claim.ocr_verified_bill_total or 0)
    return {
        "declared_amount": float(declared_amount),
        "ocr_verified_amount": float(verified_amount),
        "mismatch_ratio": float(claim.claim_amount_mismatch_ratio or 0),
        "integrity_status": claim.integrity_status,
        "integrity_status_display": claim.get_integrity_status_display() if hasattr(claim, "get_integrity_status_display") else claim.integrity_status,
        "required_action": claim.integrity_required_action,
        "payout_basis_amount": float(claim.payout_basis_amount or 0),
        "payout_basis_source": claim.payout_basis_source,
        "payout_basis_source_display": claim.get_payout_basis_source_display() if hasattr(claim, "get_payout_basis_source_display") else claim.payout_basis_source,
        "manual_amount_confirmed": bool(claim.manual_amount_confirmed),
        "review_hold_flag": bool(claim.review_hold_flag),
        "critical_mismatch_flag": bool(claim.critical_mismatch_flag),
        "fraud_risk_score": float(claim.fraud_risk_score or 0),
        "documentation_risk_score": float(claim.documentation_risk_score or 0),
        "payout_uncertainty_score": float(claim.payout_uncertainty_score or 0),
    }


def _apply_integrity_basis_selection(claim, basis_selection, manual_amount=None, performed_by=None, persist_audit=True):
    declared_amount = safe_money(claim.declared_claim_amount or claim.claimed_amount or 0)
    verified_amount = safe_money(claim.ocr_verified_bill_total or 0)
    old_basis = claim.payout_basis_source
    old_amount = claim.payout_basis_amount

    if basis_selection == "DECLARED":
        chosen_amount = declared_amount
        chosen_source = "DECLARED"
    elif basis_selection == "OCR":
        chosen_amount = verified_amount
        chosen_source = "OCR"
    elif basis_selection == "MANUAL":
        if manual_amount is None or str(manual_amount).strip() == "":
            raise ValueError("Manual amount is required for manual payout selection.")
        try:
            chosen_amount = safe_money(manual_amount)
        except (InvalidOperation, TypeError):
            raise ValueError("Manual amount is required for manual payout selection.")
        chosen_source = "MANUAL"
    else:
        raise ValueError("Unsupported payout basis selection.")

    claim.payout_basis_amount = chosen_amount
    claim.payout_basis_source = chosen_source
    claim.manual_amount_confirmed = True
    claim.review_hold_flag = False
    claim.critical_mismatch_flag = (claim.claim_amount_mismatch_ratio or 0) > 0.50
    claim.integrity_status = claim.derive_integrity_status(claim.claim_amount_mismatch_ratio or 0)

    if persist_audit and performed_by and (old_basis != chosen_source or old_amount != chosen_amount):
        ClaimAuditLog.objects.create(
            claim=claim,
            action="PAYOUT_BASIS_OVERRIDE",
            description=(
                f"Basis changed from {old_basis} (₹{old_amount}) to "
                f"{chosen_source} (₹{chosen_amount})"
            ),
            performed_by=performed_by,
        )

    return {
        "previous_basis": old_basis,
        "previous_amount": float(old_amount or 0),
        "basis": _serialize_claim_integrity_state(claim),
    }


# =====================================
# CLAIM LIST
# =====================================

@login_required
def claim_list(request):
    is_admin_or_staff = request.user.is_superuser or request.user.role in ["admin", "staff"]
    
    # Base queryset with optimization
    claims = Claim.objects.select_related("policy", "assigned_to", "created_by")

    # 1. Base Role-Based Filtering
    if not is_admin_or_staff:
        claims = claims.filter(get_visible_claims_q(request.user)).distinct()

    # 2. Filter Setup
    all_user_claims = list(claims)
    claim_choices = [('', 'All Claims')] + [(c.claim_number, c.claim_number) for c in all_user_claims]
    claims_data_json = json.dumps({
        c.claim_number: {
            'type': c.claim_type,
            'status': c.status,
            'date': c.incident_date.isoformat() if c.incident_date else None
        } for c in all_user_claims
    })

    # 3. Filter Execution
    filter_form = ClaimFilterForm(request.GET or None, claim_choices=claim_choices)
    is_filtered = False
    
    # Status Definition
    active_states = ['submitted', 'under_review', 'staff_reviewed', 'investigation', 'approved']
    
    if filter_form.is_valid() and any(request.GET.values()):
        data = filter_form.cleaned_data
        if data.get('claim_number'):
            claims = claims.filter(claim_number__icontains=data['claim_number'])
            is_filtered = True
        if data.get('claim_type'):
            claims = claims.filter(claim_type=data['claim_type'])
            is_filtered = True
        if data.get('status'):
            claims = claims.filter(status=data['status'])
            is_filtered = True
        if data.get('date_from'):
            claims = claims.filter(incident_date__gte=str(data['date_from']))
            is_filtered = True
        if data.get('date_to'):
            claims = claims.filter(incident_date__lte=str(data['date_to']))
            is_filtered = True

    # 4. KPI Summary calculation (NOW DYNAMIC)
    summary = {
        'total': claims.count(),
        'submitted': claims.filter(status='submitted').count(),
        'under_review': claims.filter(status='under_review').count(),
        'waiting_approval': claims.filter(status='staff_reviewed').count(),
        'investigation': claims.filter(status='investigation').count(),
        'approved': claims.filter(status__in=['approved', 'partially_approved']).count(),
        'rejected': claims.filter(status='rejected').count(),
        'settled': claims.filter(status='settled').count(),
    }
            
    if not is_filtered:
        # Default view: Only active dossiers (Requirement #1)
        claims = claims.filter(status__in=active_states)

    # 5. Presentation
    claims = claims.order_by("-created_at")

    context = {
        "claims": claims,
        "summary": summary,
        "filter_form": filter_form,
        "claims_data_json": claims_data_json,
        "is_filtered": is_filtered,
        "has_claims_at_all": len(all_user_claims) > 0,
        "total_active_count": claims.count()
    }

    return render(request, "claims/claim_list.html", context)



# =====================================
# CREATE CLAIM (AI INTEGRATED)
# =====================================

@login_required
def claim_submit(request):

    if request.user.is_superuser or request.user.role in ["admin", "staff"]:
        # For admins/staff, we use the catalog policies for now or all UserPolicies
        # But usually they submit on behalf of a user. For simplicity, we'll keep all catalog policies
        policies = Policy.objects.all()
    else:
        # Pass the actual UserPolicy objects so we can access remaining_sum_insured property
        policies = UserPolicy.objects.filter(
            user=request.user,
            status__in=['active', 'grace']
        ).select_related('policy')
        
        # 🔥 PROACTIVE BALANCE SYNC: Refresh available coverage before rendering dropdown
        for p in policies:
            p.sync_status_with_premiums()

    if request.method == "POST":

        policy = get_object_or_404(Policy, public_id=request.POST.get("policy"))
        user_policy = None

        if not (request.user.is_superuser or request.user.role in ["admin", "staff"]):
            if not user_has_policy(request.user, policy):
                messages.error(request, "Invalid policy")
                return redirect("claim:create")
            
            # 🛡️ Real Insurance Lifecycle Gate: Block claims for Lapsed policies
            user_policy = UserPolicy.objects.filter(
                user=request.user,
                policy=policy,
                status__in=['active', 'grace'],
            ).first()
            if user_policy:
                # Refresh status before checking (this also checks for exhaustion)
                current_status = user_policy.sync_status_with_premiums()
                
                # 🛑 1. Block if Coverage is 0
                if user_policy.remaining_sum_insured <= 0:
                    messages.error(
                        request, 
                        "Claim submission BLOCKED. Your policy coverage (Sum Insured) is FULLY EXHAUSTED. "
                        "You have successfully utilized 100% of your available insurance limit. "
                        "No further claims can be filed against this policy."
                    )
                    return redirect("claim:create")

                # 🛑 2. Block if Lapsed
                if current_status == 'lapsed':
                    messages.error(
                        request, 
                        "Claim submission BLOCKED. Your policy has LAPSED due to non-payment. "
                        "Please clear outstanding installments in the Billing Console to reactivate coverage."
                    )
                    return redirect("claim:create")

                # ⚠️ 3. Warning for High Usage (> 80%)
                if user_policy.coverage_usage_percentage >= 80:
                    messages.warning(
                        request,
                        f"IMPORTANT: You have utilized {user_policy.coverage_usage_percentage:.1f}% of your Sum Insured. "
                        f"Remaining coverage available: ₹{user_policy.remaining_sum_insured:,.2f}. "
                        "Please keep this in mind when filing your claim."
                    )
            
            # 🛡️ New Check: Only allow claims for ACTIVE policies
            if policy.status != 'active':
                messages.error(
                    request, 
                    f"Cannot file claim. This policy is currently '{policy.get_status_display()}'. "
                    "Only fully activated policies are eligible for claims."
                )
                return redirect("claim:create")
            
            # 🛡️ Duplicate Claim Prevention: Check if user already submitted claim for this policy recently
            # Check for same policy, user, incident date, and amount to prevent exact duplicates
            try:
                claimed_amount = safe_money(request.POST.get("claimed_amount", "0"))
            except (TypeError, InvalidOperation):
                claimed_amount = Decimal('0')
            
            recent_claims = Claim.objects.filter(
                policy=policy,
                created_by=request.user,
                incident_date=request.POST.get("incident_date"),
                claimed_amount=claimed_amount,
                status__in=['submitted', 'under_review', 'investigation']
            )
            
            if recent_claims.exists():
                messages.error(
                    request, 
                    "You have already submitted a claim for this policy with the same incident date and amount. "
                    "Please wait for the current claim to be processed."
                )
                return redirect("claim:create")

        # 📋 Extract Common Fields
        description = request.POST.get("description")
        incident_date_str = request.POST.get("incident_date")
        
        # 🛡️ Date Validation
        try:
            # Parse the incoming date string
            incident_date = datetime.datetime.strptime(incident_date_str, "%Y-%m-%d").date()
            today = timezone.now().date()

            # 1 & 2. Block Future Dates (Allow same-day)
            if incident_date > today:
                messages.error(request, f"Claim Rejected: Incident date ({incident_date}) cannot be in the future. (Current Date: {today})")
                return redirect("claim:create")
                
            # 3 & 4. Policy Start Date Validation
            user_policy = UserPolicy.objects.filter(
                user=request.user,
                policy=policy,
                status__in=['active', 'grace'],
            ).first()
            if user_policy and user_policy.start_date:
                if not settings.DEBUG:
                    # PRODUCTION: Strictly block dates before policy start
                    if incident_date < user_policy.start_date:
                        messages.error(
                            request, 
                            f"Claim Rejected: Incident happened on {incident_date}, but your coverage only began on {user_policy.start_date}."
                        )
                        return redirect("claim:create")
                else:
                    # DEMO MODE: Allow past dates with an optional grace period (using system default)
                    min_allowed_date = user_policy.start_date - datetime.timedelta(days=GRACE_PERIOD_DAYS)
                    if incident_date < min_allowed_date:
                        messages.error(
                            request, 
                            f"Demo Notice: Incident date is restricted to a {GRACE_PERIOD_DAYS}-day grace period before policy start."
                        )
                        return redirect("claim:create")
        except (ValueError, TypeError):
            messages.error(request, "Invalid incident date format.")
            return redirect("claim:create")

        claimed_amount_str = request.POST.get("claimed_amount")
        
        try:
            claimed_amount = safe_money(claimed_amount_str)
        except (TypeError, InvalidOperation):
            messages.error(request, "Invalid claim amount format.")
            return redirect("claim:create")

        # 🛡️ Policy Type Specific Validation
        policy_type_lower = (policy.policy_type or "").lower()
        
        # 🚗 Motor Policy Validation
        v_num = request.POST.get("vehicle_number")
        if 'motor' in policy_type_lower or 'vehicle' in policy_type_lower:
            if not v_num:
                messages.error(request, "Vehicle Registration Number is required for motor claims.")
                return redirect("claim:create")
            
            # Fetch the registered vehicle number from the actual UserPolicy
            user_policy = UserPolicy.objects.filter(
                user=request.user,
                policy=policy,
                status__in=['active', 'grace'],
            ).first()
            registered_vnum = user_policy.vehicle_number if user_policy else policy.vehicle_number
            
            # Use our new robust comparison utility
            match_found, similarity, db_norm, input_norm = compare_vehicle_numbers(registered_vnum, v_num)
            
            # 🛠️ DEBUG LOGGING (Important for diagnosing OCR issues)
            print(f"--- VEHICLE VALIDATION DEBUG ---")
            print(f"DB (Original): {registered_vnum} | DB (Normalized): {db_norm}")
            print(f"INPUT (Original): {v_num} | INPUT (Normalized): {input_norm}")
            print(f"Similarity Score: {similarity:.2%}")
            print(f"Match Result: {match_found}")
            print(f"-------------------------------")

            if not match_found:
                messages.error(
                    request, 
                    "Vehicle number format mismatch. Please verify your document or try re-uploading. "
                    "(If the error persists, ensure the number exactly matches your policy certificate.)"
                )
                return redirect("claim:create")
                
            rc_file = request.FILES.get("rc_document")
            if not rc_file:
                messages.error(request, "RC Document upload is mandatory for motor claims.")
                return redirect("claim:create")
            if not request.FILES.get("repair_bill"):
                messages.error(request, "Repair Bill upload is mandatory for motor claims.")
                return redirect("claim:create")

            # Real-time RC OCR Verification
            from claims.services.ocr_service import RCOCRService
            from django.core.files.storage import default_storage
            
            # Temporary save for OCR processing
            rc_temp_filename = f"verify_rc_{request.user.id}_{int(timezone.now().timestamp())}_{rc_file.name}"
            rc_temp_path = default_storage.save(f"tmp/{rc_temp_filename}", rc_file)
            rc_full_temp_path = os.path.join(settings.MEDIA_ROOT, rc_temp_path)
            
            try:
                rc_ocr_service = RCOCRService()
                rc_valid = rc_ocr_service.validate_rc(rc_full_temp_path, v_num)
                if not rc_valid:
                    messages.error(
                        request,
                        "RC Document Validation Failed: Vehicle number does not match uploaded RC."
                    )
                    return redirect("claim:create")
            finally:
                # Cleanup temp file
                if os.path.exists(rc_full_temp_path):
                    try:
                        os.remove(rc_full_temp_path)
                    except Exception as e:
                        print(f"Error removing temp RC file: {e}")

        # 🏥 Health Policy Validation
        if 'health' in policy_type_lower:
            if not request.FILES.get("hospital_bill"):
                messages.error(request, "Hospital Bill is mandatory for health claims.")
                return redirect("claim:create")

        # 🏠 Home Policy Validation
        if 'home' in policy_type_lower:
            if not (request.FILES.get("property_proof") or request.FILES.get("damage_proof")):
                messages.error(request, "Property or Damage proof is mandatory for home claims.")
                return redirect("claim:create")

        # 🕯️ Life Policy Validation
        if 'life' in policy_type_lower:
            if not request.FILES.get("death_certificate"):
                messages.error(request, "Death Certificate is mandatory for life insurance claims.")
                return redirect("claim:create")

        # 🆔 Aadhaar Verification (All Types)
        entered_aadhaar = request.POST.get("aadhaar_number")
        if not entered_aadhaar:
            messages.error(request, "Aadhaar Number is required.")
            return redirect("claim:create")

        # 💳 Aadhaar Identity Verification
        try:
            profile = request.user.profile
            # 1. Match Entered Number with Registered Profile
            if entered_aadhaar.strip() != profile.aadhaar_number:
                messages.error(request, f"Aadhaar Mismatch: The entered number does not match your registered identity ({profile.masked_aadhaar}).")
                return redirect("claim:create")
            
            # 2. OCR Verification of Uploaded Document
            identity_proof = request.FILES.get("identity_proof")
            if identity_proof:
                from ai_features.services.ocr_engine import extract_text_compat
                from ai_features.services.ocr_service import verify_identity
                from django.core.files.storage import default_storage
                
                # Temporary save to full path for OCR processing
                temp_filename = f"verify_{request.user.id}_{int(timezone.now().timestamp())}_{identity_proof.name}"
                temp_path = default_storage.save(f"tmp/{temp_filename}", identity_proof)
                full_temp_path = os.path.join(settings.MEDIA_ROOT, temp_path)
                
                try:
                    results = verify_identity(full_temp_path, profile.full_name, profile.aadhaar_number)
                    
                    if not results.get("verified"):
                        # Detailed feedback on why it failed
                        msg = "Identity Validation Failed: The uploaded document could not be verified as your registered Aadhaar. "
                        if not results.get("number_match"):
                            if results.get("extracted_number"):
                                msg += f"Extracted number {results['extracted_number'][-4:].rjust(12, 'X')} doesn't match."
                            else:
                                msg += "Aadhaar number not legible in scan."
                        else:
                            if results.get("user_message"):
                                msg += results.get("user_message")
                            else:
                                msg += f"Name on the document does not match your registered profile name ('{profile.full_name}')."
                        
                        messages.error(request, msg)
                        return redirect("claim:create")
                finally:
                    # Cleanup immediately
                    if os.path.exists(full_temp_path):
                        os.remove(full_temp_path)
        except AttributeError:
            # Policyholder missing profile - shouldn't happen with current reg flow
            messages.error(request, "Identity profile incomplete. Please update your profile before filing a claim.")
            return redirect("accounts:policyholder_dashboard")

        # 👨‍💼 Automatic Staff Assignment (Ensures analytics populates)
        from django.contrib.auth import get_user_model
        User = get_user_model()
        staff_member = User.objects.filter(role='staff').first()

        # 💾 Save Claim (Initial State)
        claim = Claim.objects.create(
            policy=policy,
            user_policy=user_policy,
            claim_number=f"CLM-{int(timezone.now().timestamp())}",
            claim_type="other", # Temporary, will be updated by pipeline
            status="submitted",
            incident_date=incident_date,
            description=description,
            claimed_amount=claimed_amount,
            vehicle_number=v_num,
            deductible_amount=policy.deductible,
            created_by=request.user,
            assigned_to=staff_member
        )

        # Eagerly run NLP Claim Type Prediction at submission (Fixes classification order of operations)
        try:
            ai_type, confidence = predict_claim_type(claim.description)
            claim.ai_claim_type = ai_type
            claim.confidence_score = confidence * 100
            if (claim.confidence_score or 0) > 70:
                claim.claim_type = claim.ai_claim_type
            claim.save(update_fields=['ai_claim_type', 'confidence_score', 'claim_type'])
        except Exception as e:
            logger.error(f"Eager claim type prediction failed: {str(e)}")


        # 📎 Document Saving Helper
        def save_doc(file_key, doc_type_code, desc=""):
            files = request.FILES.getlist(file_key)
            for f in files:
                ClaimDocument.objects.create(
                    claim=claim,
                    document_type=doc_type_code,
                    file=f,
                    description=desc,
                    uploaded_by=request.user
                )

        save_doc("identity_proof", "identity_proof", "Aadhaar / ID Proof")
        save_doc("hospital_bill", "hospital_bill", "Medical / Hospital Bill")
        save_doc("repair_bill", "repair_bill", "Repair / Maintenance Bill")
        save_doc("rc_document", "rc_document", "Vehicle RC")
        save_doc("death_certificate", "death_certificate", "Death Certificate")
        save_doc("property_proof", "property_proof", "Property Ownership Proof")
        save_doc("damage_proof", "damage_proof", "Damage Photos / evidence")
        save_doc("supporting_document", "other", "Other supporting document")

        # 🤖 UNIFIED AI PIPELINE (OCR -> Classify -> Risk -> Payout -> Decision)
        try:
            pipeline_res = run_intelligence_pipeline(claim)
            
            # 🔄 REFRESH: Ensure the claim instance in memory has updated fields from the engine
            claim.refresh_from_db()
            
            if pipeline_res and "error" not in pipeline_res:
                # Sync primary claim_type with AI classification if high confidence
                if (claim.confidence_score or 0) > 70:
                    claim.claim_type = claim.ai_claim_type
                    claim.save(update_fields=['claim_type'])

                # ── PHASE 7: AUDIT LOGGING (Enterprise Mismatch Feature) ────────
                from claims.services.claim_payout_service import ClaimPayoutService
                authoritative_amount = ClaimPayoutService.get_authoritative_payout(claim)
                
                audit_msg = f"AI Pipeline v2 SUCCESS: Decision={claim.ai_decision}, Amount=₹{authoritative_amount:,.2f}"
                if claim.mismatch_flag:
                    audit_msg += f" | Mismatch detected: {claim.claim_amount_mismatch_ratio*100:.1f}%"
                    if claim.additional_bill_requested:
                        audit_msg += " | Auto review triggered"
                
                ClaimAuditLog.objects.create(
                    claim=claim,
                    action=audit_msg,
                    performed_by=request.user
                )
            else:
                ClaimAuditLog.objects.create(
                    claim=claim,
                    action=f"AI Pipeline processed with errors: {pipeline_res.get('message', 'Unknown Error')}. Defaulting to manual audit.",
                    performed_by=request.user
                )
        except Exception as e:
            ClaimAuditLog.objects.create(
                claim=claim,
                action=f"AI Pipeline CRITICAL ERROR: {str(e)}",
                performed_by=request.user
            )

        ClaimAuditLog.objects.create(
            claim=claim,
            action="Claim submitted and documents uploaded",
            performed_by=request.user
        )

        create_notification(
            user=request.user,
            title="Claim Submitted Successfully",
            message=f"Your claim {claim.claim_number} has been submitted and is now under review.",
            type="success",
            related_claim_id=claim.public_id,
        )

        messages.success(request, f"Claim submitted successfully. Ref: {claim.claim_number}")

        return redirect("claim:detail", id=claim.public_id)

    return render(request, "claims/claim_submit.html", {"policies": policies})


# =====================================
# CLAIM DETAIL
# =====================================

@login_required
def claim_detail(request, id):
    claim = _get_claim_by_public_id_or_404(id)

    if not (request.user.is_superuser or request.user.role in ["admin", "staff"]):
        if not user_can_access_claim(request.user, claim):
            return render(request, "accounts/unauthorized.html")

    # If it's a staff user, redirect to the enhanced staff assessment workflow 
    # ONLY if the claim is in a state that requires active review.
    if request.user.role == 'staff' and not request.user.is_superuser:
        if claim.status in ['submitted', 'under_review', 'investigation']:
            return redirect('claim:staff_review', id=claim.public_id)

    # 💰 Compute authoritative AI recommendation via service
    from claims.services import ClaimPayoutService
    computed_ai_recommendation = ClaimPayoutService.get_authoritative_payout(claim)
    breakdown = ClaimPayoutService.get_breakdown_context(claim)

    return render(request, "claims/claim_detail.html", {
        "claim": claim,
        "computed_ai_recommendation": computed_ai_recommendation,
        "breakdown": breakdown,
    })


# =====================================
# EDIT CLAIM
# =====================================

@login_required
def claim_edit(request, id):
    claim = _get_claim_by_public_id_or_404(id)

    if not (request.user.is_superuser or request.user.role in ["admin", "staff"]):
        if not user_can_access_claim(request.user, claim):
            return render(request, "accounts/unauthorized.html")

    if request.method == "POST":
        # Update claim fields
        claim.claim_type = request.POST.get("claim_type")
        claim.incident_date = request.POST.get("incident_date")
        claim.description = request.POST.get("description")
        claim.claimed_amount = safe_money(request.POST.get("claimed_amount"))
        claim.save()

        ClaimAuditLog.objects.create(
            claim=claim,
            action="Claim updated",
            performed_by=request.user
        )

        messages.success(request, "Claim updated successfully")
        return redirect("claim:detail", id=claim.public_id)

    return render(request, "claims/claim_edit.html", {"claim": claim})


# =====================================
# DELETE CLAIM
# =====================================

@login_required
def claim_delete(request, id):
    claim = _get_claim_by_public_id_or_404(id)

    if not (request.user.is_superuser or request.user.role in ["admin", "staff"]):
        return render(request, "accounts/unauthorized.html")

    if request.method == "POST":
        claim.delete()
        messages.success(request, "Claim deleted successfully")
        return redirect("claim:list")

    return render(request, "claims/claim_delete.html", {"claim": claim})


# =====================================
# REVIEW CLAIM
# =====================================

@staff_or_admin
def staff_claim_review(request, id):
    """
    Dedicated review page for Staff users.
    Allows: Adding comments, Forwarding to Admin (under_review), Rejecting.
    Restrictions: Cannot Mark as Settled.
    """
    claim = _get_claim_by_public_id_or_404(id)

    # ── WORKFLOW STATE SYNC ──────────────────────────────────────────────
    # Requirement: submitted -> under_review -> staff_reviewed (No skips allowed)
    if claim.status == "submitted" and request.user.role in ["staff", "admin"]:
        claim.status = "under_review"
        claim.save(update_fields=["status"])
        ClaimAuditLog.objects.create(
            claim=claim,
            action="Workflow Initialization",
            description="Process initiated: Dossier automatically moved to 'under_review' stage.",
            performed_by=request.user
        )
    
    # ── AUTO-ASSIGNMENT LOGIC ───────────────────────────────────────────
    # If the dossier is unassigned and a staff member initiates the review, 
    # we dynamically bind them as the lead auditor for audit traceability.
    if not claim.assigned_to and request.user.role == 'staff':
        claim.assigned_to = request.user
        claim.assigned_at = timezone.now()
        # Save with skip_workflow_check=True because we aren't changing the claim status yet
        claim.save(update_fields=['assigned_to', 'assigned_at'], skip_workflow_check=True)
        
        ClaimAuditLog.objects.create(

            claim=claim,
            action="Lead Auditor Binding",
            description=f"System automatically assigned dossier processing to {request.user.get_full_name() or request.user.username}.",
            performed_by=request.user
        )


    # Requirement 3: Edit Lock After Staff Review
    if claim.status == "staff_reviewed" and request.user.role == "staff":
        messages.error(request, "🛡️ Regulatory Lock: This dossier is under Admin review and cannot be modified by Staff.")
        return redirect("accounts:staff_dashboard")

    if request.method == "POST":
        action = request.POST.get("action")
        comment = request.POST.get("comment", "").strip()
        new_claim_type = request.POST.get("claim_type")
        new_approved_amount = request.POST.get("approved_amount")
        manual_override = request.POST.get("manual_override") == "on"
        override_reason = request.POST.get("override_reason", "").strip()
        staff_rec = request.POST.get("staff_recommendation")

        # ── PHASE 5: PAYOUT BASIS SELECTION (Enterprise Payout Engine) ──────
        basis_selection = request.POST.get("payout_basis_selection")
        if basis_selection in ["DECLARED", "OCR", "MANUAL"]:
            manual_val = request.POST.get("manual_payout_amount")
            try:
                _apply_integrity_basis_selection(
                    claim,
                    basis_selection,
                    manual_amount=manual_val if basis_selection == "MANUAL" else None,
                    performed_by=request.user,
                    persist_audit=True,
                )
            except ValueError as exc:
                messages.error(request, str(exc))
                return redirect("claim:staff_review", id=claim.public_id)

        # 0. Safety Sync: Ensure we aren't bypassing under_review
        if claim.status == "submitted":
            claim.status = "under_review"
            claim.save(update_fields=["status"])

        # 1. Update Editable Fields
        if new_claim_type and new_claim_type != claim.claim_type:
            claim.claim_type = new_claim_type
            ClaimAuditLog.objects.create(claim=claim, performed_by=request.user, action="Field Update", description=f"Updated claim type to {new_claim_type}")

        claim.manual_override = manual_override
        if manual_override:
            if not override_reason and action in ["approve", "submit_to_admin"]:
                messages.error(request, "🚨 GOVERNANCE VIOLATION: A justification reason is mandatory for manual overrides.")
                return redirect("claim:staff_review", id=claim.public_id)
            claim.override_reason = override_reason

        net_claimable = max(Decimal('0'), safe_money(claim.claimed_amount) - safe_money(claim.deductible_amount))
        if new_approved_amount:
            try:
                dec_amount = safe_money(new_approved_amount)
                if dec_amount > net_claimable:
                    messages.error(request, f"Exceeds Net Claimable ceiling (₹{net_claimable:,.2f})")
                    return redirect("claim:staff_review", id=claim.public_id)
                claim.approved_amount = dec_amount
            except: pass

        # 2. Add Review Evidence
        if comment:
            ClaimNote.objects.create(claim=claim, created_by=request.user, message=comment)

        # 3. Decision Processing & Governance Chaining
        if action in ["approve", "reject", "submit_to_admin"]:
            
            # REQUIREMENT 2: Staff Decision Persistence & Performance Tracking
            if request.user.role == 'staff':
                final_decision = 'MODIFY' # Default logic for investigation/unknown
                if action == "approve": final_decision = 'APPROVE'
                elif action == "reject": final_decision = 'REJECT'
                elif staff_rec: final_decision = 'APPROVE' if staff_rec == 'APPROVE' else ('REJECT' if staff_rec == 'REJECT' else 'MODIFY')

                # Update Claim State
                if action == "submit_to_admin":
                    if not staff_rec:
                        messages.error(request, "Governance Error: You must select a formal recommendation (Approve/Reject/Review) before submitting to Administration.")
                        return redirect("claim:staff_review", id=claim.public_id)
                    claim.staff_recommendation = staff_rec
                    claim.staff_notes = comment or "Audit complete. Transferred for finalization."
                    claim.status = "staff_reviewed"
                else:
                   # For direct approve/reject (if enabled for staff)
                   claim.status = "approved" if action == "approve" else ("rejected" if action == "reject" else claim.status)

                # 🎯 RECORD AUDITOR PERFORMANCE DATA
                from .models import AuditorReview
                AuditorReview.objects.update_or_create(
                    claim=claim,
                    auditor=request.user,
                    defaults={
                        'decision': final_decision,
                        'recommended_amount': claim.approved_amount or claim.final_ai_recommendation or 0,
                        'ai_original_amount': claim.final_ai_recommendation or 0,
                        'throughput_value': safe_money(claim.claimed_amount),
                        'assigned_at': claim.assigned_at or claim.created_at,
                        'reviewed_at': timezone.now()
                    }
                )
                
                # 🤖 SYNC HUMAN FEEDBACK TO AI HISTORY
                from .models import ClaimAIHistory
                latest_history = ClaimAIHistory.objects.filter(claim=claim).first()
                if latest_history:
                    latest_history.human_decision = final_decision
                    latest_history.human_amount = claim.approved_amount or claim.final_ai_recommendation or 0
                    latest_history.is_disputed = (abs((latest_history.ai_recommendation or 0) - (latest_history.human_amount or 0)) > 100)
                    latest_history.save()
                
                # 🛡️ Governance Debug Check
                print(f"📊 WORKFLOW SYNC: AuditorReview archived. Current Ledger Count: {AuditorReview.objects.count()}")

                ClaimAuditLog.objects.create(
                    claim=claim, performed_by=request.user, 
                    action="TRANSFERRED_TO_INVESTIGATION" if action == "submit_to_admin" else action.upper(), 
                    description=f"Initial audit complete. Decision/Rec: {final_decision}. Notes: {comment[:100]}..."
                )

            # REQUIREMENT 4: Admin Override Accountability
            elif request.user.role == 'admin':
                decision_mapped = "APPROVE" if action == "approve" else "REJECT"
                if claim.staff_recommendation and decision_mapped != claim.staff_recommendation:
                    claim.admin_override = {
                        "decision": decision_mapped,
                        "original_rec": claim.staff_recommendation,
                        "reason": comment or "Administrative policy directive override.",
                        "timestamp": timezone.now().isoformat(),
                        "admin_id": request.user.id
                    }
                    logger.warning(f"⚖️ Admin Override Tracked: Claim {claim.claim_number} | {claim.staff_recommendation} -> {decision_mapped}")

                claim.status = "approved" if action == "approve" else "rejected"
                ClaimAuditLog.objects.create(
                    claim=claim, performed_by=request.user, 
                    action="APPROVED" if action == "approve" else "REJECTED",
                    description=f"Final management decision: {action.upper()}." + (f" (OVERRIDE: {comment})" if claim.admin_override else "")
                )

            # ── REQUIREMENT 5: FORMAL ASSESSMENT PERSISTENCE ──
            # Record/Update the formal assessment dossier for compliance reporting
            ClaimAssessment.objects.update_or_create(
                claim=claim,
                defaults={
                    'assessed_by': request.user,
                    'assessed_on': timezone.now().date(),
                    'verdict': 'approved' if action == "approve" else ("rejected" if action == "reject" else "pending"),
                    'bill_amount': claim.bill_amount or claim.ocr_verified_bill_total or claim.claimed_amount,
                    'coverage': Decimal('100.0'), # Standard coverage
                    'deductible': claim.deductible_amount or Decimal('0'),
                    'recommended_amount': claim.approved_amount or claim.final_ai_recommendation or Decimal('0'),
                    'remarks': comment or claim.staff_notes or "Dossier assessment complete.",
                    'investigation_required': (claim.status == "investigation")
                }
            )

            # Finalize Persistence
            try:
                claim.save(user=request.user)
                messages.success(request, f"Dossier {claim.claim_number} successfully transitioned to {claim.get_status_display().upper()}.")
                return redirect("accounts:admin_dashboard" if request.user.role == 'admin' else "accounts:staff_dashboard")
            except ValidationError as e:
                messages.error(request, str(e))
                return redirect("claim:staff_review", id=claim.public_id)

        elif action == "flag":
            claim.status = "investigation"
            ClaimAuditLog.objects.create(claim=claim, performed_by=request.user, action="INVESTIGATION", description="Claim flagged for deep investigation.")
            msg = "submitted to Admin"
            audit_msg = "Claim submitted to Admin for final settlement/review."
        elif action == "reject":
            # Edge case: If claimed_amount < deductible, we should also reject
            claim.status = "rejected"
            msg = "rejected"
            audit_msg = "Claim rejected by staff."
        else:
            msg = None

        try:
            claim.save(user=request.user)
        except ValidationError as e:
            msg = ", ".join(e.messages) if hasattr(e, 'messages') else str(e)
            messages.error(request, f"Workflow Restriction: {msg}")
            return redirect("claim:staff_review", id=claim.public_id)

        if msg:
            ClaimAuditLog.objects.create(
                claim=claim,
                performed_by=request.user,
                action=audit_msg
            )
            messages.success(request, f"Claim {claim.claim_number} has been {msg}.")
            return redirect("accounts:staff_dashboard")
        
        elif action == "comment_only":
            messages.success(request, "Changes and comment saved successfully.")
            return redirect("claim:staff_review", id=claim.public_id)

    # Context for rendering
    days_since_incident = (timezone.now().date() - claim.incident_date).days
    net_claimable = max(Decimal('0'), safe_money(claim.claimed_amount) - safe_money(claim.deductible_amount))
    
    # Validation logic (reusing existing one)
    user_policy = get_claim_subject_user_policy(claim)
    policy_active = False
    if user_policy and user_policy.status == 'active':
        policy_active = True
    
    # Dynamic AI Refresh (If missing)
    if not claim.final_ai_recommendation:
        try:
            from claims.services import ClaimPayoutService
            computed = predict_recommended_amount(claim)
            claim.final_ai_recommendation = safe_money(computed)
            if not claim.initial_ai_prediction:
                claim.initial_ai_prediction = claim.final_ai_recommendation
            claim.save(update_fields=['final_ai_recommendation', 'initial_ai_prediction'])
        except Exception:
            claim.final_ai_recommendation = safe_money(float(claim.claimed_amount) * 0.85)
    
    # Refresh Fraud Risk if missing
    if not claim.fraud_explanation:
        try:
            predict_fraud_risk(claim)
            claim.save(update_fields=['risk_score', 'fraud_flag', 'fraud_explanation'])
        except Exception:
            pass

    # Refresh AI Classification if missing
    if not claim.ai_claim_type:
        try:
            ai_type, confidence = predict_claim_type(claim.description)
            claim.ai_claim_type = ai_type
            claim.confidence_score = confidence * 100
            claim.save(update_fields=['ai_claim_type', 'confidence_score'])
        except Exception:
            pass

    # Refresh OCR bill extraction from the stored dossier text/documents.
    if claim.documents.exists():
        try:
            from ai_features.services.ocr_service import OCRService

            ocr_service = OCRService()
            extracted_chunks = []
            financial_doc_types = {"hospital_bill", "repair_bill", "other"}
            prioritized_documents = list(claim.documents.filter(document_type__in=financial_doc_types))

            if not prioritized_documents:
                prioritized_documents = list(claim.documents.all())

            for document in prioritized_documents:
                if not document.file:
                    continue
                try:
                    text_chunk = ocr_service.extract_text(document.file.path)
                except Exception:
                    text_chunk = ""
                if text_chunk:
                    extracted_chunks.append(text_chunk)

            consolidated_ocr_text = "\n\n--- DOCUMENT BOUNDARY ---\n\n".join(extracted_chunks).strip()
            if not consolidated_ocr_text:
                consolidated_ocr_text = (claim.ocr_text or "").strip()

            if consolidated_ocr_text:
                ocr_details = ocr_service.extract_claim_details(consolidated_ocr_text)
                extracted_total = safe_money(ocr_details.get("total_amount") or "0")

                updates = {}
                if consolidated_ocr_text != (claim.ocr_text or ""):
                    updates["ocr_text"] = consolidated_ocr_text
                    claim.ocr_text = consolidated_ocr_text

                if extracted_total > 0 and extracted_total != safe_money(claim.bill_amount or 0):
                    updates["bill_amount"] = extracted_total
                    claim.bill_amount = extracted_total

                if updates:
                    Claim.objects.filter(pk=claim.pk).update(**updates)
        except Exception:
            pass
            
    subject_user = claim.user_policy.user if claim.user_policy_id and claim.user_policy and claim.user_policy.user_id else claim.created_by
    subject_display_name = "System"
    if subject_user:
        subject_display_name = (
            subject_user.get_full_name().strip()
            if hasattr(subject_user, "get_full_name") and subject_user.get_full_name()
            else getattr(subject_user, "username", "System")
        ) or "System"

    policy_display_number = ""
    if claim.user_policy_id and claim.user_policy and claim.user_policy.policy_id and claim.user_policy.policy:
        policy_display_number = claim.user_policy.policy.policy_number or ""
    elif getattr(claim, "policy_id", None) and getattr(claim, "policy", None):
        policy_display_number = claim.policy.policy_number or ""

    certificate_display_number = ""
    if claim.user_policy_id and claim.user_policy:
        certificate_display_number = claim.user_policy.certificate_number or ""

    # 📊 AUDIT: Generate Unified Financial Calculation Breakdown (SSoT)
    from claims.services.claim_review_service import ClaimReviewService
    review_payload = ClaimReviewService.get_review_payload(claim)

    context = {
        "claim": claim,
        "days_since_incident": days_since_incident,
        "net_claimable": net_claimable,
        "policy_active": policy_active,
        "subject_display_name": subject_display_name,
        "policy_display_number": policy_display_number,
        "certificate_display_number": certificate_display_number,
        "documents": claim.documents.all(),
        "notes": claim.notes.all().order_by('-created_at'),
        "audit_logs": claim.audit_logs.all().order_by('-created_at'),
        "claim_history_count": Claim.objects.filter(created_by=claim.created_by).exclude(id=claim.id).count(),
        "review_payload": review_payload,
        "breakdown": review_payload # Keep for backward compatibility with existing templates if needed
    }

    return render(request, "claims/staff_claim_review.html", context)


@admin_only
def claim_review(request, id):
    claim = _get_claim_by_public_id_or_404(id)

    if request.method == "POST":
        action = request.POST.get("action")
        comment = request.POST.get("admin_comment", "").strip()

        if action == "approve":
            claim.status = "approved"
            
            # 🛡️ Synchronize Financial SSoT (Single Source of Truth) before final archival
            from claims.services.claim_review_service import ClaimReviewService
            
            try:
                review_payload = ClaimReviewService.get_review_payload(claim)
                claim.approved_amount = Decimal(str(review_payload.get("final_amount", 0)))
                claim.save(user=request.user)
                
                ClaimAuditLog.objects.create(
                    claim=claim,
                    performed_by=request.user,
                    action="FINAL_APPROVAL",
                    description=f"Claim FINAL APPROVED by Admin. Rationale: {comment}" if comment else "Claim FINAL APPROVED by Admin."
                )
                # ── REQUIREMENT 5: FINAL ASSESSMENT PERSISTENCE (Admin) ──
                ClaimAssessment.objects.update_or_create(
                    claim=claim,
                    defaults={
                        'assessed_by': request.user,
                        'assessed_on': timezone.now().date(),
                        'verdict': 'approved',
                        'recommended_amount': claim.approved_amount,
                        'remarks': comment or "Final Administrative Approval.",
                        'investigation_required': False
                    }
                )

                messages.success(request, f"Claim {claim.claim_number} has been approved. Dossier has been moved to the Settlement Queue.")
                return redirect("claim:settlement_queue")
            except ValidationError as e:
                msg = ", ".join(e.messages) if hasattr(e, 'messages') else str(e)
                messages.error(request, f"Workflow Restriction: {msg}")
                return redirect("claim:review", id=claim.public_id)
            
        elif action == "reject":
            claim.status = "rejected"
            try:
                claim.save(user=request.user)
                ClaimAuditLog.objects.create(
                    claim=claim,
                    performed_by=request.user,
                    action="FINAL_REJECTION",
                    description=f"Claim FINAL REJECTED by Admin. Rationale: {comment}" if comment else "Claim FINAL REJECTED by Admin."
                )
                # ── REQUIREMENT 5: FINAL ASSESSMENT PERSISTENCE (Admin Rejection) ──
                ClaimAssessment.objects.update_or_create(
                    claim=claim,
                    defaults={
                        'assessed_by': request.user,
                        'assessed_on': timezone.now().date(),
                        'verdict': 'rejected',
                        'recommended_amount': 0,
                        'remarks': comment or "Final Administrative Rejection.",
                        'investigation_required': False
                    }
                )

                messages.success(request, f"Claim {claim.claim_number} has been rejected.")
                return redirect("claim:review", id=claim.public_id)
            except ValidationError as e:
                msg = ", ".join(e.messages) if hasattr(e, 'messages') else str(e)
                messages.error(request, f"Workflow Restriction: {msg}")
                return redirect("claim:review", id=claim.public_id)

    # 📊 Calculate derived view data
    days_since_incident = (timezone.now().date() - claim.incident_date).days
    
    # Financials
    net_claimable = max(Decimal('0'), safe_money(claim.claimed_amount) - safe_money(claim.deductible_amount))
    
    # ── IDENTIFY THE TRUE POLICYHOLDER (Subject of Claim) ───────────────
    # 1. Start with the account that recorded the claim
    subject_user = claim.user_policy.user if claim.user_policy_id else claim.created_by
    self_claimant = claim.claimants.filter(relationship='self').first()
    
    # 2. If recorded by staff, prioritize the linked identity from 'self' claimants
    if self_claimant and self_claimant.email:
        from django.contrib.auth import get_user_model
        User = get_user_model()
        potential_subj = User.objects.filter(email=self_claimant.email).first()
        if potential_subj:
            subject_user = potential_subj
    
    # 3. If subject is STILL a staff/admin, we must find the actual Policyholder 
    # who owns this policy instance (UserPolicy).
    if subject_user and (subject_user.is_superuser or subject_user.role in ['admin', 'staff']):
        # If it's a Motor policy, we can match by vehicle number for highest precision
        if claim.vehicle_number:
            owner_policy = UserPolicy.objects.filter(policy=claim.policy, vehicle_number=claim.vehicle_number).first()
            if owner_policy:
                subject_user = owner_policy.user
        
        # If still not found, find ANY user policy for this plan that isn't held by an admin/staff
        if not subject_user or subject_user.role in ['admin', 'staff']:
            owner_policy = UserPolicy.objects.filter(policy=claim.policy).exclude(user__role__in=['admin', 'staff']).first()
            if owner_policy:
                subject_user = owner_policy.user

    # ── POLICY VALIDITY CHECK (Based on subject_user) ────────────────────
    policy_active_on_incident = False
    user_policy = get_claim_subject_user_policy(claim)

    if user_policy:
        if user_policy.status == 'active':
            policy_active_on_incident = True
        elif user_policy.start_date and user_policy.end_date:
            import datetime
            # Grace period fallback (usually 30 days)
            effective_start = user_policy.start_date - datetime.timedelta(days=30)
            if effective_start <= claim.incident_date <= user_policy.end_date:
                policy_active_on_incident = True
    else:
        # Fallback for legacy PolicyHolder if no UserPolicy exists
        if PolicyHolder.objects.filter(user=subject_user, policy=claim.policy).exists():
            policy_active_on_incident = True

    # Ensure Risk Analysis exists for admin review
    if not claim.fraud_explanation:
        try:
            predict_fraud_risk(claim)
            claim.save(update_fields=['risk_score', 'fraud_flag', 'fraud_explanation'])
        except Exception:
            pass

    # Refresh AI Classification if missing
    if not claim.ai_claim_type:
        try:
            ai_type, confidence = predict_claim_type(claim.description)
            claim.ai_claim_type = ai_type
            claim.confidence_score = confidence * 100
            claim.save(update_fields=['ai_claim_type', 'confidence_score'])
        except Exception:
            pass

    # 📊 AUDIT: Generate Unified Financial Calculation Breakdown (SSoT)
    from claims.services.claim_review_service import ClaimReviewService
    review_payload = ClaimReviewService.get_review_payload(claim)

    context = {
        "claim": claim,
        "applicant": subject_user,
        "subject_user": subject_user,
        "days_since_incident": days_since_incident,
        "net_claimable": net_claimable,
        "policy_active_on_incident": policy_active_on_incident,
        "documents": claim.documents.all().order_by("-uploaded_at"),
        "claim_history_count": Claim.objects.filter(created_by=subject_user).exclude(id=claim.id).count(),
        "notes": claim.notes.select_related("created_by").all().order_by('-created_at'),
        "audit_logs": claim.audit_logs.select_related("performed_by").all().order_by('-created_at'),
        "show_full_data": request.user.is_superuser,
        "masked_email": mask_email(subject_user.email if subject_user else ""),
        "masked_phone": mask_phone(subject_user.phone if subject_user else ""),
        "review_payload": review_payload,
        "breakdown": review_payload, # Backwards compatibility
    }

    return render(request, "claims/admin_review.html", context)


# =====================================
# CLAIM HISTORY
# =====================================

@login_required
def claim_history(request, claim_id):
    claim = _get_claim_by_public_id_or_404(claim_id)

    # 🛡️ Access Control: Staff/Admin see all. Users see only their own.
    if not (request.user.role in ['admin', 'staff'] or request.user.is_superuser):
        if not user_can_access_claim(request.user, claim):
            return render(request, "accounts/unauthorized.html")

    history = ClaimAuditLog.objects.filter(claim=claim).order_by('-created_at')
    return render(request, "claims/claim_history.html", {"claim": claim, "history": history})


# =====================================
# CLAIM SETTLEMENT
# =====================================

@admin_only
def claim_settlement(request, claim_id):
    """
    Final settlement and financial payout processing.
    Reserved for Admin role to ensure strictly controlled financial distribution.
    """
    claim = _get_claim_by_public_id_or_404(claim_id)
    
    # 🛡️ Workflow Safety: Settlement can ONLY proceed from 'approved' state
    if claim.status != 'approved':
        messages.error(request, f"Workflow Violation: Claim {claim.claim_number} is currently '{claim.get_status_display()}'. Dossiers must be FINAL APPROVED before settlement can be initiated.")
        return redirect("claim:review", id=claim.public_id)

    # 🛡️ Safety Guard: Prevent Duplicate Settlement Records (OneToOne Constraint)
    if hasattr(claim, 'settlement'):
        messages.warning(request, f"Record Integrity Check: A settlement dossier already exists for claim {claim.claim_number}. Operation halted to prevent duplicates.")
        return redirect("claim:detail", id=claim.public_id)

    if request.method == "POST":
        # Use automatic Ledger ID generation logic from Payment model (TXN-SETL prefix)
        # We will no longer generate manual 'SETL-' strings here unless overridden by Admin
        # If admin provides a reference (like a Cheque No), we still keep it in gateway_reference
        txn_ref = request.POST.get("reference", "").strip()

        # Read the FINAL result from the form (Admin might have edited it)
        try:
            manual_settled_amount = safe_money(request.POST.get("settled_amount", "0"))
        except (InvalidOperation, TypeError):
            manual_settled_amount = Decimal('0')

        # Determine default final payable using standardized fallback (Staff > AI > Claimed)
        from claims.services import ClaimPayoutService
        staff_val = claim.approved_amount or claim.recommended_amount or Decimal('0')
        ai_val = ClaimPayoutService.get_authoritative_payout(claim)
        base_assessment = staff_val if staff_val > 0 else ai_val
        if base_assessment <= 0:
            base_assessment = safe_money(claim.claimed_amount)
            
        default_final_payable = min(base_assessment, claim.net_claimable)

        # 🛡️ PRIORITIZE the manual edited amount from Admin, if provided and valid (>0)
        # Otherwise fallback to the system calculated default_final_payable
        final_payable = manual_settled_amount if manual_settled_amount > 0 else default_final_payable
        
        # 🛡️ MANDATORY SAFETY CHECK: Payout cannot EXCEED Net Claimable
        if final_payable > claim.net_claimable:
            messages.error(request, f"Financial Block: Final payout (₹{final_payable:,.2f}) cannot exceed Net Claimable ceiling (₹{claim.net_claimable:,.2f}).")
            return redirect("claim:settlement", claim_id=claim.public_id)
        
        # 🔍 Debug Logging for Financial Trace (as requested by USER)
        print(f"DEBUG — SETTLEMENT START: Claim {claim.claim_number}")
        print(f"CLAIMED: {claim.claimed_amount}")
        print(f"APPROVED: {claim.approved_amount}")
        print(f"SETTLED (FINAL): {final_payable}")
        print(f"LIMIT (NET): {claim.net_claimable}")

        txn_ref = request.POST.get("transaction_reference") or get_random_string(12).upper()

        # 🛡️ Use atomic transaction to ensure financial consistency
        # 🛡️ Use atomic transaction to ensure financial consistency
        try:
            with transaction.atomic():
                # Create settlement record
                settlement = ClaimSettlement.objects.create(
                    claim=claim,
                    settlement_date=request.POST.get("settlement_date") or timezone.now().date(),
                    payment_mode=request.POST.get("payment_mode", "neft"),
                    transaction_reference=txn_ref,
                    settled_amount=final_payable, # MUST be approved_amount
                    payee_name=request.POST.get("payee_name", ""),
                    bank_account=request.POST.get("bank_account", ""),
                    bank_ifsc=request.POST.get("bank_ifsc", ""),
                    bank_name=request.POST.get("bank_name", ""),
                    remarks=request.POST.get("remarks", ""),
                    processed_by=request.user
                )

                # Update claim status and sync financial fields
                claim.status = "settled"
                claim.settled_amount = final_payable
                
                # 🔄 Final Save (Workflow Validated)
                claim.save(user=request.user)

                # 🔗 Real Insurance Lifecycle Sync: Update UserPolicy status
                user_policy = get_claim_subject_user_policy(claim)
                if user_policy:
                    user_policy.sync_status_with_premiums()

                ClaimAuditLog.objects.create(
                    claim=claim,
                    action=f"Claim settled through {request.POST.get('payment_mode', 'standard')} channel. Reference: {txn_ref}",
                    performed_by=request.user
                )

                # 💸 Sync with Unified Ledger: Create Payment entry for the payout (DEBIT)
                Payment.objects.create(
                    user=user_policy.user if user_policy else claim.created_by,
                    user_policy=user_policy,
                    claim=claim,
                    amount=final_payable,
                    payment_status='completed',
                    payment_type='CLAIM_SETTLEMENT',
                    direction='DEBIT',
                    payment_method=request.POST.get("payment_mode", "neft").lower(),
                    transaction_id="", # Model generates TXN-SETL- ID
                    gateway_reference=txn_ref,
                    description=f"Claim Payout Settlement - {claim.claim_number}",
                    notes=f"Processed by {request.user.username}."
                )

                # 🛡️ Record activity in system ledger for Admin Analytics
                ActivityLog.objects.create(
                    title=f"Claim Payout Dispatched: #{claim.claim_number}",
                    description=f"Payment of ₹{final_payable:,.2f} finalized for {claim.created_by.username}. Txn: {txn_ref}",
                    log_type='payment',
                    status='success',
                    user=request.user,
                    claim=claim
                )

                # 🔔 Success Notification to Policyholder
                try:
                    from notifications.utils import create_notification
                    if claim.created_by:
                        create_notification(
                            user=claim.created_by,
                            title="Payout Dispatched: Claim Settled",
                            message=f"Financial settlement for claim {claim.claim_number} is complete. Your payout of ₹{final_payable:,.2f} has been processed via {request.POST.get('payment_mode', 'standard').upper()}.",
                            notification_type="success",
                            priority="low"
                        )
                except:
                    pass

        except ValidationError as e:
            msg = ", ".join(e.messages) if hasattr(e, 'messages') else str(e)
            messages.error(request, f"Financial Workflow Error: {msg}. Settlement rolled back.")
            return redirect("claim:settlement", claim_id=claim.public_id)
        except Exception as e:
            messages.error(request, f"System Integrity Error: {str(e)}. Payout distribution aborted.")
            return redirect("claim:settlement", claim_id=claim.public_id)

        messages.success(request, f"Settlement Successful! Payout of ₹{final_payable:,.2f} has been dispatched for claim {claim.claim_number}.")
        return redirect("claim:detail", id=claim.public_id)

    # Calculate the INITIAL final payable for the template display
    from claims.services import ClaimPayoutService
    staff_val = claim.approved_amount or claim.recommended_amount or Decimal('0')
    ai_val = ClaimPayoutService.get_authoritative_payout(claim)
    base_assessment = staff_val if staff_val > 0 else ai_val
    if base_assessment <= 0:
        base_assessment = safe_money(claim.claimed_amount)
    
    final_payable = min(base_assessment, claim.net_claimable)

    context = {
        "claim": claim,
        "final_payable": final_payable,
        "net_claimable": claim.net_claimable
    }

    return render(request, "claims/claim_settlement.html", context)


@admin_only
def admin_settlement_queue(request):
    """
    Centralized dashboard for Admins to view and process all approved claims 
    that are pending final financial settlement.
    """
    # Base queryset for approved claims
    approved_claims = Claim.objects.filter(status='approved').select_related(
        'policy', 'created_by', 'user_policy'
    ).order_by('-updated_at')

    # 🩹 DATA RECONCILIATION: Self-healing for legacy/leaky financial data
    from claims.services.claim_review_service import ClaimReviewService
    
    for claim in approved_claims:
        # If approved_amount is missing but dossier is approved, we MUST restore from SSoT
        if claim.approved_amount is None or claim.approved_amount == 0:
            try:
                payload = ClaimReviewService.get_review_payload(claim)
                claim.approved_amount = Decimal(str(payload.get("final_amount", 0)))
                # Save without triggering full clean to avoid workflow side-effects
                claim.save(update_fields=['approved_amount'])
            except Exception as e:
                print(f"Failed to reconcile financials for {claim.claim_number}: {e}")

    # Statistics for the queue (Recalculated after healing)
    stats = {
        'total_pending': approved_claims.count(),
        'total_value': approved_claims.aggregate(Sum('approved_amount'))['approved_amount__sum'] or 0,
        'high_value_count': approved_claims.filter(approved_amount__gt=50000).count(),
        'oldest_pending': approved_claims.order_by('updated_at').first().updated_at if approved_claims.exists() else None,
    }

    # Search and Filter
    query = request.GET.get('q', '')
    if query:
        approved_claims = approved_claims.filter(
            Q(claim_number__icontains=query) | 
            Q(created_by__username__icontains=query) |
            Q(policy__policy_number__icontains=query)
        )

    context = {
        'claims': approved_claims,
        'stats': stats,
        'query': query,
    }

    return render(request, "claims/admin_settlement_queue.html", context)


# =====================================
# DOCUMENT UPLOAD
# =====================================

@login_required
def upload_claim_document(request, claim_id):
    claim = _get_claim_by_public_id_or_404(claim_id)

    if not (request.user.is_superuser or request.user.role in ["admin", "staff"]):
        if not user_can_access_claim(request.user, claim):
            return render(request, "accounts/unauthorized.html")

    if request.method == "POST" and request.FILES.get("file"):
        document = ClaimDocument.objects.create(
            claim=claim,
            document_type=request.POST.get("document_type", "other"),
            description=request.POST.get("description", ""),
            file=request.FILES["file"],
            uploaded_by=request.user
        )

        messages.success(request, "Document uploaded successfully")
        return redirect("claim:detail", id=claim.public_id)

    return render(request, "claims/document_upload.html", {"claim": claim})


# =====================================
# DOCUMENT DELETE
# =====================================

@login_required
def delete_claim_document(request, id):
    document = _get_claim_document_by_public_id_or_404(id)

    if not (request.user.is_superuser or request.user.role in ["admin", "staff"]):
        if not user_can_access_claim(request.user, document.claim):
            return render(request, "accounts/unauthorized.html")

    if request.method == "POST":
        document.delete()
        messages.success(request, "Document deleted successfully")
        return redirect("claim:detail", id=document.claim.public_id)

    return render(request, "claims/document_delete.html", {"document": document})


# =====================================
# NOTE DELETE
# =====================================

@login_required
def delete_claim_note(request, note_id):
    """
    Removes a note from the discussion history. 
    Maintains lead auditor override permissions.
    """
    note = get_object_or_404(ClaimNote, id=note_id)

    if not (request.user.is_superuser or request.user.role in ["admin", "staff"]):
        if not user_can_access_claim(request.user, note.claim):
            return render(request, "accounts/unauthorized.html")

    if request.method == "POST":
        # Audit trail creation BEFORE deletion for traceability
        ClaimAuditLog.objects.create(
            claim=note.claim,
            action="NOTE_DELETED",
            performed_by=request.user,
            description=f"Deleted note by {note.created_by.username} from {note.created_at}"
        )
        
        claim_id = note.claim.public_id
        note.delete()
        messages.info(request, "Audit note has been removed from discourse.")
        return redirect("claim:notes", claim_id=claim_id)

    return render(request, "claims/note_delete.html", {"note": note})


# =====================================
# CLAIM NOTES LIST
# =====================================

@login_required
def claim_notes_list(request, claim_id):
    """Returns a focused view of the discussion history for a claim."""
    claim = _get_claim_by_public_id_or_404(claim_id)

    if not (request.user.is_superuser or request.user.role in ["admin", "staff"]):
        if not user_can_access_claim(request.user, claim):
            return render(request, "accounts/unauthorized.html")

    notes = claim.notes.select_related('created_by').all().order_by('-created_at')
    
    # Pre-calculated context for the template to avoid complex template logic
    context = {
        "claim": claim,
        "notes": notes,
        "customer_notes": notes.filter(note_type='customer'),
        "internal_notes": notes.filter(note_type='internal'),
        "can_create_notes": True,
        "important_count": notes.filter(is_important=True).count(),
        "important_notes_count": notes.filter(is_important=True).count(), # For dashboard consistency
    }
    return render(request, "claims/claim_notes.html", context)


# =====================================
# EDIT CLAIM NOTE
# =====================================

@login_required
def edit_claim_note(request, note_id):
    note = get_object_or_404(ClaimNote, id=note_id)

    if not (request.user.is_superuser or request.user.role in ["admin", "staff"]):
        if not user_can_access_claim(request.user, note.claim):
            return render(request, "accounts/unauthorized.html")

    if request.method == "POST":
        note.message = request.POST.get("content") or request.POST.get("message", "")
        note.save()

        messages.success(request, "Note updated successfully")
        return redirect("claim:notes", claim_id=note.claim.public_id)

    return render(request, "claims/claim_notes_edit.html", {"note": note})


# =====================================
# MARK NOTE IMPORTANT
# =====================================

@login_required
def mark_note_important(request, note_id):
    note = get_object_or_404(ClaimNote, id=note_id)

    if not (request.user.is_superuser or request.user.role in ["admin", "staff"]):
        if not user_can_access_claim(request.user, note.claim):
            return render(request, "accounts/unauthorized.html")

    note.is_important = not note.is_important
    note.save()

    messages.success(request, "Note importance updated")
    return redirect("claim:notes", claim_id=note.claim.public_id)


# =====================================
# NOTES DASHBOARD
# =====================================

@login_required
@staff_or_admin
def notes_dashboard(request):
    """
    Centralized hub for all claim notes with filtering, statistics, and pagination.
    """
    # 1. Base Queryset
    notes = ClaimNote.objects.select_related("claim", "claim__policy", "created_by").order_by('-created_at')

    # 2. Extract and Apply Filters
    note_type = request.GET.get('note_type', '')
    is_important = request.GET.get('is_important', '')
    claim_number = request.GET.get('claim_number', '').strip()

    if note_type:
        notes = notes.filter(note_type=note_type)
    if is_important == 'true':
        notes = notes.filter(is_important=True)
    elif is_important == 'false':
        notes = notes.filter(is_important=False)
    if claim_number:
        notes = notes.filter(claim__claim_number__icontains=claim_number)

    # 3. Global Statistics (Unfiltered for overview)
    all_notes = ClaimNote.objects.all()
    stats = {
        'total_notes': all_notes.count(),
        'customer_notes_count': all_notes.filter(note_type='customer').count(),
        'internal_notes_count': all_notes.filter(note_type='internal').count(),
        'important_notes_count': all_notes.filter(is_important=True).count(),
        'unique_claims_count': all_notes.values('claim').distinct().count(),
    }

    # 4. Pagination
    # Using 15 items per page for optimized governance review
    paginator = Paginator(notes, 15)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'notes': page_obj,
        'note_type': note_type,
        'is_important': is_important,
        'claim_number': claim_number,
        **stats
    }

    return render(request, "claims/notes_dashboard.html", context)


# =====================================
# UPDATE STATUS
# =====================================

@login_required
def update_claim_status(request, id):
    claim = _get_claim_by_public_id_or_404(id)

    if request.method == "POST":
        status = request.POST.get("status")
        claim.status = status

        # Extracting additional fields from dashboard review form
        if 'staff_policy_validity' in request.POST:
            claim.policy_validity = request.POST.get('staff_policy_validity')
        elif 'policy_validity' in request.POST:
            claim.policy_validity = request.POST.get('policy_validity')

        if 'staff_document_verification' in request.POST:
            claim.document_verification = request.POST.get('staff_document_verification')
        elif 'document_verification' in request.POST:
            claim.document_verification = request.POST.get('document_verification')

        if 'staff_amount_verification' in request.POST:
            claim.amount_verification = request.POST.get('staff_amount_verification')
        elif 'amount_verification' in request.POST:
            claim.amount_verification = request.POST.get('amount_verification')

        if 'staff_comments' in request.POST:
            claim.staff_comments = request.POST.get('staff_comments')
        
        if 'recommended_amount' in request.POST:
            claim.recommended_amount = safe_money(request.POST.get('recommended_amount'), fallback=0)

        if status == "approved":
            # 🛡️ Real Insurance Financial Protocol: Honor the Net Claimable ceiling
            from claims.services import ClaimPayoutService
            
            staff_val = safe_money(claim.recommended_amount)
            ai_val = ClaimPayoutService.get_authoritative_payout(claim)
            
            # Use staff value if it exists and is non-zero, else fallback to AI
            base_assessment = staff_val if staff_val > 0 else ai_val
            
            # If still 0, fallback to total claimed amount
            if base_assessment <= 0:
                base_assessment = safe_money(claim.claimed_amount)
                
            # 2. Final payable logic: MIN(base_assessment, net_claimable)
            claim.approved_amount = min(base_assessment, claim.net_claimable)

        if status == "settled":
            # 🔄 Ensure settled amount perfectly mirrors approved benefits
            if not claim.approved_amount:
                from claims.services import ClaimPayoutService
                staff_val = safe_money(claim.recommended_amount)
                ai_val = ClaimPayoutService.get_authoritative_payout(claim)
                base_assessment = staff_val if staff_val > 0 else ai_val
                if base_assessment <= 0:
                    base_assessment = safe_money(claim.claimed_amount)
                claim.approved_amount = min(base_assessment, claim.net_claimable)
            
            claim.settled_amount = claim.approved_amount

        claim.save()

        # 🔔 Automation: Dispatch Notifications based on status change
        try:
            from notifications.utils import create_notification
            if status == "investigation":
                # Notify Admins of pending escalation
                from django.contrib.auth import get_user_model
                User = get_user_model()
                admins = User.objects.filter(role='admin')
                for admin in admins:
                    create_notification(
                        user=admin,
                        title="Audit Escalation: Final Review Required",
                        message=f"Staff {request.user.username} has submitted Claim {claim.claim_number} for final management review.",
                        notification_type="system",
                        priority="high"
                    )
                
                # 🎯 RECORD AUDITOR PERFORMANCE DATA (Analytics Bridge)
                from .models import AuditorReview
                AuditorReview.objects.update_or_create(
                    claim=claim,
                    auditor=request.user,
                    defaults={
                        'decision': 'APPROVE' if safe_money(claim.recommended_amount or 0) >= safe_money(claim.final_ai_recommendation or 0) else 'MODIFY',
                        'recommended_amount': claim.recommended_amount or claim.approved_amount or claim.final_ai_recommendation or 0,
                        'ai_original_amount': claim.final_ai_recommendation or 0,
                        'throughput_value': claim.claimed_amount,
                        'assigned_at': claim.assigned_at or claim.created_at,
                        'reviewed_at': timezone.now(),
                        'remarks': f"Manual status transition to {status.upper()}."
                    }
                )
                print(f"📊 WORKFLOW SYNC: AuditorReview archived during status transition. Count: {AuditorReview.objects.count()}")
            
            elif status == "settled":
                # Notify Policyholder of successful payout
                if claim.created_by:
                    create_notification(
                        user=claim.created_by,
                        title="Financial Settlement Complete",
                        message=f"Your claim {claim.claim_number} has been settled. A payout of ₹{claim.settled_amount:,.2f} was approved and processed.",
                        notification_type="success",
                        priority="low"
                    )
        except Exception:
            pass

        # Handle ClaimAssessment record if assessment_comments or specific assessment fields are provided
        assessment_remarks = request.POST.get('assessment_comments')
        if assessment_remarks:
            assessment, created = ClaimAssessment.objects.update_or_create(
                claim=claim,
                defaults={
                    'remarks': assessment_remarks,
                    'assessed_by': request.user,
                    'verdict': 'approved' if status == 'investigation' else status, # Mapping status to verdict loosely
                    'recommended_amount': claim.recommended_amount
                }
            )

        ClaimAuditLog.objects.create(
            claim=claim,
            action=f"Status updated to {status}. Logic Trace: [AI: ₹{claim.final_ai_recommendation or 0:,.2f}] [Staff Approved: ₹{claim.recommended_amount or 0:,.2f}] [Final Payout: ₹{claim.settled_amount or claim.approved_amount or 0:,.2f}]",
            performed_by=request.user
        )

    if request.user.role == "staff" and not request.user.is_superuser:
        return redirect("accounts:staff_dashboard")
    return redirect("accounts:admin_dashboard")



# =====================================
# DOCUMENT VIEW
# =====================================

@login_required
def view_claim_document(request, id):
    document = _get_claim_document_by_public_id_or_404(id)

    if not document.file:
        raise Http404()

    return FileResponse(document.file.open("rb"))


# =====================================
# NOTES
# =====================================



# =====================================
# ASSESSMENT
# =====================================

@login_required
def claim_assessment(request, claim_id):
    claim = _get_claim_by_public_id_or_404(claim_id)

    form = ClaimAssessmentForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        assessment = form.save(commit=False)
        assessment.claim = claim
        assessment.assessed_by = request.user
        assessment.save()

        messages.success(request, "Assessment saved")
        return redirect("claim:detail", id=claim.public_id)

    return render(request, "claims/claim_assessment.html", {"form": form, "claim": claim})


# =====================================
# INTERNAL DISCUSSION & NOTES
# =====================================

@login_required
@staff_or_admin
def add_claim_note(request, claim_id):
    """
    Securely appends an internal or customer note to the claim dossier.
    Only authorized staff/admin can contribute to the audit discussion.
    """
    claim = _get_claim_by_public_id_or_404(claim_id)
    
    if request.method == "POST":
        # Form field can be 'content' or 'message' depending on the template origin
        message = request.POST.get('content') or request.POST.get('message')
        note_type = request.POST.get('note_type', 'internal')
        is_important = request.POST.get('is_important') == 'on'
        
        if message and message.strip():
            # Create the note in the audit trail
            ClaimNote.objects.create(
                claim=claim,
                created_by=request.user,
                message=message.strip(),
                note_type=note_type,
                is_important=is_important
            )
            
            # Log the action for regulatory compliance
            ClaimAuditLog.objects.create(
                claim=claim,
                action="NOTE_ADDED",
                performed_by=request.user,
                description=f"Added {note_type} note: {message[:50]}..."
            )
            
            messages.success(request, "Discussion note archived.")
        else:
            messages.warning(request, "Discussion archiving requires content.")

    # Redirect back to the source of the interaction
    redirect_url = request.META.get('HTTP_REFERER') or f'/claim/{claim.public_id}/'
    return redirect(redirect_url)


@login_required
@staff_or_admin
def delete_claim_note(request, note_id):
    """
    Removes a note from the discussion history. 
    Maintains lead auditor override permissions.
    """
    note = get_object_or_404(ClaimNote, id=note_id)

    claim_id = note.claim.public_id
    
    # Audit trail creation BEFORE deletion for traceability
    ClaimAuditLog.objects.create(
        claim=note.claim,
        action="NOTE_DELETED",
        performed_by=request.user,
        description=f"Deleted note by {note.created_by.username} from {note.created_at}"
    )
    
    note.delete()
    messages.info(request, "Audit note has been removed from discourse.")
    
    redirect_url = request.META.get('HTTP_REFERER') or f'/claim/{claim_id}/'
    return redirect(redirect_url)


@login_required
@staff_or_admin
def claim_notes_list(request, claim_id):
    """Returns a focused view of the discussion history for a claim."""
    claim = _get_claim_by_public_id_or_404(claim_id)
    notes = claim.notes.select_related('created_by').all().order_by('-created_at')
    
    # Pre-calculated context for the template to avoid complex template logic
    context = {
        "claim": claim,
        "notes": notes,
        "customer_notes": notes.filter(note_type='customer'),
        "internal_notes": notes.filter(note_type='internal'),
        "can_create_notes": True,
        "important_count": notes.filter(is_important=True).count()
    }
    return render(request, "claims/claim_notes.html", context)

from django.http import JsonResponse
from .utils import generate_assessment_remark

@login_required
@staff_or_admin
def generate_claim_remark_api(request, id):
    """
    API endpoint for auto-generating professional remarks.
    Supports 'decision' (APPROVE/REVIEW/REJECT) and 'mode' (short/detailed) params.
    """
    claim = _get_claim_by_public_id_or_404(id)
    
    # Extract params from GET or POST
    decision = request.GET.get('decision') or request.POST.get('decision')
    mode = request.GET.get('mode', 'detailed')
    
    remark = generate_assessment_remark(claim, decision=decision, mode=mode)
    return JsonResponse({'remark': remark})

def test_route(request):
    return JsonResponse({'status': 'ok', 'message': 'Routing is working'})

@login_required
@staff_or_admin
def ai_audit(request, claim_id):
    """
    Returns a high-fidelity, AI-powered explainable financial audit of the claim logic.
    Provides complete transparency into every step of the calculation.
    """
    claim = get_object_or_404(Claim, id=claim_id)
    
    # Authorization Check
    if not (request.user.is_superuser or request.user.role in ['admin', 'staff']):
        if not user_can_access_claim(request.user, claim):
            return JsonResponse({'error': 'Unauthorized'}, status=403)

    # 1. Run Enterprise XGBoost Audit Engine (Requirement 1-5)
    from .xgb_audit_engine import process_claim_audit
    # 🔥 READ-ONLY MODE: Disable snapshot storage for standard audit views to prevent signal loops
    audit_data = process_claim_audit(claim, user=request.user, store_snapshot=False)

    if audit_data.get("error"):
        return JsonResponse(audit_data, status=500)

    # 2. Return Enriched Enterprise Response
    return JsonResponse(audit_data)


@csrf_exempt
@require_POST
def ai_audit_replay(request):
    """
    Requirement 2: Deterministic Replay API
    Allows regulators to verify past decisions using stored feature hashes.
    """
    import json
    try:
        data = json.loads(request.body)
        f_hash = data.get('feature_hash')
        version = data.get('model_version')
        
        if not f_hash:
            return JsonResponse({'error': 'feature_hash is required'}, status=400)
            
        from .xgb_audit_engine import XGBAuditEngine
        engine = XGBAuditEngine()
        replay_result = engine.replay_audit(f_hash, version)
        
        return JsonResponse(replay_result)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_POST
def verify_audit_signature(request):
    """
    Requirement 1: Signature Verification
    Validates whether an audit response is authentic and untampered.
    """
    import json
    try:
        data = json.loads(request.body)
        payload = data.get('payload')
        signature = data.get('signature')
        meta = payload.get('signature_meta', {}) if payload else {}
        key_id = meta.get('key_id')
        
        if not payload or not signature or not key_id:
            return JsonResponse({'error': 'Missing payload, signature, or key_id'}, status=400)
            
        from .xgb_audit_engine import XGBAuditEngine
        engine = XGBAuditEngine()
        is_valid = engine.verify_signature(payload, signature, key_id)
        
        return JsonResponse({'valid': is_valid, 'algorithm': meta.get('algorithm'), 'key_id': key_id})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
@staff_or_admin
def claim_intelligence_api(request, id):
    """
    Enterprise Entry Point for High-Governance AI Intelligence
    Triggers the 5-layer pipeline and returns a standardized audit JSON.
    Accessible by Staff/Admin.
    """
    from ai_features.services.ai_pipeline_service import run_intelligence_pipeline
    from django.shortcuts import get_object_or_404
    from .models import Claim
    
    # Simple lookup for id (supports UUID and INT)
    try:
        if len(str(id)) > 30: # Likely UUID
            claim = Claim.objects.get(public_id=id)
        else:
            claim = Claim.objects.get(id=id)
    except:
        claim = get_object_or_404(Claim, public_id=id)
        
    success = run_intelligence_pipeline(claim)
    return JsonResponse({
        'status': 'success' if success else 'failed',
        'message': 'AI Intelligence Pipeline executed' if success else 'Pipeline execution encountered errors',
        'success': success
    })

@require_POST
@login_required
@staff_or_admin
def auditor_review_api(request):
    """
    🔐 AJAX API: Persists Auditor Decision and updates performance metrics.
    Enforces mandatory recommendation, remarks, and amount validation.
    """
    try:
        data = json.loads(request.body)
        claim_public_id = data.get('claim_id')
        decision = data.get('decision')
        recommended_amount = safe_money(data.get('recommended_amount'))
        remarks = data.get('remarks')

        # 1. Validation Logic
        if not claim_public_id or not decision or not remarks:
            return JsonResponse({'error': 'Please complete all mandatory fields (Recommendation, Remarks) before submitting review.'}, status=400)

        claim = get_object_or_404(Claim, public_id=claim_public_id)

        if recommended_amount <= 0:
            return JsonResponse({'error': 'Approved amount must be greater than zero.'}, status=400)

        # Max Payable Check (claimed_amount - deductible_amount)
        max_payable = safe_money(claim.claimed_amount) - safe_money(claim.deductible_amount)
        if recommended_amount > max_payable:
            return JsonResponse({'error': f'Financial Violation: Amount ₹{recommended_amount} exceeds maximum policy payable of ₹{max_payable}.'}, status=400)

        # 2. Persist Official Auditor Review
        with transaction.atomic():
            review, created = AuditorReview.objects.update_or_create(
                claim=claim,
                auditor=request.user,
                defaults={
                    'decision': decision,
                    'recommended_amount': recommended_amount,
                    'remarks': remarks,
                    'ai_original_amount': recommended_amount,
                    'throughput_value': safe_money(claim.claimed_amount),
                    'assigned_at': claim.assigned_at or claim.created_at,
                    'reviewed_at': timezone.now()
                }
            )

            # 🛡️ Governance Debug Check
            print(f"📊 SYSTEM AUDIT: AuditorReview Entry Captured via API. Current Ledger Count: {AuditorReview.objects.count()}")

            # 3. Update Dossier State
            claim.staff_recommendation = decision
            claim.staff_notes = remarks
            claim.approved_amount = recommended_amount
            claim.status = "staff_reviewed" # Transition to Senior Audit / Management Approval phase
            claim.save(user=request.user)

            # 4. Success Activity Logging
            ClaimAuditLog.objects.create(
                claim=claim,
                performed_by=request.user,
                action="AUDITOR_REVIEW_SUBMITTED",
                description=f"Formal review archived. Decision: {decision}. Amount: ₹{recommended_amount}. Remarks: {remarks[:100]}..."
            )

        # 5. Dynamic Response for UI Feedback
        # Compute authoritative AI recommendation (SSoT)
        from .services.claim_payout_service import ClaimPayoutService
        ai_val = float(ClaimPayoutService.get_authoritative_payout(claim))
        aud_val = float(recommended_amount)
        deviation = 0
        if ai_val > 0:
            deviation = abs(ai_val - aud_val) / ai_val * 100

        return JsonResponse({
            'success': True,
            'message': 'Review Submitted Successfully',
            'ai_amount': ai_val,
            'auditor_amount': aud_val,
            'deviation': round(deviation, 2),
            'tier': 'A' if deviation < 5 else ('B' if deviation < 15 else 'C')
        })

    except Exception as e:
        logger.error(f"FATAL: Auditor API Fatal: {str(e)}", exc_info=True)
        return JsonResponse({'error': f'System failure during audit persistence: {str(e)}'}, status=500)


@require_POST
@login_required
@staff_or_admin
def claim_integrity_api(request, id):
    """
    Lightweight preview API for the integrity engine.
    Returns the payout-basis decision and required action without persisting changes.
    """
    claim = _get_claim_by_public_id_or_404(id)

    try:
        data = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        data = {}

    basis_selection = data.get("basis_selection")
    manual_amount = data.get("manual_amount")

    if basis_selection not in {"DECLARED", "OCR", "MANUAL"}:
        return JsonResponse({"error": "Invalid payout basis selection."}, status=400)

    declared_amount = safe_money(claim.declared_claim_amount or claim.claimed_amount or 0)
    verified_amount = safe_money(claim.ocr_verified_bill_total or 0)

    if basis_selection == "DECLARED":
        preview_amount = declared_amount
    elif basis_selection == "OCR":
        preview_amount = verified_amount
    else:
        preview_amount = safe_money(manual_amount)

    response = _serialize_claim_integrity_state(claim)
    response.update({
        "selected_basis": basis_selection,
        "selected_basis_display": {
            "DECLARED": "Declared Amount",
            "OCR": "OCR Verified Amount",
            "MANUAL": "Manual Corrected Amount",
        }[basis_selection],
        "preview_payout_basis_amount": float(preview_amount),
        "preview_payout_basis_source": basis_selection,
        "required_action": claim.integrity_required_action,
    })
    return JsonResponse(response)

@staff_or_admin
def ai_audit_api(request, id):
    """
    API for the AI Explainable Audit Trace component.
    Requirement Phase 3: Explainability 2.0.
    """
    claim = _get_claim_by_public_id_or_404(id)
    engine = AICalculationEngine(claim, user=request.user)
    audit_data = engine.get_audit_trail()
    
    # Add governance details
    audit_data["governance"] = {
        "priority": claim.priority_level,
        "priority_reason": claim.priority_reason,
        "admin_note": claim.ai_audit_note,
        "model_version": claim.model_version.version_id if claim.model_version else "v1.1",
        "features": claim.top_features
    }

    # Add multi-risk values specifically for the radar
    audit_data["risk_analysis"]["multi_risk"] = {
        "fraud_risk": float(safe_money(claim.fraud_risk_score)),
        "leakage_risk": float(safe_money(claim.leakage_risk_score)),
        "doc_risk": float(safe_money(claim.documentation_risk_score)),
        "uncertainty": float(safe_money(claim.payout_uncertainty_score))
    }

    # 🛡️ AUTHORITATIVE FINANCIAL SYNC (Regulator-Grade SSoT)
    from .services.claim_review_service import ClaimReviewService
    review_payload = ClaimReviewService.get_review_payload(claim)

    audit_data.update({
        "claimed_amount": review_payload["declared_amount"],
        "ocr_amount": review_payload["verified_bill"],
        "calculation_steps": review_payload["steps"],
        "final_amount": review_payload["final_amount"],
        "risk_adjustment": review_payload["risk_amount"],
        "composite_risk_score": review_payload["risk_score"],
        "risk_label": review_payload["risk_label"],
        "compliance_score": round(100 - review_payload["risk_score"], 1),
        "explainability_snapshot": {
            "audit_note": review_payload["summary_text"],
            "forensic_details": [
                {"factor": d["name"], "impact_score": d["impact"], "actual": "Detected", "benchmark": "N/A"} 
                for d in review_payload["drivers"]
            ]
        },
        "integrity_check": {
            "status": claim.integrity_status,
            "status_display": claim.get_integrity_status_display(),
            "mismatch_ratio": float(safe_money(claim.claim_amount_mismatch_ratio)),
            "payout_basis": review_payload["verified_bill"] if claim.payout_basis_source == 'OCR' else float(safe_money(claim.payout_basis_amount)),
            "payout_source": claim.payout_basis_source,
            "review_hold": claim.review_hold_flag,
            "declared_amount": review_payload["declared_amount"],
            "ocr_verified_amount": review_payload["verified_bill"]
        }
    })

    return JsonResponse(audit_data)
