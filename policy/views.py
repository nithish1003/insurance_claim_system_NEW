from decimal import Decimal
from datetime import date, timedelta

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils.crypto import get_random_string
from django.utils import timezone
from django.db import transaction
from django.db.models import Prefetch

from .models import (
    PolicyHolder,
    UserPolicy,
    Policy,
    Coverage,
    Beneficiary,
    PolicyDocument,
    PolicyAuditLog,
    PolicyType,
    Insurer,
    PolicyPlan,
    PolicyApplication,
    Payment,
)
from premiums.models import PremiumSchedule
from accounts.utils import mask_phone, mask_email, log_sensitive_data_access


# ── Helpers ───────────────────────────────────────────────────────────────────

def _generate_certificate_number():
    """Generate a unique certificate number like CERT-XXXXXX."""
    while True:
        cert = "CERT-" + get_random_string(6).upper()
        if not UserPolicy.objects.filter(certificate_number=cert).exists():
            return cert


def _approve_policy_application(application, reviewer, admin_remarks=""):
    import calendar
    from dateutil.relativedelta import relativedelta
    from premiums.models import PremiumPayment
    from django.utils import timezone

    def add_months_local(base_date, months):
        return base_date + relativedelta(months=months)

    with transaction.atomic():
        application = PolicyApplication.objects.select_for_update().select_related(
            "user", "user__profile", "policy"
        ).get(id=application.id)

        existing_policy = UserPolicy.objects.select_related("premium_schedule").filter(
            user=application.user,
            policy=application.policy,
        ).first()

        # 🔥 FIX: Policy Start Date is the Purchase/Activation Date (Today)
        today_date = timezone.now().date()
        start_date = today_date
        end_date = start_date + relativedelta(years=1)

        user_policy, created = UserPolicy.objects.get_or_create(
            user=application.user,
            policy=application.policy,
            defaults={
                "certificate_number": _generate_certificate_number(),
                "status": "active",
                "start_date": start_date,
                "end_date": end_date,
                "vehicle_number": application.vehicle_number or "",
                "rc_upload": application.rc_upload or None,
            },
        )

        update_fields = []
        if user_policy.status != "active":
            user_policy.status = "active"
            update_fields.append("status")
        if not user_policy.start_date:
            user_policy.start_date = start_date
            update_fields.append("start_date")
        if not user_policy.end_date:
            user_policy.end_date = end_date
            update_fields.append("end_date")
        if application.vehicle_number and user_policy.vehicle_number != application.vehicle_number:
            user_policy.vehicle_number = application.vehicle_number
            update_fields.append("vehicle_number")
        if application.rc_upload and user_policy.rc_upload != application.rc_upload:
            user_policy.rc_upload = application.rc_upload
            update_fields.append("rc_upload")
        if update_fields:
            user_policy.save(update_fields=update_fields)

        plan_schedule = application.policy.premium_schedules.filter(
            user_policy__isnull=True
        ).order_by("-created_at").first()

        if plan_schedule:
            user_schedule, schedule_created = PremiumSchedule.objects.update_or_create(
                user_policy=user_policy,
                defaults={
                    "policy": application.policy,
                    "base_premium": plan_schedule.base_premium,
                    "gst_percentage": plan_schedule.gst_percentage,
                    "gst_amount": plan_schedule.gst_amount,
                    "gross_premium": plan_schedule.gross_premium,
                    "payment_frequency": plan_schedule.payment_frequency,
                    "total_installments": plan_schedule.total_installments,
                    "installment_amount": plan_schedule.installment_amount,
                    "auto_debit_enabled": plan_schedule.auto_debit_enabled,
                    "start_date": user_policy.start_date,
                    "end_date": user_policy.end_date,
                },
            )

            if schedule_created or not user_schedule.payments.exists():
                user_schedule.payments.all().delete()
                months_step = {"monthly": 1, "quarterly": 3, "yearly": 12}.get(
                    user_schedule.payment_frequency, 1
                )
                # 🔥 Dynamic Generation with Status Check
                PremiumPayment.objects.bulk_create([
                    PremiumPayment(
                        schedule=user_schedule,
                        installment_number=i + 1,
                        due_date=add_months_local(user_policy.start_date, i * months_step),
                        amount=user_schedule.installment_amount,
                        status="upcoming" if add_months_local(user_policy.start_date, i * months_step) >= today_date else "lapsed",
                    )
                    for i in range(user_schedule.total_installments)
                ])

            amount = user_schedule.gross_premium
        else:
            base_prem = application.policy.sum_insured * Decimal("0.02")
            gst_pct = Decimal("18.0")
            gst_amt = base_prem * (gst_pct / Decimal("100.0"))
            amount = base_prem + gst_amt

        Payment.objects.get_or_create(
            user_policy=user_policy,
            direction="CREDIT",
            payment_type="PREMIUM_PAYMENT",
            description=f"Policy Activation Premium - {application.policy.policy_number}",
            defaults={
                "amount": amount,
                "payment_status": "completed",
                "payment_method": "cash",
                "notes": "Initial premium record upon approval.",
            },
        )

        was_already_approved = application.status == "approved"
        application.status = "approved"
        application.reviewed_at = timezone.now()
        application.reviewed_by = reviewer
        application.admin_remarks = admin_remarks
        application.save()

        if not was_already_approved:
            PolicyAuditLog.objects.create(
                policy=application.policy,
                performed_by=reviewer,
                action="Application Approved",
                description=(
                    f"Application by {application.user.username} approved. "
                    f"UserPolicy created for policy plan {application.policy.policy_number}."
                ),
            )

        return created


