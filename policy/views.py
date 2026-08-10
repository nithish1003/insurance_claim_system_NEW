import logging
from decimal import Decimal
from datetime import date, timedelta

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth import get_user_model
from django.contrib import messages
from django.utils.crypto import get_random_string
from django.utils import timezone
from django.db import transaction
from django.db.models import Prefetch
from django.views.decorators.http import require_POST

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
from reports.models import ActivityLog
from premiums.models import PremiumSchedule
from accounts.utils import mask_phone, mask_email, log_sensitive_data_access
from notifications.utils import create_notification

logger = logging.getLogger(__name__)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _generate_certificate_number():
    """Generate a unique certificate number like CERT-XXXXXX."""
    while True:
        cert = "CERT-" + get_random_string(6).upper()
        if not UserPolicy.objects.filter(certificate_number=cert).exists():
            return cert


def _notify_admins_of_application(application):
    """Push a notification to every admin when a new policy application is submitted."""
    User = get_user_model()
    admin_users = User.objects.filter(role="admin").distinct()

    for admin_user in admin_users:
        create_notification(
            user=admin_user,
            title="New Policy Application",
            message=(
                f"{application.user.username} applied for {application.policy.policy_number}. "
                "Review the request in Pending Policy Applications."
            )
        )


def _create_pending_user_policy(application):
    """
    Lock the premium at application time so the customer pays the
    stored backend amount even if admin pricing changes later.
    """
    return UserPolicy.objects.create(
        user=application.user,
        policy=application.policy,
        certificate_number=_generate_certificate_number(),
        status="pending",
        final_premium=application.policy.calculate_final_premium(),
        is_paid=False,
        vehicle_number=application.vehicle_number or "",
        rc_upload=application.rc_upload or None,
    )


def _get_policy_by_public_id_or_404(public_id, **filters):
    return get_object_or_404(Policy, public_id=public_id, **filters)


def _get_policy_application_by_public_id_or_404(public_id):
    return get_object_or_404(
        PolicyApplication.objects.select_related("user", "user__profile", "policy"),
        public_id=public_id,
    )


def _get_payment_by_public_id_or_404(public_id):
    return get_object_or_404(Payment, public_id=public_id)


def _is_new_policy_activation_payment(payment):
    metadata = payment.payment_metadata or {}
    description = payment.description or ""
    if payment.direction != "CREDIT" or payment.payment_type not in ["PREMIUM_PAYMENT", "PREMIUM"]:
        return False

    if (
        metadata.get("premium_source") == "new_policy"
        or "Activation Payment" in description
        or "Policy Activation Premium" in description
    ):
        return True

    user_policy = payment.user_policy
    return bool(user_policy and user_policy.status == "approved" and not user_policy.is_paid)


