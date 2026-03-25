import datetime
import mimetypes
import os
from decimal import Decimal, InvalidOperation

from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.conf import settings

from policy.models import PolicyHolder, Policy, UserPolicy, Payment
from accounts.utils import mask_phone, mask_email
from django.db.models import Q, Sum
from .models import (
    Claim,
    ClaimDocument,
    ClaimNote,
    ClaimAssessment,
    ClaimSettlement,
    ClaimAuditLog,
    DOCUMENT_EXTENSION_VALIDATOR
)

from .forms import StaffNoteForm, ClaimAssessmentForm
from .utils import compare_vehicle_numbers

# 🔥 AI IMPORTS
from ai_features.services.ai_claim_service import predict_claim_type
from ai_features.services.amount_service import predict_recommended_amount
from ai_features.services.fraud_service import predict_fraud_risk
from ai_features.services.ai_pipeline_service import run_ai_pipeline

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


# =====================================
# CLAIM LIST
# =====================================

@login_required
def claim_list(request):
    is_admin_or_staff = request.user.is_superuser or request.user.role in ["admin", "staff"]
    
    # Base queryset
    claims = Claim.objects.select_related("policy", "assigned_to", "created_by")

    if is_admin_or_staff:
        # Admins/Staff see all claims by default (not excluding anything)
        pass
    else:
        # Filter by identifying the user's specific policy instances
        # and include claims either submitted by them OR linked to their owned policies
        user_policies = UserPolicy.objects.filter(user=request.user)
        owned_policy_ids = list(user_policies.values_list('policy_id', flat=True))
        owned_vehicles = list(user_policies.exclude(vehicle_number=None).values_list('vehicle_number', flat=True))

        # 1. Base filter: User submitted OR policy matches one of their owned plans
        claims_q = Q(created_by=request.user) | Q(policy_id__in=owned_policy_ids)
        claims = claims.filter(claims_q).distinct()

        # 2. Refine Motor claims: If it's a motor claim, it MUST match the user's vehicle
        # to prevent User A from seeing User B's claims on the same 'Basic Car Plan'
        if owned_vehicles:
            claims = claims.filter(
                Q(created_by=request.user) | 
                Q(vehicle_number__isnull=True) | 
                Q(vehicle_number="") |
                Q(vehicle_number__in=owned_vehicles)
            )
        else:
            # If the user has NO motor policies, enforce created_by for any motor claims they see
            claims = claims.filter(
                Q(vehicle_number__isnull=True) | 
                Q(vehicle_number="") |
                Q(created_by=request.user)
            )
        
        # 3. Final: Exclude finalized claims from the main tracking list
        claims = claims.exclude(status__in=['settled', 'closed'])

    return render(request, "claims/claim_list.html", {"claims": claims})


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
            status='active'
        ).select_related('policy')

    if request.method == "POST":

        policy = get_object_or_404(Policy, id=request.POST.get("policy"))

        if not (request.user.is_superuser or request.user.role in ["admin", "staff"]):
            if not user_has_policy(request.user, policy):
                messages.error(request, "Invalid policy")
                return redirect("claim:create")
            
            # 🛡️ Real Insurance Lifecycle Gate: Block claims for Lapsed policies
            user_policy = UserPolicy.objects.filter(user=request.user, policy=policy).first()
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
                claimed_amount = Decimal(request.POST.get("claimed_amount", "0"))
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
            user_policy = UserPolicy.objects.filter(user=request.user, policy=policy, status='active').first()
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
            claimed_amount = Decimal(claimed_amount_str)
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
            user_policy = UserPolicy.objects.filter(user=request.user, policy=policy, status='active').first()
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
                
            if not request.FILES.get("rc_document"):
                messages.error(request, "RC Document upload is mandatory for motor claims.")
                return redirect("claim:create")
            if not request.FILES.get("repair_bill"):
                messages.error(request, "Repair Bill upload is mandatory for motor claims.")
                return redirect("claim:create")

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
                from ai_features.services.ocr_service import verify_identity
                from django.core.files.storage import default_storage
                import os
                
                # Temporary save to full path for OCR processing
                temp_filename = f"verify_{request.user.id}_{int(timezone.now().timestamp())}_{identity_proof.name}"
                temp_path = default_storage.save(f"tmp/{temp_filename}", identity_proof)
                full_temp_path = os.path.join(settings.MEDIA_ROOT, temp_path)
                
                try:
                    results = verify_identity(full_temp_path, profile.full_name, profile.aadhaar_number)
                    
                    if not results.get("verified"):
                        # Detailed feedback on why it failed
                        msg = "Identity Validation Failed: The uploaded document could not be verified as your registered Aadhaar. "
                        if results.get("extracted_number"):
                            msg += f"Extracted number {results['extracted_number'][-4:].rjust(12, 'X')} doesn't match."
                        else:
                            msg += "Aadhaar number not legible in scan."
                        
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
            pipeline_success = run_ai_pipeline(claim)
            
            if pipeline_success:
                # Sync primary claim_type with AI classification if high confidence
                if claim.confidence_score > 70:
                    claim.claim_type = claim.ai_claim_type
                    claim.save(update_fields=['claim_type'])

                ClaimAuditLog.objects.create(
                    claim=claim,
                    action=f"AI Pipeline v2 SUCCESS: Decision={claim.ai_decision}, Amount=₹{claim.ai_predicted_amount:,.2f}",
                    performed_by=request.user
                )
            else:
                ClaimAuditLog.objects.create(
                    claim=claim,
                    action="AI Pipeline processed with errors. Defaulting to manual audit.",
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
                action=f"AI Classification: {ai_type} ({confidence*100:.1f}%), Amount: ₹{ai_recommended_amount:.2f}, Fraud Risk: {risk_score:.2f}",
                performed_by=request.user
            )
        except Exception as e:
            # If AI prediction fails, log error but continue
            ClaimAuditLog.objects.create(
                claim=claim,
                action=f"AI Amount Prediction Failed: {str(e)}",
                performed_by=request.user
            )

        ClaimAuditLog.objects.create(
            claim=claim,
            action="Claim submitted and documents uploaded",
            performed_by=request.user
        )

        messages.success(request, f"Claim submitted successfully. Ref: {claim.claim_number}")

        return redirect("claim:detail", id=claim.id)

    return render(request, "claims/claim_submit.html", {"policies": policies})