# =============================================================================
# POLICYHOLDER — My Policies (uses UserPolicy)
# =============================================================================
@login_required
def policy_list(request):
    if request.user.is_superuser or request.user.role in ["admin", "staff"]:
        return redirect("policy:admin_list")

    if request.user.role != "policyholder":
        return render(request, "accounts/unauthorized.html")

    user_policies = UserPolicy.objects.filter(
        user=request.user,
        status='active',
    ).select_related("policy", "premium_schedule").order_by("-assigned_at")

    return render(request, "policy/my_policies.html", {"user_policies": user_policies})


# =============================================================================
# ADMIN — All Policies List
# =============================================================================
@login_required
def admin_policy_list(request):
    if not (request.user.is_superuser or request.user.role in ["admin", "staff"]):
        return render(request, "accounts/unauthorized.html")

    policies = Policy.objects.prefetch_related("premium_schedules").all().order_by("-created_at")

    return render(request, "policy/admin_policies.html", {"policies": policies})


# =============================================================================
# ADMIN — Create Policy (plan template)
# =============================================================================
@login_required
def create_policy(request):
    if not (request.user.is_superuser or request.user.role == "admin"):
        return render(request, "accounts/unauthorized.html")

    if request.method == "POST":
        policy_number = "POL-" + get_random_string(6).upper()
        base_premium = request.POST.get("base_premium")

        policy = Policy.objects.create(
            policy_number=policy_number,
            policy_type=request.POST.get("policy_type"),
            insurer_name=request.POST.get("insurer_name"),
            start_date=request.POST.get("start_date"),
            end_date=request.POST.get("end_date"),
            sum_insured=request.POST.get("sum_insured"),
            deductible=request.POST.get("deductible") or 0,
            status="active",
        )

        PolicyAuditLog.objects.create(
            policy=policy,
            performed_by=request.user,
            action="Policy Created",
            description=f"Policy {policy.policy_number} created with base premium ₹{base_premium}",
        )

        messages.success(request, f"Policy {policy_number} created successfully.")
        return redirect("policy:admin_list")

    return render(request, "policy/policy_create.html", {
        "policy_types": PolicyType.objects.all(),
        "insurers": Insurer.objects.all(),
    })