def _sync_user_policy_after_payment_update(payment):
    user_policy = payment.user_policy
    if not user_policy or not _is_new_policy_activation_payment(payment):
        return

    was_paid = user_policy.is_paid
    completed_activation_exists = Payment.objects.filter(
        user_policy=user_policy,
        payment_status="completed",
        direction="CREDIT",
        payment_type__in=["PREMIUM_PAYMENT", "PREMIUM"],
    ).exclude(pk=payment.pk if payment.payment_status != "completed" else None).exists()

    update_fields = []
    if payment.payment_status == "completed":
        if not user_policy.is_paid:
            user_policy.is_paid = True
            update_fields.append("is_paid")
        if user_policy.status != "active":
            user_policy.status = "active"
            update_fields.append("status")
        if not was_paid:
            activation_date = timezone.now().date()
            user_policy.start_date = activation_date
            user_policy.end_date = activation_date + timedelta(days=365)
            update_fields.extend(["start_date", "end_date"])
        
        # 🔥 FIX: Mark the specific installment as PAID if this is an activation/premium payment
        due = user_policy.current_due_payment
        if due:
            due.status = 'paid'
            due.paid_date = timezone.now().date()
            due.transaction_reference = payment.transaction_id
            due.save(update_fields=['status', 'paid_date', 'transaction_reference'])

        if not update_fields:
            return
    elif not completed_activation_exists:
        if user_policy.is_paid:
            user_policy.is_paid = False
            update_fields.append("is_paid")
        if user_policy.status == "active":
            user_policy.status = "approved"
            update_fields.append("status")
        if not update_fields:
            return
    else:
        return

    user_policy.save(update_fields=update_fields)


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
                "status": "approved",
                "final_premium": application.policy.calculate_final_premium(),
                "is_paid": False,
                "vehicle_number": application.vehicle_number or "",
                "rc_upload": application.rc_upload or None,
            },
        )

        update_fields = []
        if user_policy.status != "approved" and user_policy.status != "active":
            user_policy.status = "approved"
            update_fields.append("status")
        if user_policy.status == "approved" and user_policy.is_paid:
            user_policy.is_paid = False
            update_fields.append("is_paid")
        if user_policy.final_premium is None:
            user_policy.final_premium = application.policy.calculate_final_premium()
            update_fields.append("final_premium")
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

            amount = user_schedule.installment_amount
        else:
            base_prem = application.policy.sum_insured * Decimal("0.02")
            gst_pct = Decimal("18.0")
            gst_amt = base_prem * (gst_pct / Decimal("100.0"))
            amount = base_prem + gst_amt

        # 🛡️ SYSTEM INTEGRITY: removed automatic payment & activation logic.
        # Activation now happens only after User Payment via make_payment API.

        was_already_approved = application.status == "approved"
        application.status = "approved"
        application.reviewed_at = timezone.now()
        application.reviewed_by = reviewer
        application.admin_remarks = admin_remarks
        application.save()

        # 🔔 NOTIFICATION: Policy Approved
        create_notification(
            user=application.user,
            title="Policy Approved",
            message="Your policy has been approved. Please complete payment to activate."
        )

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

            # 🛡️ Record activity in system ledger for Admin Analytics
            ActivityLog.objects.create(
                title=f"Policy Activated: {application.policy.policy_number}",
                description=f"Membership finalized for {application.user.username}. Application ID: {application.public_id}",
                log_type='claim',  # Treat as a 'claim/case' type for management
                status='success',
                user=reviewer,
                related_id=str(application.public_id)
            )

        return created


# =============================================================================
# POLICYHOLDER — My Policies (uses UserPolicy)
# =============================================================================
@login_required
def policy_list(request):
    if request.user.is_superuser or request.user.role in ["admin", "staff"]:
        return redirect("policy:admin_list")

    if request.user.role != "user":
        return render(request, "accounts/unauthorized.html")


    # Fetch active policies plus approved policies awaiting payment
    user_policies = UserPolicy.objects.filter(
        user=request.user,
        status__in=['approved', 'active', 'grace', 'lapsed'],
    ).select_related("policy", "premium_schedule").order_by("-assigned_at")

    # 🔥 UNIFIED VIEW: Also fetch pending applications to show in the same dashboard
    pending_applications = PolicyApplication.objects.filter(
        user=request.user,
        status='pending'
    ).select_related("policy")

    return render(request, "policy/my_policies.html", {
        "user_policies": user_policies,
        "pending_applications": pending_applications,
    })