# =====================================
# CLAIM DETAIL
# =====================================

@login_required
def claim_detail(request, id):
    claim = get_object_or_404(Claim, id=id)

    if not (request.user.is_superuser or request.user.role in ["admin", "staff"]):
        if not user_has_policy(request.user, claim.policy):
            return render(request, "accounts/unauthorized.html")

    # If it's a staff user, redirect to the enhanced staff assessment workflow
    if request.user.role == 'staff' and not request.user.is_superuser:
        return redirect('claim:staff_review', id=id)

    return render(request, "claims/claim_detail.html", {"claim": claim})


# =====================================
# EDIT CLAIM
# =====================================

@login_required
def claim_edit(request, id):
    claim = get_object_or_404(Claim, id=id)

    if not (request.user.is_superuser or request.user.role in ["admin", "staff"]):
        if not user_has_policy(request.user, claim.policy):
            return render(request, "accounts/unauthorized.html")

    if request.method == "POST":
        # Update claim fields
        claim.claim_type = request.POST.get("claim_type")
        claim.incident_date = request.POST.get("incident_date")
        claim.description = request.POST.get("description")
        claim.claimed_amount = Decimal(request.POST.get("claimed_amount"))
        claim.save()

        ClaimAuditLog.objects.create(
            claim=claim,
            action="Claim updated",
            performed_by=request.user
        )

        messages.success(request, "Claim updated successfully")
        return redirect("claim:detail", id=claim.id)

    return render(request, "claims/claim_edit.html", {"claim": claim})


# =====================================
# DELETE CLAIM
# =====================================

@login_required
def claim_delete(request, id):
    claim = get_object_or_404(Claim, id=id)

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

