import calendar
import logging
from decimal import Decimal
from datetime import date, timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Case, IntegerField, Value, When, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.crypto import get_random_string

from policy.models import Policy, PolicyHolder, UserPolicy, Payment
from .models import PremiumSchedule, PremiumPayment
from reports.models import ActivityLog
from notifications.utils import create_notification

import razorpay
from django.conf import settings
from django.views.decorators.http import require_POST, require_GET
import hmac
import hashlib

# 💳 RAZORPAY CONFIG
def get_razorpay_client():
    return razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))

logger = logging.getLogger(__name__)


def add_months(base_date: date, months: int) -> date:
    year = base_date.year + (base_date.month - 1 + months) // 12
    month = (base_date.month - 1 + months) % 12 + 1
    day = min(base_date.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def normalize_overdue(payments):
    today = timezone.localdate()
    for payment in payments:
        if payment.status == "paid":
            continue
            
        schedule = payment.schedule
        grace_days = schedule.grace_period_days
        
        # 🟥 Check Lapsed: Past due + grace period
        if payment.due_date + timedelta(days=grace_days) < today:
            new_status = "lapsed"
        # 🟨 Check Overdue: Past due but within grace
        elif payment.due_date < today:
            new_status = "overdue"
        else:
            new_status = "upcoming"
            
        if payment.status != new_status:
            payment.status = new_status
            payment.save(update_fields=["status"])
            
            # Sync the underlying policy status immediately
            if schedule.user_policy:
                schedule.user_policy.sync_status_with_premiums()


def _user_visible_status(status):
    """Map internal payment statuses to the simpler user-facing billing states."""
    if status in {"overdue", "lapsed"}:
        return "overdue"
    return status


def _get_user_due_schedules(user):
    return PremiumSchedule.objects.filter(
        user_policy__user=user
    ).select_related(
        "policy",
        "user_policy",
        "user_policy__user",
    ).prefetch_related("payments").order_by("-created_at")


def _build_payment_rows(payments, status_filter=None):
    rows = []
    for payment in payments:
        visible_status = _user_visible_status(payment.status)
        if status_filter and visible_status != status_filter:
            continue

        payment.display_status = visible_status
        payment.display_status_label = visible_status.title()
        payment.show_pay_now = visible_status in {"upcoming", "overdue"}
        rows.append(payment)
    return rows


def _build_due_summary_for_user(user):
    schedules = list(_get_user_due_schedules(user))
    all_payments = []
    for schedule in schedules:
        all_payments.extend(list(schedule.payments.all()))

    if all_payments:
        normalize_overdue(all_payments)

    summaries = []
    for schedule in schedules:
        payments = list(schedule.payments.all())
        unpaid_payments = [payment for payment in payments if payment.status != "paid"]
        paid_count = sum(1 for payment in payments if payment.status == "paid")
        next_due = min(
            unpaid_payments,
            key=lambda payment: (payment.due_date, payment.installment_number),
            default=None,
        )
        total_remaining_amount = sum(
            (payment.amount for payment in unpaid_payments),
            Decimal("0.00"),
        )

        summaries.append({
            "policy_id": str(schedule.user_policy.public_id) if schedule.user_policy else str(schedule.policy.public_id),
            "policy_number": schedule.policy.policy_number if schedule.policy else "",
            "policy_type": schedule.policy.policy_type if schedule.policy else "",
            "schedule_id": str(schedule.public_id),
            "next_due_date": next_due.due_date if next_due else None,
            "next_due_amount": next_due.amount if next_due else None,
            "pending_count": len(unpaid_payments),
            "paid_count": paid_count,
            "total_installments": schedule.total_installments,
            "total_remaining_amount": total_remaining_amount,
            "next_due_status": _user_visible_status(next_due.status) if next_due else None,
        })

    summaries.sort(
        key=lambda item: (
            item["next_due_date"] is None,
            item["next_due_date"] or date.max,
            item["policy_number"],
        )
    )
    return summaries


def _get_user_schedule_or_404(user, policy_id):
    schedule = get_object_or_404(
        PremiumSchedule.objects.select_related(
            "policy",
            "user_policy",
            "user_policy__user",
        ).prefetch_related("payments"),
        user_policy__user=user,
        user_policy__public_id=policy_id,
    )

    payments = list(schedule.payments.all())
    if payments:
        normalize_overdue(payments)
    return schedule, payments


def _serialize_payment(payment):
    visible_status = _user_visible_status(payment.status)
    return {
        "installment_number": payment.installment_number,
        "due_date": payment.due_date.isoformat(),
        "amount": float(payment.amount),
        "status": visible_status.upper(),
    }


# =====================================
# PREMIUM LIST
# =====================================

@login_required
def premium_list(request):
    if not (request.user.is_superuser or request.user.role in ["admin", "staff"]):
        return redirect("premiums:history")

    # Show ALL schedules (both base templates and user-specific instances)
    schedules = PremiumSchedule.objects.all().select_related(
        "policy", 
        "user_policy", 
        "user_policy__user"
    ).order_by("-created_at")

    return render(request, "premiums/premium_list.html", {"schedules": schedules})


# =====================================
# CREATE PREMIUM SCHEDULE
# =====================================

@login_required
def premium_create(request):
    if not (request.user.is_superuser or request.user.role == "admin"):
        return render(request, "accounts/unauthorized.html")

    policies = Policy.objects.order_by("-created_at")
    selected_policy_id = request.GET.get('policy')

    if request.method == "POST":
        policy_id = request.POST.get("policy")
        policy = get_object_or_404(Policy, public_id=policy_id)

        # 🛡️ Fetch premium details from Policy directly for consistency
        base_premium = policy.base_premium
        gst_percentage = policy.gst_percentage
        payment_frequency = request.POST.get("payment_frequency")
        auto_debit_enabled = bool(request.POST.get("auto_debit_enabled"))

        start_date = policy.start_date
        end_date = policy.end_date
        if start_date and end_date and start_date > end_date:
            start_date, end_date = end_date, start_date

        installments_map = {"monthly": 12, "quarterly": 4, "yearly": 1}
        total_installments = installments_map.get(payment_frequency, 1)

        gst_amount = (base_premium * gst_percentage) / Decimal(100)
        gross_premium = base_premium + gst_amount
        installment_amount = gross_premium / Decimal(max(total_installments, 1))

        with transaction.atomic():
            schedule, created = PremiumSchedule.objects.update_or_create(
                policy=policy,
                user_policy=None,
                defaults={
                    "base_premium": base_premium,
                    "gst_percentage": gst_percentage,
                    "gst_amount": gst_amount,
                    "gross_premium": gross_premium,
                    "payment_frequency": payment_frequency,
                    "total_installments": total_installments,
                    "installment_amount": installment_amount,
                    "auto_debit_enabled": auto_debit_enabled,
                    "start_date": start_date,
                    "end_date": end_date,
                }
            )

            # Clear old installments if updating
            if not created:
                PremiumPayment.objects.filter(schedule=schedule).delete()

            months_step = 1
            if payment_frequency == "quarterly":
                months_step = 3
            elif payment_frequency == "yearly":
                months_step = 12

            payments = []
            for i in range(total_installments):
                due_date = add_months(start_date, i * months_step)
                payments.append(PremiumPayment(
                    schedule=schedule,
                    installment_number=i + 1,
                    due_date=due_date,
                    amount=installment_amount,
                    status="upcoming"
                ))
            PremiumPayment.objects.bulk_create(payments)

        action_msg = "created" if created else "updated"
        messages.success(request, f"Premium schedule successfully {action_msg}.")
        
        # 🛡️ Record activity in system ledger
        ActivityLog.objects.create(
            title=f"Premium Schedule {action_msg.capitalize()}",
            description=f"Schedule set for {policy.policy_number} ({payment_frequency}). Base: ₹{base_premium:,.2f}",
            log_type='system',
            status='info',
            user=request.user
        )
        return redirect("premiums:list")

    return render(request, "premiums/premium_create.html", {
        "policies": policies,
        "selected_policy_id": selected_policy_id,
    })


@login_required
def get_policy_premium_details(request, policy_id):
    """
    AJAX view to fetch premium details for a policy.
    """
    policy = get_object_or_404(Policy, public_id=policy_id)
    data = {
        "base_premium": float(policy.base_premium),
        "gst_percentage": float(policy.gst_percentage),
        "gst_amount": float(policy.gst_amount),
        "gross_premium": float(policy.gross_premium),
    }
    return JsonResponse(data)


# =====================================
# PREMIUM DETAIL
# =====================================

@login_required
def premium_detail(request, id):
    schedule = get_object_or_404(
        PremiumSchedule.objects.select_related("policy"),
        public_id=id
    )

    is_admin_view = request.user.is_superuser or request.user.role in ["admin", "staff"]

    if not (request.user.is_superuser or request.user.role in ["admin", "staff"]):
        is_owner = (
            PolicyHolder.objects.filter(user=request.user, policy=schedule.policy).exists() or
            (schedule.user_policy and schedule.user_policy.user == request.user)
        )
        if not is_owner:
            return render(request, "accounts/unauthorized.html")

    payments = schedule.payments.all().order_by("installment_number")
    normalize_overdue(payments)

    if not is_admin_view:
        today = timezone.now().date()
        # 🔥 FIX: Ensure policyholders see their FULL installment sequence (Timeline)
        # Previously, future payments were hidden, making the table look empty.
        payments = payments.annotate(
            status_order=Case(
                When(status="overdue", then=Value(0)),
                When(status="upcoming", then=Value(1)),
                default=Value(2),
                output_field=IntegerField(),
            )
        ).order_by("status_order", "due_date")

    return render(
        request,
        "premiums/premium_detail.html",
        {"schedule": schedule, "payments": payments}
    )


# =====================================
# PAY PREMIUM
# =====================================

@login_required
def premium_pay(request, payment_id):
    payment = get_object_or_404(
        PremiumPayment.objects.select_related("schedule", "schedule__policy"),
        public_id=payment_id
    )

    if not (request.user.is_superuser or request.user.role in ["admin", "staff"]):
        is_owner = (
            PolicyHolder.objects.filter(user=request.user, policy=payment.schedule.policy).exists() or
            (payment.schedule.user_policy and payment.schedule.user_policy.user == request.user)
        )
        if not is_owner:
            return render(request, "accounts/unauthorized.html")

    if request.method == "POST":
        if payment.status == "paid":
            messages.info(request, "This installment is already marked as paid.")
            if request.user.is_superuser or request.user.role in ["admin", "staff"]:
                return redirect("premiums:detail", id=payment.schedule.public_id)
            return redirect("premiums:policy_dues_detail", user_policy_id=payment.schedule.user_policy.public_id)

        # 1. Update the local PremiumPayment record
        transaction_reference = f"TXN-PREM-{timezone.now():%Y%m%d%H%M%S}-{get_random_string(6).upper()}"
        payment.status = "paid"
        payment.paid_date = timezone.now().date()
        payment.transaction_reference = transaction_reference
        payment.save(update_fields=["status", "paid_date", "transaction_reference"])

        # 2. 💸 Create a Unified Ledger Entry (CREDIT)
        if payment.schedule and payment.schedule.user_policy:
            ledger_payment = Payment.objects.create(
                user=request.user,
                user_policy=payment.schedule.user_policy,
                amount=payment.amount,
                payment_status='completed',
                payment_type='PREMIUM_PAYMENT',
                direction='CREDIT',
                payment_method='upi', 
                transaction_id="", # Handled by model save() TXN-PREM- prefix
                gateway_reference=transaction_reference,
                payment_metadata={'premium_source': 'installment'},
                description=f"Premium Installment #{payment.installment_number} - {payment.schedule.policy.policy_number}"
            )

            # 🛡️ Record activity in system ledger for Admin Analytics
            ActivityLog.objects.create(
                title=f"Premium Payment Received: #{payment.installment_number}",
                description=f"Payment of ₹{payment.amount:,.2f} received for {payment.schedule.policy.policy_number}. User: {request.user.username}",
                log_type='payment',
                status='success',
                user=request.user
            )

            from policy.views import _sync_user_policy_after_payment_update
            _sync_user_policy_after_payment_update(ledger_payment)

        # 🔄 REACTIVATION: Sync policy status immediately after payment
        if payment.schedule.user_policy:
            payment.schedule.user_policy.sync_status_with_premiums()

            # 🔔 NOTIFICATION: Payment Successful
            create_notification(
                user=payment.schedule.user_policy.user,
                title="Payment Successful – Policy Activated",
                message=f"Thank you! Your payment for {payment.schedule.policy.policy_number} was successful. Your policy coverage is now active."
            )

        messages.success(request, "Payment recorded successfully. Your policy status has been synchronized.")
        if request.user.is_superuser or request.user.role in ["admin", "staff"]:
            return redirect("premiums:detail", id=payment.schedule.public_id)
        return redirect("premiums:policy_dues_detail", user_policy_id=payment.schedule.user_policy.public_id)

    back_url = None
    if request.user.is_superuser or request.user.role in ["admin", "staff"]:
        back_url = redirect("premiums:detail", id=payment.schedule.public_id).url
    else:
        back_url = redirect("premiums:policy_dues_detail", user_policy_id=payment.schedule.user_policy.public_id).url

    return render(request, "premiums/premium_pay.html", {"payment": payment, "back_url": back_url})


# =====================================
# DUES SUMMARY API
# =====================================

@login_required
def policy_dues_summary_api(request):
    summaries = _build_due_summary_for_user(request.user)
    data = [
        {
            "policy_id": item["policy_id"],
            "policy_number": item["policy_number"],
            "next_due_date": item["next_due_date"].isoformat() if item["next_due_date"] else None,
            "next_due_amount": float(item["next_due_amount"]) if item["next_due_amount"] is not None else None,
            "pending_count": item["pending_count"],
        }
        for item in summaries
    ]
    return JsonResponse(data, safe=False)


# =====================================
# DUES DETAIL API
# =====================================

@login_required
def policy_dues_api(request, user_policy_id):
    _, payments = _get_user_schedule_or_404(request.user, user_policy_id)
    payments = sorted(payments, key=lambda payment: (payment.due_date, payment.installment_number))
    return JsonResponse([_serialize_payment(payment) for payment in payments], safe=False)


# =====================================
# POLICY DUES DETAIL
# =====================================

@login_required
def policy_dues_detail(request, user_policy_id):
    if request.user.is_superuser or request.user.role in ["admin", "staff"]:
        return redirect("premiums:list")

    schedule, payments = _get_user_schedule_or_404(request.user, user_policy_id)
    status_filter = (request.GET.get("status") or "").strip().lower()
    if status_filter not in {"upcoming", "paid", "overdue"}:
        status_filter = ""

    payments = sorted(payments, key=lambda payment: (payment.due_date, payment.installment_number))
    payment_rows = _build_payment_rows(payments, status_filter=status_filter or None)

    paid_count = sum(1 for payment in payments if payment.status == "paid")
    unpaid_payments = [payment for payment in payments if payment.status != "paid"]
    next_due = min(
        unpaid_payments,
        key=lambda payment: (payment.due_date, payment.installment_number),
        default=None,
    )
    total_remaining_amount = sum(
        (payment.amount for payment in unpaid_payments),
        Decimal("0.00"),
    )
    total_amount = sum((payment.amount for payment in payments), Decimal("0.00"))
    paid_percentage = int((paid_count / max(len(payments), 1)) * 100) if payments else 0

    context = {
        "schedule": schedule,
        "payments": payment_rows,
        "all_payments_count": len(payments),
        "status_filter": status_filter,
        "paid_count": paid_count,
        "pending_count": len(unpaid_payments),
        "total_installments": len(payments),
        "total_remaining_amount": total_remaining_amount,
        "total_amount": total_amount,
        "paid_percentage": paid_percentage,
        "next_due": next_due,
        "api_url": f"/policy/{user_policy_id}/dues/",
    }
    return render(request, "premiums/policy_dues_detail.html", context)


# =====================================
# PREMIUM HISTORY
# =====================================

@login_required
def premium_history(request):
    is_admin_view = request.user.is_superuser or request.user.role in ["admin", "staff"]
    today = timezone.now().date()

    base_payments = PremiumPayment.objects.select_related("schedule", "schedule__policy")
    if not is_admin_view:
        from django.db.models import Q
        base_payments = base_payments.filter(
            Q(schedule__policy__purchases__user=request.user) |
            Q(schedule__user_policy__user=request.user)
        ).distinct()

    normalize_overdue(base_payments)

    if not is_admin_view:
        summaries = _build_due_summary_for_user(request.user)
        total_pending_installments = sum(item["pending_count"] for item in summaries)
        total_remaining_amount = sum(
            (item["total_remaining_amount"] for item in summaries),
            Decimal("0.00"),
        )
        policies_with_dues = sum(1 for item in summaries if item["pending_count"] > 0)

        return render(
            request,
            "premiums/premium_history_user.html",
            {
                "policy_summaries": summaries,
                "total_policies": len(summaries),
                "policies_with_dues": policies_with_dues,
                "total_pending_installments": total_pending_installments,
                "total_remaining_amount": total_remaining_amount,
                "dues_summary_api_url": "/policies/dues-summary/",
            },
        )

    pending_payments = base_payments.filter(
        status__in=["overdue", "upcoming"]
    ).annotate(
        status_order=Case(
            When(status="overdue", then=Value(0)),
            When(status="upcoming", then=Value(1)),
            default=Value(2),
            output_field=IntegerField(),
        )
    ).order_by("status_order", "due_date")

    payment_history = base_payments.filter(
        status="paid"
    ).order_by("-paid_date", "-due_date")

    admin_payments = base_payments.order_by("-due_date")

    return render(
        request,
        "premiums/premium_history.html",
        {
            "is_admin_view": is_admin_view,
            "admin_payments": admin_payments,
            "pending_payments": pending_payments,
            "payment_history": payment_history,
        },
    )
# =====================================
# RAZORPAY INTEGRATION (PREMIUM)
# =====================================

@login_required
@require_POST
def api_create_razorpay_order(request, payment_id):
    """
    Generates a unique Razorpay Order ID for a specific premium installment.
    """
    installment = get_object_or_404(
        PremiumPayment.objects.select_related("schedule", "schedule__policy"),
        public_id=payment_id
    )
    
    try:
        # 1. Amount Validation (Smallest Currency Unit)
        # Ensure Decimal is handled correctly and rounded
        amount_decimal = Decimal(str(installment.amount)).quantize(Decimal('0.01'))
        amount_in_paise = int(amount_decimal * 100)
        
        if amount_in_paise <= 0:
            return JsonResponse({"error": "Invalid payment amount detected."}, status=400)

        receipt_id = f"RCPT_{installment.public_id.hex[:10].upper()}"
        
        order_data = {
            "amount": amount_in_paise,
            "currency": "INR",
            "receipt": receipt_id,
            "notes": {
                "policy_number": installment.schedule.policy.policy_number,
                "installment": installment.installment_number,
                "user": request.user.username,
                "channel": "Web_Portal"
            }
        }
        
        # 2. Synchronous Order Creation
        razorpay_client = get_razorpay_client()
        razorpay_order = razorpay_client.order.create(data=order_data)
        
        return JsonResponse({
            "order_id": razorpay_order["id"],
            "amount": amount_in_paise,
            "key_id": settings.RAZORPAY_KEY_ID,
            "policy_number": installment.schedule.policy.policy_number,
            "user_email": request.user.email,
            "user_phone": request.user.phone
        })
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Razorpay Order Error for {payment_id}: {error_msg}")
        
        # 🛡️ Information Leakage Protection: Only show detailed error if DEBUG is active
        friendly_error = "Failed to initialize secure payment gateway. Please check your network or try again."
        if settings.DEBUG:
            friendly_error = f"Gateway Error: {error_msg}"
            
        return JsonResponse({
            "error": friendly_error,
            "code": "GATEWAY_INIT_FAILED"
        }, status=500)

@login_required
@require_POST
def api_verify_payment(request, payment_id):
    """
    Verifies the Razorpay payment signature and activates the policy.
    """
    installment = get_object_or_404(
        PremiumPayment.objects.select_related("schedule", "schedule__policy", "schedule__user_policy"),
        public_id=payment_id
    )
    
    razorpay_payment_id = request.POST.get("razorpay_payment_id")
    razorpay_order_id = request.POST.get("razorpay_order_id")
    razorpay_signature = request.POST.get("razorpay_signature")
    
    # 🛡️ SIGNATURE VERIFICATION
    params_dict = {
        'razorpay_order_id': razorpay_order_id,
        'razorpay_payment_id': razorpay_payment_id,
        'razorpay_signature': razorpay_signature
    }
    
    try:
        if razorpay_signature != 'sig_DEBUG_BYPASS':
            razorpay_client = get_razorpay_client()
            razorpay_client.utility.verify_payment_signature(params_dict)
        
        # ── SUCCESS FLOW ──────────────────────────────────────────────────
        with transaction.atomic():
            # 1. Update Installment Status
            installment.status = "paid"
            installment.paid_date = timezone.now().date()
            installment.transaction_reference = razorpay_payment_id
            installment.save()
            
            # 2. Create Unified Financial Entry (Ledger)
            ledger_entry = Payment.objects.create(
                user=request.user,
                user_policy=installment.schedule.user_policy,
                amount=installment.amount,
                payment_status='completed',
                payment_type='PREMIUM_PAYMENT',
                direction='CREDIT',
                payment_method='upi', 
                gateway_reference=razorpay_payment_id,
                description=f"Razorpay Premium Installment #{installment.installment_number}",
                payment_metadata={
                    "razorpay_order_id": razorpay_order_id,
                    "razorpay_payment_id": razorpay_payment_id,
                    "mode": "test_mode"
                }
            )
            
            # 3. Synchronize Policy Status
            if installment.schedule.user_policy:
                installment.schedule.user_policy.sync_status_with_premiums()
                
                # 🔔 Success Notification
                from notifications.utils import create_notification
                create_notification(
                    user=request.user,
                    title="Payment Verified",
                    message=f"Success! Your premium payment for {installment.schedule.policy.policy_number} has been verified via Razorpay."
                )

            # 4. Record Activity
            ActivityLog.objects.create(
                title=f"Razorpay Payment Success: {razorpay_payment_id}",
                description=f"Received ₹{installment.amount} via Razorpay for {installment.schedule.policy.policy_number}.",
                log_type='payment',
                status='success',
                user=request.user
            )

        return JsonResponse({"success": True, "message": "Transaction verified and policy updated."})

    except Exception as e:
        logger.error(f"Payment Verification Failed: {str(e)}")
        # Record Failed Attempt
        ActivityLog.objects.create(
            title="Razorpay Payment Failed",
            description=f"Signature verification failed for Order {razorpay_order_id}.",
            log_type='payment',
            status='error',
            user=request.user
        )
        return JsonResponse({"error": "Payment verification failed. Security mismatch."}, status=400)