# =============================================================================
# ADMIN — All Policies List
# =============================================================================
@login_required
def admin_policy_list(request):
    if not (request.user.is_superuser or request.user.role in ["admin", "staff"]):
        return render(request, "accounts/unauthorized.html")

    # 🛡️ SYSTEM INVENTORY: Show the master Policy blueprints (Requirement: Fix Empty Table)
    policies = Policy.objects.all().order_by("-created_at")

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
            admin_premium_percent=request.POST.get("admin_premium_percent") or 0,
            room_rent_limit_per_day=request.POST.get("room_rent_limit_per_day") or 0,
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
    policy = _get_policy_by_public_id_or_404(id)

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
    policy = _get_policy_by_public_id_or_404(id)

    if request.method == "POST":
        policy.insurer_name = request.POST.get("insurer_name")
        policy.start_date   = request.POST.get("start_date")
        policy.end_date     = request.POST.get("end_date")
        policy.sum_insured           = request.POST.get("sum_insured")
        policy.deductible            = request.POST.get("deductible") or 0
        policy.admin_premium_percent = request.POST.get("admin_premium_percent") or 0
        policy.room_rent_limit_per_day = request.POST.get("room_rent_limit_per_day") or 0
        policy.status                = request.POST.get("status")
        policy.save()

        PolicyAuditLog.objects.create(
            policy=policy,
            performed_by=request.user,
            action="Policy Updated",
            description="Policy information updated",
        )
        messages.success(request, "Policy updated successfully.")
        return redirect("policy:detail", id=policy.public_id)

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
    policy = _get_policy_by_public_id_or_404(id)

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
    policy = _get_policy_by_public_id_or_404(id)

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
from django.db.models import Count, Q
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .serializers import PolicyTypeSerializer

@login_required
def manage_categories(request):
    """View to list and create policy categories (PolicyType)."""
    if not (request.user.is_superuser or request.user.role in ["admin", "staff"]):
        return render(request, "accounts/unauthorized.html")

    # The template will now mostly use AJAX, but we load initial categories
    categories = PolicyType.objects.annotate(
        plans_count=Count('policyplan')
    ).all().order_by("-created_at")

    return render(request, "policy/manage_categories.html", {
        "categories": categories,
        "category_types": PolicyType.CATEGORY_TYPES,
        "status_choices": PolicyType.STATUS_CHOICES
    })