@login_required
@login_required
def staff_claim_review(request, id):
    """
    Dedicated review page for Staff users.
    Allows: Adding comments, Forwarding to Admin (under_review), Rejecting.
    Restrictions: Cannot Mark as Settled.
    """
    claim = get_object_or_404(Claim, id=id)

    # Security check: Only staff can access this page
    if not (request.user.role == "staff" or request.user.is_superuser):
        messages.error(request, "You are not authorized to access this review page.")
        return redirect("accounts:login")

    if request.method == "POST":
        action = request.POST.get("action")
        comment = request.POST.get("comment", "").strip()
        new_claim_type = request.POST.get("claim_type")
        new_approved_amount = request.POST.get("approved_amount")

        # 1. Update Editable Fields (Manual Override)
        if new_claim_type and new_claim_type != claim.claim_type:
            old_type = claim.get_claim_type_display()
            claim.claim_type = new_claim_type
            # Find label for the new type for the log
            new_type_label = next((label for code, label in claim.CLAIM_TYPE if code == new_claim_type), new_claim_type)
            ClaimAuditLog.objects.create(
                claim=claim,
                performed_by=request.user,
                action=f"Staff changed Claim Type from {old_type} to {new_type_label}."
            )

        # Calculate Net Claimable ceiling
        net_claimable = max(Decimal('0'), claim.claimed_amount - claim.deductible_amount)

        if new_approved_amount:
            try:
                dec_amount = Decimal(new_approved_amount)
                
                # 🛡️ MANDATORY RULE: Approved amount cannot exceed Net Claimable
                if dec_amount > net_claimable:
                    messages.error(request, f"Validation Error: Approved amount (₹{dec_amount:,.2f}) cannot exceed Net Claimable amount (₹{net_claimable:,.2f}) after deductible.")
                    return redirect("claim:staff_review", id=id)

                if dec_amount != claim.approved_amount:
                    old_amt = f"₹{claim.approved_amount:,.2f}" if claim.approved_amount else "None"
                    claim.approved_amount = dec_amount
                    ClaimAuditLog.objects.create(
                        claim=claim,
                        performed_by=request.user,
                        action=f"Staff updated Approved Amount from {old_amt} to ₹{dec_amount:,.2f}."
                    )
            except (InvalidOperation, TypeError):
                messages.error(request, "Invalid approved amount format.")
                return redirect("claim:staff_review", id=id)

        # 2. Add comment if provided
        if comment:
            ClaimNote.objects.create(
                claim=claim,
                created_by=request.user,
                message=comment
            )
            ClaimAuditLog.objects.create(
                claim=claim,
                performed_by=request.user,
                action=f"Staff added a review comment."
            )

        # 3. Decision Processing
        # Final Check for Approval status
        if action in ["approve", "reject", "submit_to_admin"]:
            # ... existing logic for amount calculation ...
            if action == "approve":
                # Determine the base amount (Fallback priority: Manual Entry (dec_amount) > AI Prediction)
                staff_val = Decimal(new_approved_amount) if new_approved_amount else claim.approved_amount or Decimal('0')
                ai_val = claim.ai_predicted_amount or Decimal('0')
                
                # Use staff value if it exists and is non-zero, else fallback to AI
                base_assessment = staff_val if staff_val > 0 else ai_val
                
                # If still 0, fallback to total claimed amount
                if base_assessment <= 0:
                    base_assessment = claim.claimed_amount
                    
                # MANDATORY RULE: Approved amount MUST honor the Net Claimable limit
                claim.approved_amount = min(base_assessment, net_claimable)
                claim.status = "approved"
            elif action == "reject":
                claim.status = "rejected"
            elif action == "submit_to_admin":
                claim.status = "under_review"

            # 🔄 FEEDBACK LOOP: Update AI Retraining Ledger
            try:
                latest_history = claim.ai_history.first()
                if latest_history:
                    latest_history.human_decision = action
                    latest_history.human_amount = claim.approved_amount or Decimal('0')
                    
                    # Detect significant discrepancy (Retraining Signal)
                    ai_amt = float(latest_history.ai_predicted_amount)
                    human_amt = float(latest_history.human_amount)
                    if ai_amt > 0:
                        diff_pct = abs(human_amt - ai_amt) / ai_amt
                        if diff_pct > 0.15: # 15% discrepancy is a learning signal
                            latest_history.is_disputed = True
                    
                    latest_history.save()
                    logger.info(f"📈 Feedback loop updated for {claim.claim_number}: Disputed={latest_history.is_disputed}")
            except Exception as e:
                logger.error(f"⚠️ Failed to update AI feedback loop: {e}")

            # Final Save with Audit Log
            claim.save()
            ClaimAuditLog.objects.create(
                claim=claim,
                performed_by=request.user,
                action=f"Staff finalizing assessment with action: {action.upper()}."
            )
            
            messages.success(request, f"Claim status updated to {claim.get_status_display()}.")
            return redirect("accounts:staff_dashboard")
        
        elif action == "flag":
            claim.status = "investigation"
            msg = "flagged for review"
            audit_msg = "Claim flagged for further investigation/review."
        elif action == "submit_to_admin":
            claim.status = "under_review"
            msg = "submitted to Admin"
            audit_msg = "Claim submitted to Admin for final settlement/review."
        elif action == "reject":
            # Edge case: If claimed_amount < deductible, we should also reject
            claim.status = "rejected"
            msg = "rejected"
            audit_msg = "Claim rejected by staff."
        else:
            msg = None

        claim.save()

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
            return redirect("claim:staff_review", id=id)

    # Context for rendering
    days_since_incident = (timezone.now().date() - claim.incident_date).days
    net_claimable = max(Decimal('0'), claim.claimed_amount - claim.deductible_amount)
    
    # Validation logic (reusing existing one)
    user_policy = UserPolicy.objects.filter(user=claim.created_by, policy=claim.policy).first()
    policy_active = False
    if user_policy and user_policy.status == 'active':
        policy_active = True
    
    # Dynamic AI Refresh (If missing)
    if not claim.ai_predicted_amount:
        try:
            claim.ai_predicted_amount = predict_recommended_amount(claim)
            claim.save(update_fields=['ai_predicted_amount'])
        except Exception:
            claim.ai_predicted_amount = float(claim.claimed_amount) * 0.85
    
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
            
    context = {
        "claim": claim,
        "days_since_incident": days_since_incident,
        "net_claimable": net_claimable,
        "policy_active": policy_active,
        "documents": claim.documents.all(),
        "notes": claim.notes.all().order_by('-created_at'),
        "audit_logs": claim.audit_logs.all().order_by('-created_at'),
        "claim_history_count": Claim.objects.filter(created_by=claim.created_by).exclude(id=claim.id).count(),
    }

    return render(request, "claims/staff_claim_review.html", context)