# =============================================================================
# POLICY DETAIL
# =============================================================================
@login_required
def policy_detail(request, id):
    policy = get_object_or_404(Policy, id=id)

    return render(request, "policy/policy_detail.html", {
        "policy": policy,
        "coverages": policy.coverages.all(),
        "beneficiaries": policy.beneficiaries.all(),
        "documents": policy.documents.all(),
        "logs": policy.logs.all(),
        "latest_schedule": policy.premium_schedules.first(),
    })


# =============================================================================
# EDIT POLICY
# =============================================================================
@login_required
def edit_policy(request, id):
    policy = get_object_or_404(Policy, id=id)

    if request.method == "POST":
        policy.insurer_name = request.POST.get("insurer_name")
        policy.start_date   = request.POST.get("start_date")
        policy.end_date     = request.POST.get("end_date")
        policy.sum_insured  = request.POST.get("sum_insured")
        policy.deductible   = request.POST.get("deductible") or 0
        policy.status       = request.POST.get("status")
        policy.save()

        PolicyAuditLog.objects.create(
            policy=policy,
            performed_by=request.user,
            action="Policy Updated",
            description="Policy information updated",
        )
        messages.success(request, "Policy updated successfully.")
        return redirect("policy:detail", id=policy.id)

    return render(request, "policy/policy_edit.html", {
        "policy": policy,
        "policy_types": PolicyType.objects.all(),
        "insurers": Insurer.objects.all(),
    })


# =============================================================================
# DELETE POLICY
# =============================================================================
@login_required
def delete_policy(request, id):
    policy = get_object_or_404(Policy, id=id)

    if request.method == "POST":
        PolicyAuditLog.objects.create(
            policy=policy,
            performed_by=request.user,
            action="Policy Deleted",
            description="Policy removed from system",
        )
        policy.delete()
        messages.success(request, "Policy deleted successfully.")
        return redirect("policy_list")

    return render(request, "policys/policy_delete.html", {"policy": policy})


# =============================================================================
# UPDATE POLICY STATUS
# =============================================================================
@login_required
def update_policy_status(request, id):
    policy = get_object_or_404(Policy, id=id)

    if request.method == "POST":
        status = request.POST.get("status")
        if status in [choice[0] for choice in Policy.STATUS]:
            policy.status = status
            policy.save()
            PolicyAuditLog.objects.create(
                policy=policy,
                performed_by=request.user,
                action="Status Updated",
                description=f"Policy status changed to {status}",
            )
            messages.success(request, f"Policy status updated to {status.capitalize()}.")
        else:
            messages.error(request, "Invalid status.")

    return redirect("policy:list")


# =============================================================================
# ADMIN — Manage Categories (Policy Types)
# =============================================================================
@login_required
def manage_categories(request):
    """View to list and create policy categories (PolicyType)."""
    if not (request.user.is_superuser or request.user.role in ["admin", "staff"]):
        return render(request, "accounts/unauthorized.html")

    if request.method == "POST":
        name = request.POST.get("name")
        code = request.POST.get("code")
        description = request.POST.get("description", "")

        if name and code:
            # Create a slug-like code if not provided properly
            if not PolicyType.objects.filter(code=code).exists():
                PolicyType.objects.create(
                    name=name,
                    code=code.lower().replace(" ", "-"),
                    description=description
                )
                messages.success(request, f"Category '{name}' created successfully.")
            else:
                messages.error(request, f"Category with code '{code}' already exists.")
        else:
            messages.error(request, "Name and Code are required.")
        return redirect("policy:manage_categories")

    categories = PolicyType.objects.all().order_by("name")
    return render(request, "policy/manage_categories.html", {"categories": categories})


# =============================================================================
# BROWSE POLICIES (Policyholder catalog)
# =============================================================================
@login_required
def browse_policies(request):
    if request.user.role != "policyholder":
        messages.error(request, "Access denied. Only policyholders can browse policies.")
        return redirect("accounts:login")

    # Only show admin-created catalog policies
    policies = Policy.objects.filter(is_active=True).order_by("-created_at")

    # Map policy_id → existing application for this user (if any)
    user_applications = {
        app.policy_id: app
        for app in PolicyApplication.objects.filter(user=request.user)
    }

    return render(request, "policy/browse_policies.html", {
        "policies": policies,
        "user_applications": user_applications,
    })