# API Endpoints for Category Management
class CategoryAPIView(APIView):
    """API for listing and creating categories."""
    def get(self, request):
        # 1. Fetch all categories
        queryset = PolicyType.objects.all().order_by("-created_at")

        # 2. Serialize them (this calls the plans_count property)
        serializer = PolicyTypeSerializer(queryset, many=True)
        data = serializer.data

        # 3. Python-side filtering for hybrid data consistency
        search = request.query_params.get('search', '').lower()
        status_filter = request.query_params.get('status', 'all')
        plans_filter = request.query_params.get('plans', 'all')

        if search:
            data = [c for c in data if search in c['name'].lower() or search in c['code'].lower()]
        
        if status_filter != 'all':
            data = [c for c in data if c['status'] == status_filter]
            
        if plans_filter == 'has':
            data = [c for c in data if c['plans_count'] > 0]
        elif plans_filter == 'no':
            data = [c for c in data if c['plans_count'] == 0]

        return Response(data)

    def post(self, request):
        serializer = PolicyTypeSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class CategoryDetailAPIView(APIView):
    """API for managing individual categories."""
    def get_object(self, pk):
        try:
            return PolicyType.objects.get(pk=pk)
        except PolicyType.DoesNotExist:
            return None

    def get(self, request, pk):
        category = self.get_object(pk)
        if not category:
            return Response({"error": "Not Found"}, status=status.HTTP_404_NOT_FOUND)
        serializer = PolicyTypeSerializer(category)
        return Response(serializer.data)

    def put(self, request, pk):
        category = self.get_object(pk)
        if not category:
            return Response({"error": "Not Found"}, status=status.HTTP_404_NOT_FOUND)
        serializer = PolicyTypeSerializer(category, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        category = self.get_object(pk)
        if not category:
            return Response({"error": "Not Found"}, status=status.HTTP_404_NOT_FOUND)
        
        # Check if has plans
        if category.policyplan_set.exists():
            return Response({"error": "Cannot delete category with associated plans."}, status=status.HTTP_400_BAD_REQUEST)
            
        name = category.name
        category.delete()
        return Response({"message": f"Category '{name}' deleted successfully."}, status=status.HTTP_200_OK)


# =============================================================================
# BROWSE POLICIES (Policyholder catalog)
# =============================================================================
@login_required
def browse_policies(request):
    if request.user.role != "user":
        messages.error(request, "Access denied. Only policyholders can browse policies.")
        return redirect("accounts:login")


    # Only show admin-created catalog policies
    policies = Policy.objects.filter(is_active=True).order_by("-created_at")

    selected_type = request.GET.get('type')
    if selected_type:
        # Map friendly names to database codes if needed, or just use icontains
        policies = policies.filter(policy_type__icontains=selected_type)
        
        # 🔥 ELITE UX: If only one plan exists for this category, jump straight to its detail page
        if policies.count() == 1:
            return redirect("policy:detail", id=policies.first().public_id)

    # Map policy_id → existing application for this user (if any)
    user_applications = {
        str(app.policy.public_id): app
        for app in PolicyApplication.objects.filter(user=request.user)
    }

    return render(request, "policy/browse_policies.html", {
        "policies": policies,
        "user_applications": user_applications,
        "selected_type": selected_type,
    })


# =============================================================================
# APPLY FOR POLICY — Creates a PolicyApplication (PENDING)
# =============================================================================
@login_required
def apply_policy(request, policy_id):
    if request.user.role != "user":
        messages.error(request, "Access denied. Only policyholders can apply for policies.")
        return redirect("accounts:login")


    policy = _get_policy_by_public_id_or_404(policy_id, is_active=True)
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
            return redirect("policy:my_applications")
        elif existing.status == "approved":
            messages.info(request, "Your application for this policy has already been approved! Viewing your policy now.")
            return redirect("policy:detail", id=policy.public_id)
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
            return redirect("policy:apply", policy_id=policy.public_id)

        # ── 5. Motor validation ─────────────────────────────────────────────
        vehicle_num = request.POST.get("vehicle_number", "").strip()
        rc_file     = request.FILES.get("rc_upload")

        if is_motor and (not vehicle_num or not rc_file):
            messages.error(request, "Vehicle Number and RC Upload are required for Motor policies.")
            return redirect("policy:apply", policy_id=policy.public_id)

        # ── 6. Create PolicyApplication (PENDING) ───────────────────────────
        # Motor fields are stored directly on the application — NO draft Policy
        with transaction.atomic():
            application = PolicyApplication.objects.create(
                user=request.user,
                policy=policy,
                status="pending",
                vehicle_number=vehicle_num if is_motor else None,
                rc_upload=rc_file if (is_motor and rc_file) else None,
            )
            _create_pending_user_policy(application)

        create_notification(
            user=request.user,
            title="Application Submitted",
            message="Your policy application has been submitted and is under review."
        )
        _notify_admins_of_application(application)

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
    if request.user.role != "user":
        return render(request, "accounts/unauthorized.html")


    qs = PolicyApplication.objects.filter(user=request.user)
    applications = qs.select_related("policy", "reviewed_by").order_by("-created_at")

    return render(request, "policy/my_applications.html", {
        "applications": applications,
        "pending_count": qs.filter(status="pending").count(),
        "approved_count": qs.filter(status="approved").count(),
        "rejected_count": qs.filter(status="rejected").count(),
    })


@login_required
def user_application_detail(request, application_id):
    """View specific details of a policyholder's application."""
    if request.user.role != "user":
        return render(request, "accounts/unauthorized.html")

    application = get_object_or_404(
        PolicyApplication.objects.select_related("policy", "reviewed_by"),
        public_id=application_id,
        user=request.user
    )

    return render(request, "policy/application_detail.html", {
        "application": application,
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

    application = _get_policy_application_by_public_id_or_404(application_id)

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

        # ── HOLD (Place on Hold) ─────────────────────────────────────────────
        elif action == "hold":
            application.status = "pending"  # Keep it in pending but we can add a flag or just update remarks
            application.admin_remarks = f"[HOLD] {admin_remarks}"
            application.save()
            
            PolicyAuditLog.objects.create(
                policy=application.policy,
                performed_by=request.user,
                action="Application Placed on Hold",
                description=f"Admin {request.user.username} placed application for {application.user.username} on hold. Reason: {admin_remarks}",
            )
            messages.info(request, "Application has been placed on hold.")
            return redirect("policy:admin_applications")

        # ── REQUEST DOCUMENTS ────────────────────────────────────────────────
        elif action == "request_documents":
            application.status = "pending"
            application.admin_remarks = f"[DOCS_REQUESTED] {admin_remarks}"
            application.save()
            
            create_notification(
                user=application.user,
                title="Documents Requested",
                message=f"Additional documents are required for your policy application. Remark: {admin_remarks}"
            )
            
            PolicyAuditLog.objects.create(
                policy=application.policy,
                performed_by=request.user,
                action="Documents Requested",
                description=f"Admin {request.user.username} requested additional documents from {application.user.username}.",
            )
            messages.warning(request, "Document request sent to the user.")
            return redirect("policy:admin_applications")

        # ── REJECT ───────────────────────────────────────────────────────────
        elif action == "reject":
            application.status = "rejected"
            application.reviewed_at = timezone.now()
            application.reviewed_by = request.user
            application.admin_remarks = admin_remarks
            application.save()
            user_policy = UserPolicy.objects.filter(
                user=application.user,
                policy=application.policy,
                is_paid=False,
            ).exclude(status="active").first()
            if user_policy and user_policy.status != "rejected":
                update_fields = ["status"]
                user_policy.status = "rejected"
                if application.vehicle_number and user_policy.vehicle_number != application.vehicle_number:
                    user_policy.vehicle_number = application.vehicle_number
                    update_fields.append("vehicle_number")
                if application.rc_upload and user_policy.rc_upload != application.rc_upload:
                    user_policy.rc_upload = application.rc_upload
                    update_fields.append("rc_upload")
                user_policy.save(update_fields=update_fields)

            # 🔔 NOTIFICATION: Application Rejected
            create_notification(
                user=application.user,
                title="Application Rejected",
                message="Your policy application was rejected. Please contact support for details."
            )

            messages.error(request, f"Application for {application.user.username} has been rejected.")
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
                amount = user_schedule.installment_amount
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
                payment_status='pending',
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

    # ── Calculate Dynamic Risk Intelligence ────────────────────────────────
    user = application.user
    
    # 1. Identity Match (Base: 100 if verified, 60 if not)
    identity_match = 100.0 if user.is_verified else 60.0
    
    # 2. OCR Reliability (Real Fuzzy Matching!)
    has_docs = bool(application.rc_upload or user.id_proof)
    
    ocr_reliability = 0.0
    if has_docs:
        from ai_features.utils.name_matcher import validate_name_match
        from accounts.models import AadhaarKYCVerification
        
        # Fetch the latest OCR extraction for this user
        kyc = AadhaarKYCVerification.objects.filter(user=user).order_by('-created_at').first()
        
        if kyc and kyc.extracted_name:
            # Compare OCR Extracted Name vs Database Registered Name
            match_result = validate_name_match(kyc.extracted_name, user.get_full_name_clean)
            ocr_reliability = match_result['similarity'] * 100.0
        else:
            ocr_reliability = 75.0 # Fallback if no OCR extraction is found
    
    # 3. Registry Verified Bonus (+15)
    registry_bonus = 15.0 if user.is_verified else 0.0
    
    # 4. No Mismatch Bonus (+10)
    no_mismatch_bonus = 10.0 if has_docs else 0.0
    
    # Calculation: (IM * 0.5) + (OCR * 0.25) + RegBonus + MismatchBonus
    raw_confidence = (identity_match * 0.50) + (ocr_reliability * 0.25) + registry_bonus + no_mismatch_bonus
    confidence_score = min(100.0, max(0.0, raw_confidence))
    
    # Risk Banding
    if confidence_score >= 90: risk_band = "Very High"
    elif confidence_score >= 75: risk_band = "High"
    elif confidence_score >= 60: risk_band = "Moderate"
    else: risk_band = "Low"

    context = {
        "application": application,
        "show_full_data": show_full_data,
        "masked_phone": mask_phone(application.user.phone),
        "masked_email": mask_email(application.user.email),
        "identity_match": identity_match,
        "ocr_reliability": ocr_reliability,
        "confidence_score": confidence_score,
        "risk_band": risk_band,
        "is_registry_verified": user.is_verified,
        "no_mismatch": has_docs, # Baseline for no mismatch if docs exist
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
        "credit_payments": payments_qs.filter(Q(direction='CREDIT') | Q(direction__isnull=True)),
        "debit_payments": payments_qs.filter(direction='DEBIT'),
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

    payment = _get_payment_by_public_id_or_404(payment_id)

    if request.method == "POST":
        action = request.POST.get("action")
        
        # 🛡️ SECURITY: Only allow deletion for superusers or admins (not staff)
        if action == "delete":
            if request.user.is_superuser or request.user.role == "admin":
                txn_id = payment.transaction_id
                payment.delete()
                messages.success(request, f"Transaction {txn_id} has been voided and removed from the ledger.")
                return redirect("policy:payment_list")
            else:
                messages.error(request, "Permission Denied: Only Administrators can void transactions.")

        status = request.POST.get("payment_status")
        method = request.POST.get("payment_method")
        gateway_ref = request.POST.get("gateway_reference")
        description = request.POST.get("description")
        notes = request.POST.get("notes")

        if status in [choice[0] for choice in Payment.PAYMENT_STATUS_CHOICES]:
            payment.payment_status = status
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
        _sync_user_policy_after_payment_update(payment)

        messages.success(request, f"Payment {payment.transaction_id} updated successfully.")
        return redirect("policy:payment_list")


    return render(request, "policy/manage_payment.html", {
        "payment": payment,
        "status_choices": Payment.PAYMENT_STATUS_CHOICES,
        "method_choices": Payment.PAYMENT_METHOD_CHOICES,
    })


from django.http import JsonResponse


@login_required
def buy_policy(request, policy_id):
    """
    Realistic 'Buy Policy' workflow.
    Creates a PENDING PolicyApplication for admin review.
    """
    if request.method != "POST":
        return JsonResponse({'error': 'Only POST method is allowed'}, status=405)

    # 1. Check if policy exists
    try:
        policy = Policy.objects.get(public_id=policy_id)
    except Policy.DoesNotExist:
        return JsonResponse({'error': 'Policy not found.'}, status=404)

    # 2. Prevent duplicate applications (unless status is 'rejected')
    # Filter by user and policy, and exclude rejected statuses to avoid blocking valid reapplies
    existing_application = PolicyApplication.objects.filter(
        user=request.user,
        policy=policy
    ).first()

    if existing_application:
        return JsonResponse({
            'error': 'You have already applied for this policy. Please check My Applications.'
        }, status=400)

    existing_user_policy = UserPolicy.objects.filter(
        user=request.user,
        policy=policy
    ).exclude(status='rejected').first()
    if existing_user_policy:
        return JsonResponse({
            'error': 'This policy is already linked to your account. Please check My Policies.'
        }, status=400)

    # 3. Create the same pending application record used by admin review
    # and lock the payable premium inside UserPolicy.
    with transaction.atomic():
        application = PolicyApplication.objects.create(
            user=request.user,
            policy=policy,
            status='pending',
        )
        user_policy = _create_pending_user_policy(application)

    # 🔔 NOTIFICATION: Application Submitted
    create_notification(
        user=request.user,
        title="Application Submitted",
        message="Your policy application has been submitted and is under review."
    )
    _notify_admins_of_application(application)

    # 4. Audit Log
    PolicyAuditLog.objects.create(
        policy=policy,
        performed_by=request.user,
        action="Policy Application Submitted",
        description=f"User {request.user.username} applied for {policy.policy_number}. Status: Pending."
    )

    return JsonResponse({
        'success': True,
        'message': f'Application for {policy.policy_number} submitted successfully!',
        'application_id': str(application.public_id),
        'premium': str(user_policy.final_premium)
    }, status=201)


# =============================================================================
# MAKE PAYMENT (User Action) — Activates the Policy
# =============================================================================
@login_required
@require_POST
def make_payment(request, user_policy_id):
    """
    Final step in the workflow:
    - Verifies 'APPROVED' status
    - Processes payment using backend 'final_premium'
    - Activates policy upon success
    """
    with transaction.atomic():
        try:
            user_policy = UserPolicy.objects.select_for_update().select_related("policy").get(
                public_id=user_policy_id,
                user=request.user,
            )
        except UserPolicy.DoesNotExist:
            return JsonResponse({'error': 'Policy record not found.'}, status=404)

        # 1. Validation Logic
        if user_policy.status != "approved":
            return JsonResponse({'error': 'Only approved policies can be paid for.'}, status=400)
        
        if user_policy.is_paid:
            return JsonResponse({'error': 'This policy is already paid.'}, status=400)

        if user_policy.final_premium is None:
            user_policy.final_premium = user_policy.policy.calculate_final_premium()
            user_policy.save(update_fields=["final_premium"])

        # 2. Get Amount (Backend Controlled) - Charge current installment if exists, else total
        due = user_policy.current_due_payment
        amount = due.amount if due else user_policy.final_premium

        # 3. Create Payment Record (CREDIT)
        payment = Payment.objects.create(
            user=request.user,
            user_policy=user_policy,
            amount=amount,
            payment_status='completed',
            payment_type='PREMIUM_PAYMENT',
            direction='CREDIT',
            payment_method='upi',
            payment_metadata={'premium_source': 'new_policy'},
            description=f"Activation Payment - {user_policy.policy.policy_number}"
        )

        # 4. Update Policy Status (Activation)
        _sync_user_policy_after_payment_update(payment)

    # 5. Trigger Notification
    create_notification(
        user=user_policy.user,
        title="Payment Successful",
        message="Your payment is successful. Policy is now active."
    )

    # 6. Audit Trail
    PolicyAuditLog.objects.create(
        policy=user_policy.policy,
        performed_by=request.user,
        action="Payment Received & Activation",
        description=f"Initial premium of {amount} paid. Policy {user_policy.certificate_number} is now ACTIVE."
    )

    return JsonResponse({
        'success': True,
        'message': 'Payment successful. Your policy is now active!',
        'transaction_id': payment.transaction_id
    })
# =============================================================================
# ADMIN — Policy Plan List (Filtered by Category)
# =============================================================================
@login_required
def plan_list(request):
    if not (request.user.is_superuser or request.user.role in ["admin", "staff"]):
        return render(request, "accounts/unauthorized.html")

    category_id = request.GET.get('category')
    plans = PolicyPlan.objects.select_related('policy_type', 'insurer').all().order_by('-created_at')

    if category_id:
        plans = plans.filter(policy_type_id=category_id)
        selected_category = get_object_or_404(PolicyType, id=category_id)
    else:
        selected_category = None

    return render(request, "policy/admin_plans.html", {
        "plans": plans,
        "selected_category": selected_category,
        "categories": PolicyType.objects.all()
    })
@login_required
@require_POST
def api_generate_admin_note(request, application_id):
    """
    AJAX endpoint to generate a professional AI-powered verdict note
    based on application data and risk scoring.
    """
    if not (request.user.is_superuser or request.user.role in ["admin", "staff"]):
        return JsonResponse({'error': 'Unauthorized'}, status=403)

    application = _get_policy_application_by_public_id_or_404(application_id)
    decision = request.POST.get("decision", "ON_HOLD").upper()
    
    # 🔍 Fetch metrics (Actual data from User and Application)
    user = application.user
    
    # Check for document presence (ID Proof or Motor RC)
    has_docs = False
    if user.id_proof or (hasattr(user, 'profile') and user.profile.id_proof):
        has_docs = True
    if application.rc_upload:
        has_docs = True

    data = {
        "decision": decision,
        "risk_score": 0.08 if user.is_verified else 0.24, # Heuristic risk
        "verification_status": "VERIFIED" if user.is_verified else "PENDING",
        "document_status": "VALID" if has_docs else "UNVERIFIED",
        "fraud_flag": False 
    }

    from ai_features.services.verdict_service import generate_admin_note
    note = generate_admin_note(data)

    return JsonResponse({'note': note.strip()})