def claim_review(request, id):
    claim = get_object_or_404(Claim, id=id)

    if not (request.user.is_superuser or request.user.role in ["admin", "staff"]):
        return render(request, "accounts/unauthorized.html")

    if request.method == "POST":
        if not (request.user.is_superuser or request.user.role == "admin"):
            messages.error(request, "Only Administrators/Admins can perform final approval/rejection.")
            return redirect("claim:review", id=id)

        action = request.POST.get("action")
        comment = request.POST.get("admin_comment", "").strip()

        if action == "approve":
            claim.status = "approved"
            audit_msg = "Claim FINAL APPROVED by Admin."
            if comment:
                audit_msg += f" Note: {comment}"
                
            claim.save()
            ClaimAuditLog.objects.create(
                claim=claim,
                performed_by=request.user,
                action=audit_msg
            )
            messages.success(request, f"Claim {claim.claim_number} has been approved. You can now proceed to settlement.")
            return redirect("claim:settlement", claim_id=claim.id)
            
        elif action == "reject":
            claim.status = "rejected"
            audit_msg = "Claim FINAL REJECTED by Admin."
            if comment:
                audit_msg += f" Reason: {comment}"
                
            claim.save()
            ClaimAuditLog.objects.create(
                claim=claim,
                performed_by=request.user,
                action=audit_msg
            )
            messages.success(request, f"Claim {claim.claim_number} has been rejected.")
            return redirect("claim:review", id=id)

    # 📊 Calculate derived view data
    days_since_incident = (timezone.now().date() - claim.incident_date).days
    
    # Financials
    net_claimable = max(Decimal('0'), claim.claimed_amount - claim.deductible_amount)
    
    # ── IDENTIFY THE TRUE POLICYHOLDER (Subject of Claim) ───────────────
    # 1. Start with the account that recorded the claim
    subject_user = claim.created_by
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
    user_policy = UserPolicy.objects.filter(user=subject_user, policy=claim.policy).first()

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

    context = {
        "claim": claim,
        "applicant": subject_user, # Unified applicant source
        "subject_user": subject_user,
        "days_since_incident": days_since_incident,
        "net_claimable": net_claimable,
        "policy_active_on_incident": policy_active_on_incident,
        "documents": claim.documents.all(),
        "claim_history_count": Claim.objects.filter(created_by=subject_user).exclude(id=claim.id).count(),
        "notes": claim.notes.all().order_by('-created_at'),
        "audit_logs": claim.audit_logs.all().order_by('-created_at'),
        "show_full_data": request.user.is_superuser,
        "masked_email": mask_email(subject_user.email if subject_user else ""),
        "masked_phone": mask_phone(subject_user.phone if subject_user else ""),
    }

    return render(request, "claims/claim_review.html", context)