# =============================================================================
# APPLY FOR POLICY — Creates a PolicyApplication (PENDING)
# =============================================================================
@login_required
def apply_policy(request, policy_id):
    if request.user.role != "policyholder":
        messages.error(request, "Access denied. Only policyholders can apply for policies.")
        return redirect("accounts:login")

    policy = get_object_or_404(Policy, id=policy_id, is_active=True)
    is_motor = "motor" in (policy.policy_type or "").lower()

    # ── 1. Profile completeness check ────────────────────────────────────────
    try:
        profile = request.user.profile
        if not profile.aadhaar_number or not profile.id_proof:
            messages.warning(request, "Your profile is incomplete. Please update your Aadhaar Number and ID Proof before applying.")
            return redirect("accounts:edit_profile")
    except Exception:
        messages.warning(request, "Please complete your profile before applying for a policy.")
        return redirect("accounts:edit_profile")

    # ── 2. Duplicate application check ───────────────────────────────────────
    existing = PolicyApplication.objects.filter(user=request.user, policy=policy).first()
    if existing:
        if existing.status == "pending":
            messages.warning(request, "You already have a pending application for this policy. Please wait for admin review.")
        elif existing.status == "approved":
            messages.info(request, "Your application for this policy has already been approved!")
        elif existing.status == "rejected":
            messages.error(request, "Your previous application for this policy was rejected. Contact support for more details.")
        return redirect("policy:my_applications")

    # ── 3. Premium calculation ────────────────────────────────────────────────
    schedule = getattr(policy, "premium_schedule", None)
    if schedule:
        base_prem  = schedule.base_premium
        gst_pct    = schedule.gst_percentage
        gst_amt    = schedule.gst_amount
        total_prem = schedule.gross_premium
    else:
        base_prem  = policy.sum_insured * Decimal("0.02")
        gst_pct    = Decimal("18.0")
        gst_amt    = base_prem * (gst_pct / Decimal("100.0"))
        total_prem = base_prem + gst_amt

    if request.method == "POST":
        # ── 4. Consent validation ───────────────────────────────────────────
        if not request.POST.get("confirm_details") or not request.POST.get("confirm_terms"):
            messages.error(request, "You must confirm your details and agree to the terms.")
            return redirect("policy:apply", policy_id=policy.id)

        # ── 5. Motor validation ─────────────────────────────────────────────
        vehicle_num = request.POST.get("vehicle_number", "").strip()
        rc_file     = request.FILES.get("rc_upload")

        if is_motor and (not vehicle_num or not rc_file):
            messages.error(request, "Vehicle Number and RC Upload are required for Motor policies.")
            return redirect("policy:apply", policy_id=policy.id)

        # ── 6. Create PolicyApplication (PENDING) ───────────────────────────
        # Motor fields are stored directly on the application — NO draft Policy
        application = PolicyApplication.objects.create(
            user=request.user,
            policy=policy,
            status="pending",
            vehicle_number=vehicle_num if is_motor else None,
            rc_upload=rc_file if (is_motor and rc_file) else None,
        )

        PolicyAuditLog.objects.create(
            policy=policy,
            performed_by=request.user,
            action="Policy Application Submitted",
            description=f"User {request.user.username} applied for policy {policy.policy_number}. Status: Pending.",
        )

        messages.success(request, "✅ Application submitted! We will notify you once it has been reviewed.")
        return redirect("policy:my_applications")

    return render(request, "policy/apply_policy.html", {
        "policy":     policy,
        "plan":       policy,  # For backward compatibility with template
        "is_motor":   is_motor,
        "base_prem":  base_prem,
        "gst_pct":    gst_pct,
        "gst_amt":    gst_amt,
        "total_prem": total_prem,
        "profile":    profile,
    })


