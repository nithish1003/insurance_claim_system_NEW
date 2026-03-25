import calendar
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


def add_months(base_date: date, months: int) -> date:
    year = base_date.year + (base_date.month - 1 + months) // 12
    month = (base_date.month - 1 + months) % 12 + 1
    day = min(base_date.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def normalize_overdue(payments):
    today = timezone.now().date()
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
        policy = get_object_or_404(Policy, id=policy_id)

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
        return redirect("premiums:list")

    return render(request, "premiums/premium_create.html", {
        "policies": policies,
        "selected_policy_id": int(selected_policy_id) if selected_policy_id else None
    })


@login_required
def get_policy_premium_details(request, policy_id):
    """
    AJAX view to fetch premium details for a policy.
    """
    policy = get_object_or_404(Policy, id=policy_id)
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
        id=id
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
        payments = payments.annotate(
            status_order=Case(
                When(status="overdue", then=Value(0)),
                When(status="upcoming", then=Value(1)),
                default=Value(2),
                output_field=IntegerField(),
            )
        ).filter(
            Q(status="overdue") | Q(status="upcoming", due_date__lte=today)
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
        id=payment_id
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
            return redirect("premiums:detail", id=payment.schedule.id)

        # 1. Update the local PremiumPayment record
        transaction_reference = f"TXN-PREM-{timezone.now():%Y%m%d%H%M%S}-{get_random_string(6).upper()}"
        payment.status = "paid"
        payment.paid_date = timezone.now().date()
        payment.transaction_reference = transaction_reference
        payment.save(update_fields=["status", "paid_date", "transaction_reference"])

        # 2. 💸 Create a Unified Ledger Entry (CREDIT)
        if payment.schedule and payment.schedule.user_policy:
            Payment.objects.create(
                user_policy=payment.schedule.user_policy,
                amount=payment.amount,
                payment_status='completed',
                payment_type='PREMIUM_PAYMENT',
                direction='CREDIT',
                payment_method='upi', 
                transaction_id="", # Handled by model save() TXN-PREM- prefix
                gateway_reference=transaction_reference, 
                description=f"Premium Installment #{payment.installment_number} - {payment.schedule.policy.policy_number}"
            )

        # 🔄 REACTIVATION: Sync policy status immediately after payment
        if payment.schedule.user_policy:
            payment.schedule.user_policy.sync_status_with_premiums()

        messages.success(request, "Payment recorded successfully. Your policy status has been synchronized.")
        return redirect("premiums:detail", id=payment.schedule.id)

    return render(request, "premiums/premium_pay.html", {"payment": payment})


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