# =====================================
# CLAIM HISTORY
# =====================================

@login_required
def claim_history(request, claim_id):
    claim = get_object_or_404(Claim, id=claim_id)

    if not (request.user.is_superuser or request.user.role in ["admin", "staff"]):
        if not user_has_policy(request.user, claim.policy):
            return render(request, "accounts/unauthorized.html")

    history = ClaimAuditLog.objects.filter(claim=claim).order_by('-created_at')
    return render(request, "claims/claim_history.html", {"claim": claim, "history": history})


# =====================================
# CLAIM SETTLEMENT
# =====================================

@login_required
def claim_settlement(request, claim_id):
    claim = get_object_or_404(Claim, id=claim_id)

    # Only Admins and Superusers can process final settlement
    if not (request.user.is_superuser or request.user.role == "admin"):
        messages.error(request, "Only Administrators can process final settlement.")
        return render(request, "accounts/unauthorized.html")

    if request.method == "POST":
        # Use automatic Ledger ID generation logic from Payment model (TXN-SETL prefix)
        # We will no longer generate manual 'SETL-' strings here unless overridden by Admin
        # If admin provides a reference (like a Cheque No), we still keep it in gateway_reference
        txn_ref = request.POST.get("reference", "").strip()

        # Read the FINAL result from the form (Admin might have edited it)
        try:
            manual_settled_amount = Decimal(request.POST.get("settled_amount", "0"))
        except (InvalidOperation, TypeError):
            manual_settled_amount = Decimal('0')

        # Determine default final payable using standardized fallback (Staff > AI > Claimed)
        staff_val = claim.approved_amount or claim.recommended_amount or Decimal('0')
        ai_val = claim.ai_predicted_amount or Decimal('0')
        base_assessment = staff_val if staff_val > 0 else ai_val
        if base_assessment <= 0:
            base_assessment = claim.claimed_amount
            
        default_final_payable = min(base_assessment, claim.net_claimable)

        # 🛡️ PRIORITIZE the manual edited amount from Admin, if provided and valid (>0)
        # Otherwise fallback to the system calculated default_final_payable
        final_payable = manual_settled_amount if manual_settled_amount > 0 else default_final_payable
        
        # 🛡️ MANDATORY SAFETY CHECK: Payout cannot EXCEED Net Claimable
        if final_payable > claim.net_claimable:
            messages.error(request, f"Financial Block: Final payout (₹{final_payable:,.2f}) cannot exceed Net Claimable ceiling (₹{claim.net_claimable:,.2f}).")
            return redirect("claim:settlement", claim_id=claim.id)
        
        # 🔍 Debug Logging for Financial Trace (as requested by USER)
        print(f"DEBUG — SETTLEMENT START: Claim {claim.claim_number}")
        print(f"CLAIMED: {claim.claimed_amount}")
        print(f"APPROVED: {claim.approved_amount}")
        print(f"SETTLED (FINAL): {final_payable}")
        print(f"LIMIT (NET): {claim.net_claimable}")

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
        
        # 🔗 Safety Check: Ensure transaction amount matches settled amount
        if settlement.settled_amount != claim.settled_amount:
            raise Exception(f"Transaction mismatch with settled claim: {settlement.settled_amount} != {claim.settled_amount}")
            
        claim.save()

        # 🔗 Real Insurance Lifecycle Sync: Update UserPolicy status (checks for exhaustion)
        user_policy = UserPolicy.objects.filter(user=claim.created_by, policy=claim.policy).first()
        if user_policy:
            user_policy.sync_status_with_premiums()

        ClaimAuditLog.objects.create(
            claim=claim,
            action=f"Claim settled through {request.POST.get('payment_mode', 'standard')} channel. Reference: {txn_ref}",
            performed_by=request.user
        )

        # 💸 Sync with Unified Ledger: Create Payment entry for the payout (DEBIT)
        Payment.objects.create(
            user_policy=user_policy,
            claim=claim,
            amount=final_payable,
            payment_status='completed',
            payment_type='CLAIM_SETTLEMENT',
            direction='DEBIT',
            payment_method=request.POST.get("payment_mode", "neft").lower(),
            transaction_id="", # Let the model's save() generate the TXN-SETL- ID
            gateway_reference=txn_ref, # Store the actual Cheque/UPI ID here
            description=f"Claim Payout Settlement - {claim.claim_number}",
            notes=f"Processed by {request.user.username}. Payee: {request.POST.get('payee_name', '')}"
        )

        messages.success(request, f"Settlement Successful! Payout of ₹{final_payable:,.2f} has been dispatched for claim {claim.claim_number}.")
        return redirect("claim:detail", id=claim.id)

    # Calculate the INITIAL final payable for the template display
    staff_val = claim.approved_amount or claim.recommended_amount or Decimal('0')
    ai_val = claim.ai_predicted_amount or Decimal('0')
    base_assessment = staff_val if staff_val > 0 else ai_val
    if base_assessment <= 0:
        base_assessment = claim.claimed_amount
    
    final_payable = min(base_assessment, claim.net_claimable)

    context = {
        "claim": claim,
        "final_payable": final_payable,
        "net_claimable": claim.net_claimable
    }

    return render(request, "claims/claim_settlement.html", context)