# =============================================================================
# MY APPLICATIONS — Policyholder application tracker
# =============================================================================
@login_required
def my_applications(request):
    if request.user.role != "policyholder":
        return render(request, "accounts/unauthorized.html")

    qs = PolicyApplication.objects.filter(user=request.user)
    applications = qs.select_related("policy", "reviewed_by").order_by("-created_at")

    return render(request, "policy/my_applications.html", {
        "applications": applications,
        "pending_count": qs.filter(status="pending").count(),
        "approved_count": qs.filter(status="approved").count(),
        "rejected_count": qs.filter(status="rejected").count(),
    })


# =============================================================================
# ADMIN — Applications List (filter by status)
# =============================================================================
@login_required
def admin_applications_list(request):
    if not (request.user.is_superuser or request.user.role in ["admin", "staff"]):
        return render(request, "accounts/unauthorized.html")

    status_filter = request.GET.get("status", "pending")
    if status_filter not in ("pending", "approved", "rejected", "all"):
        status_filter = "pending"

    qs = PolicyApplication.objects.select_related(
        "user", "user__profile", "policy", "reviewed_by"
    ).order_by("-created_at")

    applications = qs if status_filter == "all" else qs.filter(status=status_filter)

    # ── PRIVACY & RBAC (Bulk Context) ──────────────────────────────────
    show_full_data = request.user.is_superuser
    
    # Pre-mask data for template safety if not superuser
    for app in applications:
        app.masked_phone = mask_phone(app.user.phone)
        app.masked_email = mask_email(app.user.email)

    return render(request, "policy/admin_applications.html", {
        "applications":   applications,
        "status_filter":  status_filter,
        "pending_count":  qs.filter(status="pending").count(),
        "approved_count": qs.filter(status="approved").count(),
        "rejected_count": qs.filter(status="rejected").count(),
        "show_full_data": show_full_data,
    })