# =====================================
# DOCUMENT UPLOAD
# =====================================

@login_required
def upload_claim_document(request, claim_id):
    claim = get_object_or_404(Claim, id=claim_id)

    if not (request.user.is_superuser or request.user.role in ["admin", "staff"]):
        if not user_has_policy(request.user, claim.policy):
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
        return redirect("claim:detail", id=claim.id)

    return render(request, "claims/document_upload.html", {"claim": claim})


# =====================================
# DOCUMENT DELETE
# =====================================

@login_required
def delete_claim_document(request, id):
    document = get_object_or_404(ClaimDocument, id=id)

    if not (request.user.is_superuser or request.user.role in ["admin", "staff"]):
        if not user_has_policy(request.user, document.claim.policy):
            return render(request, "accounts/unauthorized.html")

    if request.method == "POST":
        document.delete()
        messages.success(request, "Document deleted successfully")
        return redirect("claim:detail", id=document.claim.id)

    return render(request, "claims/document_delete.html", {"document": document})


# =====================================
# NOTE DELETE
# =====================================

@login_required
def delete_claim_note(request, id):
    note = get_object_or_404(ClaimNote, id=id)

    if not (request.user.is_superuser or request.user.role in ["admin", "staff"]):
        if not user_has_policy(request.user, note.claim.policy):
            return render(request, "accounts/unauthorized.html")

    if request.method == "POST":
        note.delete()
        messages.success(request, "Note deleted successfully")
        return redirect("claim:detail", id=note.claim.id)

    return render(request, "claims/note_delete.html", {"note": note})


# =====================================
# CLAIM NOTES LIST
# =====================================

@login_required
def claim_notes_list(request, claim_id):
    claim = get_object_or_404(Claim, id=claim_id)

    if not (request.user.is_superuser or request.user.role in ["admin", "staff"]):
        if not user_has_policy(request.user, claim.policy):
            return render(request, "accounts/unauthorized.html")

    notes = ClaimNote.objects.filter(claim=claim).order_by('-created_at')
    return render(request, "claims/claim_notes.html", {"claim": claim, "notes": notes})


# =====================================
# EDIT CLAIM NOTE
# =====================================

@login_required
def edit_claim_note(request, note_id):
    note = get_object_or_404(ClaimNote, id=note_id)

    if not (request.user.is_superuser or request.user.role in ["admin", "staff"]):
        if not user_has_policy(request.user, note.claim.policy):
            return render(request, "accounts/unauthorized.html")

    if request.method == "POST":
        note.message = request.POST.get("content") or request.POST.get("message", "")
        note.save()

        messages.success(request, "Note updated successfully")
        return redirect("claim:notes", claim_id=note.claim.id)

    return render(request, "claims/claim_notes_edit.html", {"note": note})