# =============================================================================
# ADMIN — Review Individual Application (Approve / Reject)
# =============================================================================
@login_required
def admin_review_application(request, application_id):
    if not (request.user.is_superuser or request.user.role in ["admin", "staff"]):
        return render(request, "accounts/unauthorized.html")

    application = get_object_or_404(
        PolicyApplication.objects.select_related("user", "user__profile", "policy"),
        id=application_id,
    )

    if request.method == "POST":
        action       = request.POST.get("action")
        admin_remarks = request.POST.get("admin_remarks", "").strip()

        # ── APPROVE ──────────────────────────────────────────────────────────
        if action == "approve":
            created = _approve_policy_application(application, request.user, admin_remarks)
            if created:
                messages.success(
                    request,
                    f"Application approved! {application.user.username} now has access to {application.policy.policy_number}."
                )
            else:
                messages.success(
                    request,
                    f"Approval synced without duplicates for {application.user.username} on {application.policy.policy_number}."
                )
            return redirect("policy:admin_applications")

            # Check not already approved
            if UserPolicy.objects.filter(user=application.user, policy=application.policy).exists():
                messages.warning(request, "This user already has an active policy for this plan.")
                return redirect("policy:admin_applications")

            # Set effective dates: Start from the date the user applied
            start_date = application.created_at.date()
            end_date   = start_date + timedelta(days=365)

            # Create UserPolicy — NO new Policy record, NO new policy_number
            # Use get_or_create to prevent duplicates
            user_policy, created = UserPolicy.objects.get_or_create(
                user=application.user,
                policy=application.policy,
                defaults={
                    'certificate_number': _generate_certificate_number(),
                    'status': "active",
                    'start_date': start_date,
                    'end_date': end_date,
                    'vehicle_number': application.vehicle_number or "",
                    'rc_upload': application.rc_upload or None,
                }
            )
            
            if not created:
                # Policy already exists, update vehicle info if provided
                if application.vehicle_number:
                    user_policy.vehicle_number = application.vehicle_number
                if application.rc_upload:
                    user_policy.rc_upload = application.rc_upload
                user_policy.save()

            # ── 3. ASSIGN PREMIUM SCHEDULE ──────────────────────────────────
            # Link the plan's schedule template to this individual UserPolicy
            # ── 3. ASSIGN INDIVIDUAL PREMIUM SCHEDULE ───────────────────────
            # Detect a template schedule from the plan and clone it for this user's period
            from premiums.models import PremiumSchedule, PremiumPayment
            import calendar
            
            def add_months_local(base_date, months):
                year = base_date.year + (base_date.month - 1 + months) // 12
                month = (base_date.month - 1 + months) % 12 + 1
                day = min(base_date.day, calendar.monthrange(year, month)[1])
                return date(year, month, day)

            # Try plural first (correct related_name) or singular as fallback
            plan_schedule = application.policy.premium_schedules.first()

            if plan_schedule:
                # Create a NEW, unique schedule for this UserPolicy
                user_schedule = PremiumSchedule.objects.create(
                    user_policy=user_policy,
                    policy=application.policy,
                    base_premium=plan_schedule.base_premium,
                    gst_percentage=plan_schedule.gst_percentage,
                    gst_amount=plan_schedule.gst_amount,
                    gross_premium=plan_schedule.gross_premium,
                    payment_frequency=plan_schedule.payment_frequency,
                    total_installments=plan_schedule.total_installments,
                    installment_amount=plan_schedule.installment_amount,
                    auto_debit_enabled=plan_schedule.auto_debit_enabled,
                    start_date=user_policy.start_date, # Match the 2026 coverage
                    end_date=user_policy.end_date,
                )
                
                # Generate user-specific installments starting from 2026
                months_step = {"monthly": 1, "quarterly": 3, "yearly": 12}.get(user_schedule.payment_frequency, 1)
                new_payments = []
                for i in range(user_schedule.total_installments):
                    due_date = add_months_local(user_policy.start_date, i * months_step)
                    new_payments.append(PremiumPayment(
                        schedule=user_schedule,
                        installment_number=i + 1,
                        due_date=due_date,
                        amount=user_schedule.installment_amount,
                        status="upcoming"
                    ))
                PremiumPayment.objects.bulk_create(new_payments)
                amount = user_schedule.gross_premium
            else:
                # Fallback calculation if no plan template exists
                base_prem = application.policy.sum_insured * Decimal("0.02")
                gst_pct   = Decimal("18.0")
                gst_amt   = base_prem * (gst_pct / Decimal("100.0"))
                amount    = base_prem + gst_amt

            # ── CREATE PAYMENT RECORD (DEPRECATED for Real Lifecycle) ───────
            # Payment tracking is now handled via PremiumSchedule installments.
            # But we record the first payment (Purchase) as completed if applicable.
            Payment.objects.create(
                user_policy=user_policy,
                amount=amount,
                payment_status='completed',
                payment_method='cash',
                description=f"Policy Activation Premium - {application.policy.policy_number}",
                notes=f"Initial premium record upon approval."
            )

            # Update application status
            application.status       = "approved"
            application.reviewed_at  = timezone.now()
            application.reviewed_by  = request.user
            application.admin_remarks = admin_remarks
            application.save()

            PolicyAuditLog.objects.create(
                policy=application.policy,
                performed_by=request.user,
                action="Application Approved",
                description=(
                    f"Application by {application.user.username} approved. "
                    f"UserPolicy created for policy plan {application.policy.policy_number}."
                ),
            )

            messages.success(
                request,
                f"✅ Application approved! {application.user.username} now has access to {application.policy.policy_number}."
            )

        # ── REJECT ───────────────────────────────────────────────────────────
        elif action == "reject":
            application.status        = "rejected"
            application.reviewed_at   = timezone.now()
            application.reviewed_by   = request.user
            application.admin_remarks = admin_remarks
            application.save()

            PolicyAuditLog.objects.create(
                policy=application.policy,
                performed_by=request.user,
                action="Application Rejected",
                description=(
                    f"Application by {application.user.username} for "
                    f"{application.policy.policy_number} was rejected. Reason: {admin_remarks}"
                ),
            )

            messages.warning(request, f"Application by {application.user.username} has been rejected.")

        return redirect("policy:admin_applications")

    # ── PRIVACY & RBAC ──────────────────────────────────────────────
    show_full_data = request.user.is_superuser
    
    # Log the sensitive data access event for auditing
    log_sensitive_data_access(
        user=request.user,
        accessed_user=application.user,
        fields=['phone', 'email', 'aadhaar']
    )

    context = {
        "application": application,
        "show_full_data": show_full_data,
        "masked_phone": mask_phone(application.user.phone),
        "masked_email": mask_email(application.user.email),
    }

    return render(request, "policy/admin_application_review.html", context)