# =====================================
# MARK NOTE IMPORTANT
# =====================================

@login_required
def mark_note_important(request, note_id):
    note = get_object_or_404(ClaimNote, id=note_id)

    if not (request.user.is_superuser or request.user.role in ["admin", "staff"]):
        if not user_has_policy(request.user, note.claim.policy):
            return render(request, "accounts/unauthorized.html")

    note.is_important = not note.is_important
    note.save()

    messages.success(request, "Note importance updated")
    return redirect("claim:notes", claim_id=note.claim.id)


# =====================================
# NOTES DASHBOARD
# =====================================

@login_required
def notes_dashboard(request):
    if not (request.user.is_superuser or request.user.role in ["admin", "staff"]):
        return render(request, "accounts/unauthorized.html")

    notes = ClaimNote.objects.select_related("claim", "created_by").order_by('-created_at')
    return render(request, "claims/notes_dashboard.html", {"notes": notes})


# =====================================
# UPDATE STATUS
# =====================================

@login_required
def update_claim_status(request, id):

    claim = get_object_or_404(Claim, id=id)

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
            try:
                claim.recommended_amount = Decimal(request.POST.get('recommended_amount'))
            except (ValueError, TypeError, InvalidOperation):
                pass

        if status == "approved":
            # 🛡️ Real Insurance Financial Protocol: Honor the Net Claimable ceiling
            # 1. Determine the base amount (Priority: Staff decision > AI recommendation)
            # staff_decision = claim.recommended_amount (from form) or existing approved_amount
            # ai_recommendation = claim.ai_predicted_amount
            
            staff_val = claim.recommended_amount or Decimal('0')
            ai_val = claim.ai_predicted_amount or Decimal('0')
            
            # Use staff value if it exists and is non-zero, else fallback to AI
            base_assessment = staff_val if staff_val > 0 else ai_val
            
            # If still 0, fallback to total claimed amount
            if base_assessment <= 0:
                base_assessment = claim.claimed_amount
                
            # 2. Final payable logic: MIN(base_assessment, net_claimable)
            claim.approved_amount = min(base_assessment, claim.net_claimable)

        if status == "settled":
            # 🔄 Ensure settled amount perfectly mirrors approved benefits
            if not claim.approved_amount:
                staff_val = claim.recommended_amount or Decimal('0')
                ai_val = claim.ai_predicted_amount or Decimal('0')
                base_assessment = staff_val if staff_val > 0 else ai_val
                if base_assessment <= 0:
                    base_assessment = claim.claimed_amount
                claim.approved_amount = min(base_assessment, claim.net_claimable)
            
            claim.settled_amount = claim.approved_amount

        claim.save()

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
            action=f"Status updated to {status}. Logic Trace: [AI: ₹{claim.ai_predicted_amount or 0:,.2f}] [Staff Approved: ₹{claim.recommended_amount or 0:,.2f}] [Final Payout: ₹{claim.settled_amount or claim.approved_amount or 0:,.2f}]",
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
    document = get_object_or_404(ClaimDocument, id=id)

    if not document.file:
        raise Http404()

    return FileResponse(document.file.open("rb"))


# =====================================
# NOTES
# =====================================

@login_required
def add_claim_note(request, claim_id):

    claim = get_object_or_404(Claim, id=claim_id)

    if request.method == "POST":
        ClaimNote.objects.create(
            claim=claim,
            message=request.POST.get("content") or request.POST.get("message", ""),
            created_by=request.user
        )

    return redirect("claim:detail", id=claim.id)


# =====================================
# ASSESSMENT
# =====================================

@login_required
def claim_assessment(request, claim_id):

    claim = get_object_or_404(Claim, id=claim_id)

    form = ClaimAssessmentForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        assessment = form.save(commit=False)
        assessment.claim = claim
        assessment.assessed_by = request.user
        assessment.save()

        messages.success(request, "Assessment saved")
        return redirect("claim:detail", id=claim.id)

    return render(request, "claims/claim_assessment.html", {"form": form, "claim": claim})