# =============================================================================
# ADMIN — Payments List
# =============================================================================
@login_required
def payment_list(request):
    if not (request.user.is_superuser or request.user.role in ["admin", "staff"]):
        return render(request, "accounts/unauthorized.html")

    from claims.models import Claim, ClaimSettlement
    from django.db.models import Q

    # Fetch filter parameters
    claim_id = request.GET.get('claim_filter')
    q = request.GET.get('q', '')

    # Base Queries
    payments_qs = Payment.objects.select_related(
        'user_policy', 
        'user_policy__user', 
        'user_policy__policy',
        'claim'
    ).order_by("-created_at")

    settlements_qs = ClaimSettlement.objects.select_related(
        'claim', 
        'claim__created_by', 
        'claim__policy'
    ).order_by("-created_at")

    # Dropdown options
    all_claims = Claim.objects.all().order_by('-claim_number')
    
    selected_claim_settlements = None
    if claim_id:
        selected_claim_settlements = settlements_qs.filter(claim_id=claim_id)
        # If filtering by claim, we don't necessarily filter all payments, 
        # but the user wanted a "separate table" for the selected item.

    # Search filtering
    if q:
        payments_qs = payments_qs.filter(
            Q(transaction_id__icontains=q) | 
            Q(user_policy__policy__policy_number__icontains=q) |
            Q(user_policy__user__username__icontains=q)
        )
        settlements_qs = settlements_qs.filter(
            Q(transaction_reference__icontains=q) | 
            Q(claim__claim_number__icontains=q)
        )

    return render(request, "policy/payment_list.html", {
        "payments": payments_qs,
        "settlements": settlements_qs,
        "all_claims": all_claims,
        "selected_claim_settlements": selected_claim_settlements,
        "q": q,
        "claim_filter_id": int(claim_id) if claim_id else None
    })


# =============================================================================
# ADMIN — Manage Individual Payment
# =============================================================================
@login_required
def manage_payment(request, payment_id):
    if not (request.user.is_superuser or request.user.role in ["admin", "staff"]):
        return render(request, "accounts/unauthorized.html")

    payment = get_object_or_404(Payment, id=payment_id)

    if request.method == "POST":
        status = request.POST.get("payment_status")
        method = request.POST.get("payment_method")
        gateway_ref = request.POST.get("gateway_reference")
        description = request.POST.get("description")
        notes = request.POST.get("notes")

        if status in [choice[0] for choice in Payment.PAYMENT_STATUS_CHOICES]:
            payment.payment_status = status
            
            # Set completed_at timestamp when payment is completed
            if status == 'completed' and not payment.completed_at:
                payment.completed_at = timezone.now()
            elif status != 'completed':
                payment.completed_at = None
        
        if method in [choice[0] for choice in Payment.PAYMENT_METHOD_CHOICES]:
            payment.payment_method = method
            
        payment.gateway_reference = gateway_ref
        payment.description = description
        payment.notes = notes
        payment.save()

        messages.success(request, f"Payment {payment.transaction_id} updated successfully.")
        return redirect("policy:payment_list")

    return render(request, "policy/manage_payment.html", {
        "payment": payment,
        "status_choices": Payment.PAYMENT_STATUS_CHOICES,
        "method_choices": Payment.PAYMENT_METHOD_CHOICES,
    })
