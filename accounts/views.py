from decimal import Decimal
from django.http import JsonResponse
from .otp_service import OTPService
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from .forms import RegisterForm, ProfileEditForm, CustomPasswordResetForm, CustomSetPasswordForm, ReuploadIDForm
from .models import AadhaarKYCVerification, User, UserProfile
from .decorators import admin_only, staff_or_admin, role_required, staff_only
from policy.models import Policy, PolicyHolder, PolicyApplication, UserPolicy, Payment
from premiums.models import PremiumSchedule, PremiumPayment
from django.core.exceptions import ValidationError
from django.db import models, transaction

from django.db.models import Sum, Count, Prefetch, Q, Value, Avg, F, ExpressionWrapper, FloatField, fields
from django.db.models.functions import Abs
from django.db.models.functions import Coalesce
from datetime import date, timedelta
from django.utils import timezone
from typing import Any
from django.urls import reverse
from claims.models import Claim, ClaimNote, ClaimAuditLog, ClaimSettlement
from claims.utils import get_visible_claims_q
from .utils import get_valid_pending_kyc, cleanup_pending_kyc_session, get_session_fingerprint
from ai_features.services.kyc_verification_service import save_kyc_record
import logging

logger = logging.getLogger(__name__)


@login_required
def home_redirect(request):
    """Dispatcher to route users to their role-specific dashboard."""
    if request.user.role == 'admin':
        return redirect('accounts:admin_dashboard')
    elif request.user.role == 'staff':
        return redirect('accounts:staff_dashboard')
    else:
        return redirect('accounts:policyholder_dashboard')


def unauthorized(request):
    """Fallback view for role-based access violations."""
    return render(request, "accounts/unauthorized.html")


def _build_admin_payment_metrics():
    premium_credit_qs = Payment.objects.filter(
        direction='CREDIT',
        payment_status='completed',
        payment_type__in=['PREMIUM_PAYMENT', 'PREMIUM'],
    )

    premium_collected = premium_credit_qs.aggregate(total=Sum("amount"))["total"] or 0
    successful_premium_transactions = premium_credit_qs.count()

    new_policy_premium_qs = premium_credit_qs.filter(
        Q(payment_metadata__premium_source='new_policy') |
        Q(description__icontains='Activation Payment')
    )
    installment_premium_qs = premium_credit_qs.filter(
        Q(payment_metadata__premium_source='installment') |
        Q(description__icontains='Premium Installment #')
    )

    failed_premium_transactions = Payment.objects.filter(
        direction='CREDIT',
        payment_status='failed',
        payment_type__in=['PREMIUM_PAYMENT', 'PREMIUM'],
    ).count()

    return {
        "premium_collected": premium_collected,
        "successful_premium_transactions": successful_premium_transactions,
        "premium_collected_new_policies": new_policy_premium_qs.aggregate(total=Sum("amount"))["total"] or 0,
        "premium_collected_installments": installment_premium_qs.aggregate(total=Sum("amount"))["total"] or 0,
        "failed_premium_transactions": failed_premium_transactions,
    }


def _build_admin_claim_payout_metrics():
    settled_payout_qs = ClaimSettlement.objects.all()

    return {
        "total_settled_amount": settled_payout_qs.aggregate(total=Sum("settled_amount"))["total"] or 0,
    }


def _build_admin_integrity_metrics():
    from django.db.models import Count, Sum, Avg, Q, F
    from django.utils import timezone
    from datetime import timedelta

    all_claims = Claim.objects.all()
    total_count = all_claims.count()
    
    if total_count == 0:
        return {
            "high_mismatch_count": 0,
            "recovered_leakage": 0,
            "critical_monthly_count": 0,
            "avg_integrity_gap": 0,
        }

    # Mismatch > 15% (Enterprise Severity Threshold)
    high_mismatch_count = all_claims.filter(claim_amount_mismatch_ratio__gt=0.15).count()
    
    # Recovered leakage: (Declared - Payout Basis)
    # We use a subquery/expression to find savings achieved by using OCR or manual basis
    recovered_leakage = all_claims.filter(
        claim_amount_mismatch_ratio__gt=0.05,
        payout_basis_amount__lt=F('declared_claim_amount')
    ).annotate(
        leakage=F('declared_claim_amount') - F('payout_basis_amount')
    ).aggregate(total=Sum('leakage'))['total'] or 0

    # Critical monthly count (>50% mismatch in last 30 days)
    last_30_days = timezone.now() - timedelta(days=30)
    critical_monthly_count = all_claims.filter(
        created_at__gte=last_30_days,
        claim_amount_mismatch_ratio__gt=0.50
    ).count()

    # Average integrity gap (mismatch ratio percentage)
    avg_integrity_gap = all_claims.aggregate(avg=Avg('claim_amount_mismatch_ratio'))['avg'] or 0
    avg_integrity_gap *= 100

    return {
        "high_mismatch_count": high_mismatch_count,
        "recovered_leakage": recovered_leakage,
        "critical_monthly_count": critical_monthly_count,
        "avg_integrity_gap": round(float(avg_integrity_gap), 1),
    }



# REGISTER

def register_view(request):
    """Renders the registration form GET request."""
    if request.user.is_authenticated:
        return redirect('accounts:home')
    form = RegisterForm()
    response = render(request, "accounts/register.html", {"form": form})
    return add_security_headers(response)


def add_security_headers(response):
    response['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response['Pragma'] = 'no-cache'
    response['Expires'] = '0'
    return response

def register_send_otp(request):
    """AJAX endpoint to validate basic info and dispatch OTPs."""
    if request.method != "POST":
        return JsonResponse({"success": False, "error": "Invalid request method."})

    # Validate the basic fields first
    form = RegisterForm(request.POST, request.FILES)
    # We only care about the basic fields for now, so we manually check them
    # instead of form.is_valid() which would fail on missing Aadhaar
    
    # We can check uniqueness manually to be fast
    email = request.POST.get('email')
    username = request.POST.get('username')
    phone = request.POST.get('phone')

    if User.objects.filter(username=username).exists():
        return JsonResponse({"success": False, "errors": {"username": "Username already exists."}})
    if User.objects.filter(email=email).exists():
        return add_security_headers(JsonResponse({"success": False, "errors": {"email": "Email already exists."}}))

    # Store basic fields in session
    request.session['reg_data'] = {
        'full_name': request.POST.get('full_name'),
        'username': username,
        'email': email,
        'phone': phone,
        'address': request.POST.get('address'),
        'password': request.POST.get('password'),
    }

    session_key = request.session.session_key
    if not session_key:
        request.session.create()
        session_key = request.session.session_key

    ip_address = request.META.get('REMOTE_ADDR')
    user_agent = request.META.get('HTTP_USER_AGENT', '')

    # Dispatch OTPs
    email_sent = OTPService.send_email_otp(email, session_key, ip_address=ip_address, user_agent=user_agent)
    sms_sent = OTPService.send_sms_otp(phone, session_key, ip_address=ip_address, user_agent=user_agent)

    if email_sent and sms_sent:
        from django.utils import timezone
        request.session["otp_resend_count"] = 0
        request.session["otp_sent_at"] = timezone.now().isoformat()
        request.session.modified = True
        return add_security_headers(JsonResponse({"success": True, "message": "OTP sent successfully."}))
    else:
        # If one fails, we still return false
        return add_security_headers(JsonResponse({"success": False, "message": "Failed to send OTP. Please check your network or try again."}))

def register_resend_otp(request):
    """AJAX endpoint to resend OTPs."""
    if request.method != "POST":
        return add_security_headers(JsonResponse({"success": False, "message": "Invalid request."}))

    session_key = request.session.session_key
    if not session_key:
        request.session.create()
        session_key = request.session.session_key

    reg_data = request.session.get('reg_data', {})
    email = reg_data.get('email')
    phone = reg_data.get('phone')

    if not email or not phone:
        return add_security_headers(JsonResponse({"success": False, "message": "Session expired. Please restart registration."}))

    from .models import OTPVerification
    from django.utils import timezone
    from datetime import datetime

    last_sent_iso = request.session.get("otp_sent_at")
    if last_sent_iso:
        last_sent_dt = datetime.fromisoformat(last_sent_iso)
        time_since = (timezone.now() - last_sent_dt).total_seconds()
        
        if time_since < 60:
            return add_security_headers(JsonResponse({
                "success": False, 
                "message": "Please wait before requesting another OTP."
            }))
        elif time_since >= 600:
            request.session["otp_resend_count"] = 0
            request.session["otp_sent_at"] = timezone.now().isoformat()
            request.session.modified = True

    resend_count = request.session.get("otp_resend_count", 0)
    if resend_count >= 3:
        return add_security_headers(JsonResponse({
            "success": False,
            "message": "Maximum resend attempts reached. Please wait for the current OTP to expire before requesting a new one."
        }))

    # Rotate OTPs before resending (delete previous unverified OTPs for this session)
    OTPVerification.objects.filter(session_key=session_key, purpose="email_verify", is_verified=False).delete()
    OTPVerification.objects.filter(session_key=session_key, purpose="phone_verify", is_verified=False).delete()

    ip_address = request.META.get('REMOTE_ADDR')
    user_agent = request.META.get('HTTP_USER_AGENT', '')

    try:
        email_sent = OTPService.send_email_otp(email, session_key, ip_address=ip_address, user_agent=user_agent)
        sms_sent = OTPService.send_sms_otp(phone, session_key, ip_address=ip_address, user_agent=user_agent)

        if email_sent and sms_sent:
            request.session["otp_resend_count"] = resend_count + 1
            request.session["otp_sent_at"] = timezone.now().isoformat()
            request.session.modified = True
            return add_security_headers(JsonResponse({"success": True, "message": "OTP sent successfully."}))
        else:
            return add_security_headers(JsonResponse({"success": False, "message": "Failed to resend OTPs."}))
    except Exception as e:
        return add_security_headers(JsonResponse({"success": False, "message": "An error occurred while sending OTPs."}))

def register_verify_otp(request):
    """AJAX endpoint to verify both OTPs."""
    if request.method != "POST":
        return add_security_headers(JsonResponse({"success": False, "error": "Invalid request."}))

    email_otp = request.POST.get('email_otp')
    sms_otp = request.POST.get('sms_otp')
    
    session_key = request.session.session_key
    if not session_key:
        request.session.create()
        session_key = request.session.session_key

    reg_data = request.session.get('reg_data', {})
    email = reg_data.get('email')
    phone = reg_data.get('phone')

    if not email or not phone:
        return add_security_headers(JsonResponse({"success": False, "error": "Session expired. Please restart registration."}))

    email_valid, email_err = OTPService.verify_otp(email, email_otp, 'email_verify', session_key)
    sms_valid, sms_err = OTPService.verify_otp(phone, sms_otp, 'phone_verify', session_key)

    if email_valid and sms_valid:
        request.session['otp_verified'] = True
        request.session.cycle_key()
        return add_security_headers(JsonResponse({"success": True}))
    else:
        errors = {}
        is_rate_limited = False
        if not email_valid: 
            errors['email_otp'] = email_err
            if "Maximum attempts reached" in email_err: is_rate_limited = True
        if not sms_valid: 
            errors['sms_otp'] = sms_err
            if "Maximum attempts reached" in sms_err: is_rate_limited = True
        
        status_code = 429 if is_rate_limited else 200
        return add_security_headers(JsonResponse({"success": False, "errors": errors}, status=status_code))

def register_complete(request):
    """Final submission endpoint (handles Aadhaar upload and User creation)."""
    if request.method != "POST":
        return redirect('accounts:register')

    if not request.session.get('otp_verified'):
        messages.error(request, "You must verify your email and phone before completing registration.")
        return redirect('accounts:register')

    # Re-hydrate POST with session data to use the form's clean() method for Aadhaar validation
    post_data = request.POST.copy()
    reg_data = request.session.get('reg_data', {})
    
    for key, value in reg_data.items():
        if key not in post_data:
            post_data[key] = value
            
    # We must also re-inject the confirm password so the form is happy
    if 'password' in reg_data and 'confirm_password' not in post_data:
        post_data['confirm_password'] = reg_data['password']

    form = RegisterForm(post_data, request.FILES)

    try:
        is_valid = form.is_valid()
        kyc_result = getattr(form, "kyc_result", None)

        user = None
        profile = None

        if is_valid:
            with transaction.atomic():
                user = form.save(commit=False)
                user.role = 'user'
                user.set_password(form.cleaned_data["password"])
                user.aadhaar_number = kyc_result.get("submitted_number")
                
                is_auto_verified = kyc_result.get("verified", False)
                user.is_verified = is_auto_verified
                user.verified_at = timezone.now() if is_auto_verified else None
                user.save()

                profile = UserProfile.objects.create(
                    user=user,
                    full_name=form.cleaned_data["full_name"],
                    aadhaar_number=user.aadhaar_number,
                    id_proof=request.FILES.get('id_proof'),
                    is_verified=is_auto_verified,
                    verification_status='VERIFIED' if is_auto_verified else 'PENDING'
                )

        if kyc_result:
            pending_record = get_valid_pending_kyc(request)
            previous_attempt_id = pending_record.id if pending_record else None
            
            try:
                if is_valid:
                    with transaction.atomic():
                        record = save_kyc_record(
                            user=user,
                            result=kyc_result,
                            expected_name=kyc_result.get("submitted_name"),
                            expected_number=kyc_result.get("submitted_number"),
                            file_name=kyc_result.get("filename"),
                            existing_id=previous_attempt_id
                        )
                        if profile:
                            record.profile = profile
                            record.save()
                else:
                    record = save_kyc_record(
                        user=None,
                        result=kyc_result,
                        expected_name=kyc_result.get("submitted_name"),
                        expected_number=kyc_result.get("submitted_number"),
                        file_name=kyc_result.get("filename"),
                        existing_id=previous_attempt_id
                    )

                if is_valid:
                    cleanup_pending_kyc_session(request)
                    # Also cleanup OTP session data and database records
                    request.session.pop('reg_data', None)
                    request.session.pop('otp_verified', None)
                    request.session.pop('otp_resend_count', None)
                    request.session.pop('otp_sent_at', None)
                    
                    from .models import OTPVerification
                    OTPVerification.objects.filter(session_key=request.session.session_key).delete()
                else:
                    request.session['pending_kyc_id'] = record.id
                    request.session['pending_kyc_created_at'] = timezone.now().isoformat()
                    request.session['pending_kyc_fingerprint'] = get_session_fingerprint(request)

            except Exception as kyc_err:
                logger.error(f"[KYC CRITICAL FAILURE] Persistence crashed: {str(kyc_err)}")

        if is_valid:
            from django.contrib.auth import login
            from notifications.utils import create_notification
            login(request, user)
            
            if user.is_verified:
                create_notification(
                    user=user,
                    title="Welcome to ClaimIQ",
                    message="Your account has been successfully created and your identity verified. You can now purchase policies and submit claims.",
                    type="success"
                )
                messages.success(request, "Your identity has been verified successfully.")
            else:
                create_notification(
                    user=user,
                    title="Welcome to ClaimIQ - Verification Pending",
                    message="Your account has been created, but your identity is pending manual verification. Our team will review it shortly.",
                    type="warning"
                )
                messages.info(request, "Your identity details require manual verification. Our team will review shortly.")
            
            return redirect("accounts:home")
        else:
             messages.warning(request, "Please fix the identity verification or data errors below.")

    except Exception as e:
        logger.error(f"CORRUPTION TRACE: {str(e)}", exc_info=True)
        messages.error(request, "A system error occurred. Please try again.")
        
    return render(request, "accounts/register.html", {"form": form})

# DASHBOARDS

@admin_only
def admin_dashboard(request):

    total_policies = Policy.objects.count()
    # 🔥 Governance FIX: Exclude drafts, closed, and withdrawn claims from active totals
    total_claims = Claim.objects.exclude(status__in=['draft', 'withdrawn', 'closed']).count()
    settled_claims = Claim.objects.filter(status="settled").count()
    
    # Debug Output for verification
    print(f"[AI Audit] Dashboard Sync - Total: {total_claims} | Settled: {settled_claims}")

    # Admin dashboard should prioritize and show claims sent by staff (now via Waiting Approval stage)
    waiting_approval_claims = Claim.objects.filter(status="staff_reviewed").count()
    submitted_claims = Claim.objects.filter(status="submitted").count()
    review_claims = Claim.objects.filter(status="under_review").count()
    investigation_claims = Claim.objects.filter(status="investigation").count()
    staff_reviewed_count = Claim.objects.filter(status="staff_reviewed").count()
    
    # "Approved Claims" should include all claims that passed approval (legacy label)
    approved_claims = Claim.objects.filter(status__in=["approved", "partially_approved"]).count()
    settled_claims_count = Claim.objects.filter(status="settled").count()
    rejected_claims = Claim.objects.filter(status="rejected").count()

    total_staffs = User.objects.filter(role="staff").count()
    total_premium = PremiumSchedule.objects.aggregate(
        total=Sum("gross_premium")
    )["total"] or 0

    # Show recent claims that specifically require ADMIN attention
    recent_claims = Claim.objects.filter(status__in=["staff_reviewed", "investigation"]).select_related('created_by', 'policy').order_by('-priority_score', '-created_at')[:8]
    
    # Get recent policies from both PolicyHolder and UserPolicy, but show unique policies only
    # Use a union query to get the most recent purchase/approval for each policy
    from django.db.models import Max
    
    # Get the latest purchase/approval date for each policy from both sources
    policyholder_latest = PolicyHolder.objects.values('policy_id').annotate(
        latest_date=Max('purchased_at')
    ).values('policy_id', 'latest_date')
    
    userpolicy_latest = UserPolicy.objects.values('policy_id').annotate(
        latest_date=Max('assigned_at')
    ).values('policy_id', 'latest_date')
    
    # Combine and get the most recent for each policy
    all_latest = list(policyholder_latest) + list(userpolicy_latest)
    
    # Group by policy_id and get the maximum date
    policy_dates = {}
    for entry in all_latest:
        policy_id = entry['policy_id']
        date_val = entry['latest_date']
        if policy_id not in policy_dates or date_val > policy_dates[policy_id]:
            policy_dates[policy_id] = date_val
    
    # Get the top 5 most recent policies
    recent_policy_ids = sorted(policy_dates.keys(), key=lambda x: policy_dates[x], reverse=True)[:5]
    
    # Fetch the actual policy records with user info (prioritize UserPolicy, fallback to PolicyHolder)
    recent_policies = []
    for policy_id in recent_policy_ids:
        # Try to get from UserPolicy first (newer system)
        user_policy = UserPolicy.objects.filter(policy_id=policy_id).select_related('user', 'policy').first()
        if user_policy:
            recent_policies.append(user_policy)
        else:
            # Fallback to PolicyHolder (legacy)
            policy_holder = PolicyHolder.objects.filter(policy_id=policy_id).select_related('user', 'policy').first()
            if policy_holder:
                recent_policies.append(policy_holder)

    # â”€â”€ AI Model Performance Tracking â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    from claims.models import AIModelMetrics
    from ai_features.services.metrics_service import update_regulator_governance_sync
    # Ensure fresh metrics for the dashboard view
    update_regulator_governance_sync() 
    
    # Query performance history (Last 7 Days) for trend analysis
    metrics_history = AIModelMetrics.objects.order_by('-date')[:2]
    latest_ai_metrics = metrics_history[0] if metrics_history.exists() else None
    
    # Calculate performance trend compared to previous cycle
    performance_trend = 0.0
    if metrics_history.count() >= 2:
        curr = metrics_history[0].health_score
        prev = metrics_history[1].health_score
        if prev > 0:
            performance_trend = ((curr - prev) / prev) * 100
    
    performance_trend_abs = abs(performance_trend)

    # â”€â”€ Policy Application data â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    pending_applications = PolicyApplication.objects.filter(status='pending').count()
    pending_policy_applications = PolicyApplication.objects.filter(
        status='pending'
    ).select_related("user", "policy").order_by("-created_at")[:8]

    # âœ… Calculate Total Approved Amount (Excluding rejected, including settled)
    total_approved_amount = Claim.objects.filter(
        status__in=["approved", "partially_approved", "settled"]
    ).aggregate(
        total=Sum(Coalesce("approved_amount", "final_ai_recommendation", Value(0, output_field=models.DecimalField())))
    )["total"] or 0

    # ðŸ’³ Payment Statistics (Summing only successful transactions for actual revenue)
    # Using Payment model as the Unified Source of Truth to avoid double-counting installments
    payment_metrics = _build_admin_payment_metrics()
    claim_payout_metrics = _build_admin_claim_payout_metrics()
    integrity_metrics = _build_admin_integrity_metrics()


    # Recent payment history for dashboard
    recent_payments = Payment.objects.select_related(
        'user_policy', 
        'user_policy__user', 
        'user_policy__policy'
    ).order_by('-created_at')[:10]

    recent_settlements = ClaimSettlement.objects.select_related(
        'claim', 'claim__policy', 'claim__created_by'
    ).order_by('-settlement_date')[:10]

    # ðŸ’³ Unified Transaction Ledger (Clean Source of Truth)
    all_payments = Payment.objects.select_related(
        'user_policy', 'user_policy__user', 'user_policy__policy', 'claim'
    ).order_by('-created_at')[:10]

    recent_financial_transactions = []
    for p in all_payments:
        recent_financial_transactions.append({
            'direction': p.direction,
            'payment_type_display': p.get_payment_type_display() or "Transaction",
            'id': p.transaction_id,
            'user': p.user_policy.user.get_full_name() or p.user_policy.user.username if p.user_policy else "System",
            'policy': p.user_policy.policy.policy_number if (p.user_policy and p.user_policy.policy) else "Internal",
            'amount': p.amount,
            'status': p.payment_status,
            'method': p.get_payment_method_display(),
            'date': p.created_at,
            'audit_url': reverse('policy:manage_payment', args=[p.public_id]),
        })

    context = {
        "total_users": User.objects.filter(role='user').count(),
        "total_staffs": total_staffs,
        "total_policies": total_policies,
        "total_claims": total_claims,
        "waiting_approval_claims": waiting_approval_claims,
        "submitted_claims": submitted_claims,
        "review_claims": review_claims,
        "investigation_claims": investigation_claims,
        "settled_claims": settled_claims_count,
        "approved_claims": approved_claims,
        "rejected_claims": rejected_claims,
        "total_premium": total_premium,
        "total_settled_amount": claim_payout_metrics["total_settled_amount"],
        "total_approved_amount": total_approved_amount,
        "premium_collected": payment_metrics["premium_collected"],
        "successful_premium_transactions": payment_metrics["successful_premium_transactions"],
        "premium_collected_new_policies": payment_metrics["premium_collected_new_policies"],
        "premium_collected_installments": payment_metrics["premium_collected_installments"],
        "failed_premium_transactions": payment_metrics["failed_premium_transactions"],
        "recent_claims": recent_claims,
        "recent_policies": recent_policies,
        "recent_financial_transactions": recent_financial_transactions,
        "pending_applications": pending_applications,
        "pending_policy_applications": pending_policy_applications,
        "current_user": request.user,
        "ai_metrics": latest_ai_metrics,
        "ai_performance_trend": performance_trend,
        "ai_performance_trend_abs": performance_trend_abs,
        "integrity_metrics": integrity_metrics,
        
        # ðŸ›¡ï¸ KYC GOVERNANCE (Requirement: Resolve Empty User Directory)
        # We prefetch verification status to avoid N+1 queries during rendering
        "total_kyc_pending": AadhaarKYCVerification.objects.filter(status__in=['manual_review', 'pending'], user__role='user').count(),
        "total_kyc_verified": AadhaarKYCVerification.objects.filter(status='verified', user__role='user').count(),
        "total_kyc_rejected": AadhaarKYCVerification.objects.filter(status='rejected', user__role='user').count(),
        "users": User.objects.filter(role='user').exclude(is_superuser=True).order_by('-date_joined').prefetch_related('kyc_verifications')[:100],
        
        "staff_list": User.objects.filter(role='staff').order_by('-date_joined'),
        "policies": UserPolicy.objects.select_related('policy', 'user').order_by('-assigned_at')[:50],
        # ðŸ›¡ï¸ SYSTEM INVENTORY (Requirement: Resolve Empty System Policies Table)
        "all_policies": Policy.objects.all().order_by("-created_at"),
        
        # Categorized Claims
        "staff_reviewed_list": Claim.objects.filter(status="staff_reviewed").order_by("-created_at")[:20],
        "submitted_claims_list": Claim.objects.filter(status="submitted").order_by("-created_at")[:20],
        "investigation_claims_list": Claim.objects.filter(status="investigation").order_by("-created_at")[:20],
        "review_claims_list": Claim.objects.filter(status="under_review").order_by("-created_at")[:20],
        "approved_claims_list": Claim.objects.filter(status__in=["approved", "partially_approved"]).order_by("-created_at")[:20],
        "rejected_claims_list": Claim.objects.filter(status="rejected").order_by("-created_at")[:20],
        "settled_claims_list": Claim.objects.filter(status="settled").order_by("-created_at")[:20],
        "integrity_claims": Claim.objects.filter(claim_amount_mismatch_ratio__gt=0.05).select_related('created_by', 'policy').order_by('-claim_amount_mismatch_ratio')[:15],
        # Financial Lists (with deduplication for schedules)
        "success_payments": Payment.objects.filter(payment_status="completed").order_by("-created_at")[:20],
        "failed_payments": Payment.objects.filter(payment_status="failed").order_by("-created_at")[:20],
        "ai_metrics_history": AIModelMetrics.objects.order_by("-date")[:10],
    }

    # Deduplicate Premium Schedules by Policy in Python (MySQL/SQLite compatibility)
    all_schedules = PremiumSchedule.objects.all().select_related('policy').order_by("-created_at")
    seen_policies = set()
    deduped_schedules = []
    for s in all_schedules:
        p_num = s.policy.policy_number if s.policy else "N/A"
        if p_num not in seen_policies:
            deduped_schedules.append(s)
            seen_policies.add(p_num)
    
    context["premium_schedules_list"] = deduped_schedules[:20]

    return render(request, "accounts/dashboard_admin.html", context)


@staff_or_admin
def staff_dashboard(request):
    from policy.models import Payment
    from claims.models import ClaimSettlement

    # Initial Queryset - Sorted by AI Priority Score to help staff focus
    claims_qs = Claim.objects.select_related('assessment', 'policy', 'created_by').order_by('-priority_score', '-created_at').distinct()

    # Advanced Filtering (Status, Type, Search)
    status_filter = request.GET.get('status')
    type_filter = request.GET.get('type')
    search_query = request.GET.get('q')
    search_type = request.GET.get('search_type', 'all')

    if status_filter:
        claims_qs = claims_qs.filter(status=status_filter)
    if type_filter:
        claims_qs = claims_qs.filter(claim_type=type_filter)
    
    if search_query:
        if search_type == 'claim':
            claims_qs = claims_qs.filter(claim_number__icontains=search_query)
        elif search_type == 'policy':
            claims_qs = claims_qs.filter(policy__policy_number__icontains=search_query)
        elif search_type == 'name':
            claims_qs = claims_qs.filter(
                Q(created_by__username__icontains=search_query) |
                Q(created_by__first_name__icontains=search_query) |
                Q(created_by__last_name__icontains=search_query)
            )
        else: # 'all'
            claims_qs = claims_qs.filter(
                Q(claim_number__icontains=search_query) | 
                Q(created_by__username__icontains=search_query) |
                Q(policy__policy_number__icontains=search_query)
            )

    # Prefetch notes, documents and audit logs (Optimization)
    claims_qs = claims_qs.prefetch_related(
        'documents', 
        Prefetch('notes', queryset=ClaimNote.objects.select_related('created_by')),
        Prefetch('audit_logs', queryset=ClaimAuditLog.objects.select_related('performed_by'))
    )

    # KPI & Global Summary metrics
    # Staff cards should reflect the live operational workflow, not archived seed rows.
    kpi_claims = Claim.objects.exclude(status__in=["closed", "withdrawn"])
    total_claims = kpi_claims.count()
    status_counts = kpi_claims.values('status').annotate(count=Count('id'))
    
    # Specific KPI for top cards (Workflow aligned)
    kpi = {
        'total_claims': total_claims,
        'submitted_claims': kpi_claims.filter(status="submitted").count(),
        'review_claims': kpi_claims.filter(status="under_review").count(),
        'waiting_approval_claims': kpi_claims.filter(status="staff_reviewed").count(),
        'investigation_claims': kpi_claims.filter(status="investigation").count(),
        'settled_claims': kpi_claims.filter(status="settled").count(),
        'processed_claims': kpi_claims.filter(status__in=["approved", "rejected", "settled", "partially_approved"]).count(),
    }
    
    claim_status_summary = []
    for s in status_counts:
        status = s['status']
        count = s['count']
        pct = (count / total_claims * 100) if total_claims > 0 else 0
        
        bar_class = 'bg-secondary'
        if status in ['approved', 'settled']: bar_class = 'bg-success'
        elif status in ['under_review', 'investigation', 'staff_reviewed']: bar_class = 'bg-warning'
        elif status == 'submitted': bar_class = 'bg-primary'
        elif status == 'rejected': bar_class = 'bg-danger'
        
        claim_status_summary.append({
            'label': status.replace('_', ' ').title(),
            'count': count,
            'percentage': pct,
            'bar_class': bar_class
        })

    # Policy information for the inventory screen
    all_policies = Policy.objects.all().order_by("-created_at")

    # Efficiency Rate
    total_handled = kpi_claims.exclude(status='draft').count()
    success_count = kpi_claims.filter(status__in=['approved', 'settled', 'partially_approved']).count()
    efficiency = (success_count / total_handled * 100) if total_handled > 0 else 0

    # Monthly performance
    six_months_ago = timezone.now() - timedelta(days=180)
    monthly_perf_raw = kpi_claims.filter(created_at__gte=six_months_ago).values('created_at__month').annotate(count=Count('id')).order_by('created_at__month')
    
    month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    monthly_perf = []
    current_month = timezone.now().month
    for i in range(5, -1, -1):
        m = (current_month - i - 1) % 12 + 1
        count = 0
        for entry in monthly_perf_raw:
            if entry['created_at__month'] == m:
                count = entry['count']
                break
        monthly_perf.append({
            'label': month_names[m-1],
            'count': count,
            'percentage': (count / float(total_claims if total_claims > 0 else 1) * 100)
        })

    # Enhancing claims with authoritative SSoT payload
    enhanced_claims = []
    for claim in claims_qs:
        # Pre-calculate the authoritative payload (Risk, Reserve, Settlement, SLA)
        claim.payload = claim.review_payload
        enhanced_claims.append(claim)

    # Staff Performance Data (Enhanced with Process Time)
    from django.contrib.auth import get_user_model
    User = get_user_model()
    
    from claims.models import AuditorReview
    
    staff_users = User.objects.filter(role='staff')
    # ðŸ›¡ï¸ ARCHIVE-DRIVEN ANALYTICS (Requirement: No status/workflow filters)
    reviews_all = AuditorReview.objects.select_related('auditor', 'claim').filter(reviewed_at__isnull=False)
    
    # Debug Logs for Global Consistency
    print(f"ðŸ“Š SYSTEM TELEMETRY - ALL REVIEWS: {reviews_all.count()}")
    
    staff_analytics = []
    unique_auditors = reviews_all.values_list('auditor', flat=True).distinct()
    auditor_users = User.objects.filter(id__in=unique_auditors)
    
    # If a staff member hasn't reviewed yet, add them manually for empty state
    all_staff = User.objects.filter(role='staff')
    
    def _auditor_display_name(user):
        return (
            getattr(user, "full_name_display", None)
            or user.get_full_name()
            or user.username
        )

    for aud_user in (list(auditor_users) + list(set(all_staff) - set(auditor_users))):
        user_reviews = reviews_all.filter(auditor=aud_user)
        total_reviewed = user_reviews.count()
        display_name = _auditor_display_name(aud_user)
        
        # User-Specific Debug Logs
        if aud_user == request.user:
            print(f"ðŸ“ˆ TELEMETRY - USER {aud_user.username} REVIEWS: {total_reviewed}")

        if total_reviewed == 0:
            staff_analytics.append({
                'user': aud_user,
                'display_name': display_name,
                'display_initial': display_name[:1].upper(),
                'total_audit': 0,
                'accuracy': 0.0,
                'sla_score': 0.0,
                'throughput': 0,
                'avg_rec': 0,
                'tier': 'C',
                'tier_color': 'warning',
                'empty_state': True
            })
            continue

        # Dynamic Aggregations from SSoT (AuditorReview)
        throughput = user_reviews.aggregate(total=Sum('claim__claimed_amount'))['total'] or 0
        avg_rec = user_reviews.aggregate(avg=Avg('recommended_amount'))['avg'] or 0
        
        accuracy_data = user_reviews.exclude(ai_original_amount=0).annotate(
            deviation=ExpressionWrapper(
                Abs(F('recommended_amount') - F('ai_original_amount')) / F('ai_original_amount'),
                output_field=FloatField()
            )
        ).aggregate(avg_acc=Avg(ExpressionWrapper(1.0 - F('deviation'), output_field=FloatField())))
        accuracy = (accuracy_data['avg_acc'] or 1.0) * 100.0

        # Efficiency logic (24h SLA)
        on_time = 0
        for r in user_reviews:
            if r.reviewed_at and r.assigned_at and (r.reviewed_at - r.assigned_at).total_seconds() <= 86400:
                on_time += 1
        sla_score = (on_time / total_reviewed * 100)
        
        # Tier logic
        if accuracy >= 95 and sla_score >= 90:
            tier, tier_color = 'A', 'success'
        elif accuracy >= 80:
            tier, tier_color = 'B', 'primary'
        else:
            tier, tier_color = 'C', 'warning'

        staff_analytics.append({
            'user': aud_user,
            'display_name': display_name,
            'display_initial': display_name[:1].upper(),
            'total_audit': total_reviewed,
            'accuracy': round(accuracy, 2),
            'sla_score': round(sla_score, 1),
            'throughput': round(float(throughput), 0),
            'avg_rec': round(float(avg_rec), 0),
            'tier': tier,
            'tier_color': tier_color,
            'empty_state': False
        })
    
    # Isolate logged in user performance for personal dashboard view
    my_performance = next((s for s in staff_analytics if s['user'] == request.user), None)

    # ðŸ›¡ï¸ AUDIT-DRIVEN HISTORY: Show claims where this staff member actually performed an action
    # We fetch these independently of the global page filters to ensure the history is always visible
    if request.user.is_superuser or request.user.role == 'admin':
        recent_audited_ids = ClaimAuditLog.objects.order_by('-created_at').values_list('claim_id', flat=True).distinct()[:10]
    else:
        recent_audited_ids = ClaimAuditLog.objects.filter(
            performed_by=request.user
        ).order_by('-created_at').values_list('claim_id', flat=True).distinct()[:15]
    
    # Fetch and enhance history claims separately
    # Only show claims that have actually been REVIEWED (not still pending/under_review)
    REVIEWED_STATUSES = ['staff_reviewed', 'approved', 'rejected', 'settled', 'closed', 'partially_approved', 'investigation']
    history_claims_raw = Claim.objects.filter(
        id__in=recent_audited_ids,
        status__in=REVIEWED_STATUSES
    ).select_related('assessment', 'policy', 'created_by')
    # Auditor History (Enhanced with SSoT payload)
    recent_history = []
    for c in history_claims_raw:
        c.payload = c.review_payload
        recent_history.append(c)

    # Separate claims for different dashboard sections
    # ðŸ¥ Active Workflow Queues (Unified Data Strategy)
    if request.user.is_superuser or request.user.role == 'admin':
        waiting_claims = [c for c in enhanced_claims if c.status in ["submitted", "under_review"]]
        investigation_queue = [c for c in enhanced_claims if c.status == "investigation"]
        processed_all = [c for c in enhanced_claims if c.status in ["approved", "rejected", "settled", "closed", "partially_approved", "staff_reviewed"]]
    else:
        # For Staff: Show ALL submitted/under_review claims so they can take them
        waiting_claims = [c for c in enhanced_claims if c.status in ["submitted", "under_review"] and not c.staff_recommendation]
        # For Investigation: Show if assigned/unassigned AND doesn't have a formal recommendation yet
        investigation_queue = [c for c in enhanced_claims if c.status == "investigation" and (c.assigned_to == request.user or c.assigned_to is None) and not c.staff_recommendation]
        
        # Claims that are currently being handled by Admin after staff review
        processed_all = [c for c in enhanced_claims if (c.status in ["approved", "rejected", "settled", "closed", "partially_approved", "staff_reviewed"] or (c.status == "investigation" and c.staff_recommendation)) and c.assigned_to == request.user]
    
    # Combined list for metrics calculation (if needed)
    active_workload = waiting_claims + investigation_queue

    workspace_metrics = {
        'pending_count': len(waiting_claims),
        'investigation_count': len(investigation_queue),
        'completed_count': len(processed_all),
        'overdue_count': sum(1 for c in active_workload if c.payload.get('sla_days', 0) > 7),
        'attention_count': sum(
            1
            for c in active_workload
            if (
                c.payload.get('sla_days', 0) > 3
                or c.payload.get('risk_score', 0) > 50
                or c.status == 'investigation'
            )
        ),
    }

    # 💳 Unified Transaction Ledger Data (Cross-Module Sync)
    premium_payments = Payment.objects.filter(
        payment_status='completed',
        direction='CREDIT',
        payment_type__in=['PREMIUM_PAYMENT', 'PREMIUM'],
    ).select_related('user_policy__user', 'user_policy__policy').order_by('-created_at')[:15]
    settled_claims = ClaimSettlement.objects.select_related('claim').order_by('-settlement_date')[:15]

    ledger_credits = []
    for payment in premium_payments:
        user_policy = payment.user_policy
        payer = user_policy.user if user_policy else None
        policy = user_policy.policy if user_policy else None
        payer_name = (
            getattr(payer, "full_name_display", None)
            or payer.get_full_name()
            or payer.username
        ) if payer else "System"
        ledger_credits.append({
            'ref_id': payment.transaction_id,
            'policy_number': policy.policy_number if policy else "Internal",
            'payer_name': payer_name,
            'amount': payment.amount,
            'date': payment.created_at,
        })

    ledger_debits = []
    for settlement in settled_claims:
        ledger_debits.append({
            'ref_id': settlement.transaction_reference,
            'claim_number': settlement.claim.claim_number if settlement.claim else "Unknown",
            'payee_name': settlement.payee_name or "Payee",
            'amount': settlement.settled_amount,
            'date': settlement.settlement_date,
        })

    # Calculate Integrity Metrics dynamically using Single Source of Truth helper
    integrity_metrics = _build_admin_integrity_metrics()

    context = {
        'claims': waiting_claims,  # Primary actionable list
        'waiting_claims': waiting_claims,
        'investigation_queue': investigation_queue,
        'active_workload': active_workload,
        'processed_claims': processed_all,
        'recent_claims': recent_history, # Use audit-driven history
        'ledger_credits': ledger_credits,
        'ledger_debits': ledger_debits,
        'workspace_metrics': workspace_metrics,
        'kpi': kpi,
        'efficiency': round(efficiency, 1),
        'monthly_perf': monthly_perf,
        'staff_analytics': sorted(staff_analytics, key=lambda x: x['total_audit'], reverse=True),
        'claim_status_summary': claim_status_summary,
        'all_policies': all_policies,
        'status_choices': Claim.STATUS,
        'type_choices': Claim.CLAIM_TYPE,
        'my_performance': my_performance,
        'integrity_metrics': integrity_metrics,
    }

    return render(request, "accounts/dashboard_staff.html", context)



@role_required(allowed_roles=['user'])
def policyholder_dashboard(request):
    """
    Enforces policyholder/user role access while allowing Admins to access for support.
    """


    context: dict[str, Any] = {
        'settled_claims': [],
        'recent_claims': [],
        'user_policies': [],
        'policies': [],
        'expiring_policies': [],
        'pending_payments': [],
        'payment_history': [],
        'policy_applications': [],
        'claim_status_summary': [],
    }

    try:
        purchased_policy_number = request.session.pop("purchased_policy_number", None)
        if purchased_policy_number:
            messages.success(
                request,
                f"Policy {purchased_policy_number} purchased successfully."
            )

        # 1. Fetching all base user policies
        user_policies_qs = UserPolicy.objects.filter(
            user=request.user,
        ).exclude(status='cancelled').select_related("policy", "policy__plan")

        # ðŸ”¥ DYNAMIC SYNC: Re-evaluate policy health (Overdue/Grace/Lapsed) before calculations
        # This ensures the KPI cards and Tables show accurate REAL-TIME status.
        for up in user_policies_qs:
            up.sync_status_with_premiums()
        
        # Fresh queryset with updated statuses from DB
        user_policies = user_policies_qs.all()

        claims = Claim.objects.filter(get_visible_claims_q(request.user)).distinct()

        # KPI calculations (Refined for robustness)
        # 1. Active policies for the "Active" badge & counter
        active_user_policies = user_policies.filter(status__in=['active', 'grace'])
        
        # 2. Open claims (including those in progress)
        open_claims = claims.filter(status__in=['submitted', 'under_review', 'investigation', 'partially_approved'])

        # 3. Total Sum Insured (Available across all non-cancelled policies)
        total_sum = user_policies.aggregate(total=Sum('sum_insured_remaining'))['total'] or 0
        
        # 4. Total Settled Amount (Ensuring null safety across financial fields)
        total_settled = claims.filter(
            status__in=['approved', 'settled']
        ).aggregate(
            total=Sum(Coalesce('settled_amount', 'approved_amount', Value(0, output_field=models.DecimalField())))
        )['total'] or 0

        settled_claims_count = claims.filter(status='settled').count()
        claim_progress_pct = round((open_claims.count() / claims.count()) * 100, 1) if claims.count() else 0
        coverage_utilization_pct = round((float(total_settled) / float(total_sum)) * 100, 1) if total_sum else 0
        settled_ratio_pct = round((settled_claims_count / claims.count()) * 100, 1) if claims.count() else 0

        context['kpi'] = {
            'total_policies':   user_policies.count(),
            'active_policies':  active_user_policies.count(),
            'active_policy_pct': round((active_user_policies.count() / user_policies.count()) * 100, 1) if user_policies.count() else 0,
            'total_claims':     claims.count(),
            'open_claims':      open_claims.count(),
            'total_sum_insured': total_sum,
            'total_settled':    total_settled,
            'settled_claims':   settled_claims_count,
            'claim_progress_pct': claim_progress_pct,
            'coverage_utilization_pct': coverage_utilization_pct,
            'coverage_remaining_pct': round(max(0, 100 - coverage_utilization_pct), 1),
            'settled_ratio_pct': settled_ratio_pct,
        }

        # Expiring policies (based on UserPolicy.end_date)
        today = date.today()
        expiring_policies = []
        for up in user_policies:
            if up.end_date and today <= up.end_date <= today + timedelta(days=30):
                up.days_left = (up.end_date - today).days
                expiring_policies.append(up)

        context['expiring_policies'] = expiring_policies
        context['user_policies']     = user_policies.order_by('-assigned_at')[:10]
        # Keep 'policies' alias so old template references still work
        context['policies']          = user_policies.order_by('-assigned_at')[:10]

        # Claim summary breakdown
        total_claims_count = claims.count()
        status_counts = claims.values('status').annotate(count=Count('id'))
        
        claim_status_summary = []
        for s in status_counts:
            status = s['status']
            count = s['count']
            pct = (count / total_claims_count * 100) if total_claims_count > 0 else 0
            
            bar_class = 'bg-secondary'
            if status in ['approved', 'settled']: bar_class = 'bg-success'
            elif status in ['under_review', 'investigation']: bar_class = 'bg-warning'
            elif status == 'submitted': bar_class = 'bg-primary'
            elif status == 'rejected': bar_class = 'bg-danger'
            
            claim_status_summary.append({
                'label': status.replace('_', ' ').title(),
                'count': count,
                'percentage': pct,
                'bar_class': bar_class
            })
            
        context['claim_status_summary'] = claim_status_summary
        context['recent_claims'] = claims.order_by('-created_at')[:5]
        
        # 💰 ENHANCED SETTLEMENT VISIBILITY: 
        # Include both 'settled' and 'approved' (Awaiting Payout) claims to manage policyholder expectations.
        context['settled_claims'] = claims.filter(
            status__in=['settled', 'approved']
        ).select_related('settlement').order_by('-updated_at')

        # â”€â”€ Policy Applications â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        from policy.models import PolicyApplication
        policy_applications_qs = PolicyApplication.objects.filter(
            user=request.user
        ).select_related("policy").order_by("-created_at")
        context['pending_app_count'] = policy_applications_qs.filter(status='pending').count()
        context['policy_applications'] = policy_applications_qs[:5]

        try:
            from premiums.views import normalize_overdue
            
            # Find all schedules specifically linked to this individual user-policy or legacy purchase
            base_payments = PremiumPayment.objects.filter(
                Q(schedule__policy__purchases__user=request.user) |
                Q(schedule__user_policy__user=request.user)
            ).distinct().select_related("schedule", "schedule__policy")

            # ðŸ”¥ DYNAMIC STATUS UPDATE: Ensure overdue/lapsed states are captured before rendering
            normalize_overdue(base_payments)

            # Show overdue, upcoming, and lapsed payments in the "Pending" section
            pending_payments = base_payments.filter(
                status__in=["overdue", "upcoming", "lapsed"]
            ).order_by("status", "due_date")

            payment_history = base_payments.filter(
                status="paid"
            ).order_by("-paid_date", "-due_date")

            total_paid = payment_history.aggregate(total=Sum("amount"))["total"] or 0
            total_pending = pending_payments.aggregate(total=Sum("amount"))["total"] or 0
        except Exception:
            pending_payments = []
            payment_history = []
            total_paid = 0
            total_pending = 0

        context["pending_payments"] = pending_payments
        context["payment_history"] = payment_history
        context["premium_summary"] = {
            "total_paid": total_paid,
            "total_pending": total_pending,
        }
        
    except Exception as e:
        context['kpi'] = {
            'total_policies': 0, 'active_policies': 0,
            'active_policy_pct': 0,
            'total_claims': 0, 'open_claims': 0,
            'total_sum_insured': 0, 'total_settled': 0,
            'settled_claims': 0,
            'claim_progress_pct': 0,
            'coverage_utilization_pct': 0,
            'coverage_remaining_pct': 100,
            'settled_ratio_pct': 0,
        }
        context['policies'] = []
        context['expiring_policies'] = []
        context['claim_status_summary'] = []
        context['recent_claims'] = []
        context['settled_claims'] = []
        context['premium_payments'] = []

    return render(request, "accounts/dashboard_policyholder.html", context)


@login_required
def profile_view(request, profile_id=None):
    target_user = request.user
    target_profile = getattr(request.user, "profile", None)

    if profile_id is not None:
        target_profile = get_object_or_404(UserProfile.objects.select_related("user"), public_id=profile_id)
        if not (
            request.user.is_superuser
            or request.user.role in ["admin", "staff"]
            or target_profile.user_id == request.user.id
        ):
            return render(request, "accounts/unauthorized.html")
        target_user = target_profile.user
        return render(request, "accounts/profile_detail.html", {
            "target_user": target_user,
            "target_profile": target_profile,
        })

    if target_user.role == "admin":
        return render(request, "accounts/profile_admin.html")
    elif target_user.role == "staff":
        return render(request, "accounts/profile_staff.html")
    elif target_user.role == "user":
        return render(request, "accounts/profile_policyholder.html")
    else:
        return render(request, "accounts/profile.html")




@login_required
def edit_profile(request):
    if request.method == "POST":
        form = ProfileEditForm(request.POST, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, "Profile updated successfully.")
            return redirect("accounts:profile")
        else:
            messages.warning(request, "Please correct the errors below.")
    else:
        form = ProfileEditForm(instance=request.user)
    
    return render(request, "accounts/profile_edit.html", {"form": form})


@login_required
def reupload_id(request):
    """
    Allows user to re-upload Aadhaar.
    Resets verification status to False.
    """
    if request.method == "POST":
        form = ReuploadIDForm(request.POST, request.FILES, instance=request.user)
        if form.is_valid():
            user = form.save(commit=False)
            user.is_verified = False
            user.verified_at = None
            user.save()
            
            # ðŸ”¥ Sync legacy profile if exists
            if hasattr(request.user, 'profile'):
                profile = request.user.profile
                profile.id_proof = user.id_proof
                profile.is_verified = False
                profile.verification_status = 'PENDING'
                profile.save()

            messages.success(request, "ID Proof re-uploaded successfully. It will be reviewed by staff.")
            return redirect("accounts:policyholder_dashboard")
    else:
        form = ReuploadIDForm(instance=request.user)
    
    return render(request, "accounts/reupload_id.html", {"form": form})


# LOGIN

def login_view(request):

    if request.method == "POST":

        username = request.POST.get("username")
        password = request.POST.get("password")

        user = authenticate(request,username=username,password=password)

        if user is not None:
            # ðŸ›¡ï¸ IDENTITY GATING: Enforce Aadhaar verification status
            if not user.is_verified and not user.is_staff and not user.is_superuser:
                 # Check legacy profile if it exists for backward compatibility
                 if hasattr(user, 'profile') and user.profile.verification_status == 'MISMATCH':
                    messages.error(request, "Your account verification failed due to Aadhaar mismatch. Please contact support or register again.")
                    return render(request, "accounts/login.html")
                
                 # If User model is not verified and it's a regular user
                 # messages.warning(request, "Account verification is currently pending. Please check back later.")
                 # (Optional: Block login if strict KYC was required, but for now we follow old logic)
                 pass

            login(request, user)
            
            # ðŸ›¡ï¸ COMMIT SESSION: Ensure sessionid cookie is pinned for AJAX reliability
            if not request.session.session_key:
                request.session.create()
            
            # Optional: Ensure session persists until browser closure
            request.session.set_expiry(0) 
            
            logger.info(f"User Logged In: {user.username} | Session: {request.session.session_key}")
            return redirect(user.dashboard_url)


        else:

            messages.error(request,"Invalid username or password")

    return render(request,"accounts/login.html")


# LOGOUT

def logout_view(request):

    logout(request)

    return redirect("accounts:login")


from django.http import JsonResponse
def check_auth_api(request):
    """Diagnostic endpoint to check session/auth status."""
    return JsonResponse({
        "is_authenticated": request.user.is_authenticated,
        "user": str(request.user),
        "role": getattr(request.user, 'role', 'N/A'),
        "session_exists": bool(request.session.session_key)
    })


def unauthorized_view(request):

    return render(request,"accounts/unauthorized.html")


@admin_only
def admin_create_staff(request):
    """
    SECURITY: Only administrators can create staff users.
    Role assignment is hardcoded to 'staff' in the backend to prevent escalation.
    """
    if request.method == "POST":
        form = StaffCreationForm(request.POST) # Uses secure staff form
        if form.is_valid():
            user = form.save(commit=False)
            
            # ðŸ›¡ï¸ Hardened Staff Assignment (Forces role, prevents shadow escalation)
            user.role = 'staff'
            user.is_staff = True
            user.is_superuser = False
            
            user.set_password(form.cleaned_data["password"])
            user.save()
            
            # ðŸ™ï¸ Create Staff Profile (Admin Provisioned)
            # Aadhaar is forced to a unique 12-digit dummy to satisfy DB constraint
            UserProfile.objects.create(
                user=user,
                full_name=form.cleaned_data.get("full_name"),
                aadhaar_number=str(100000000000 + user.id), 
                is_verified=True # Pre-verified by Admin
            )
            
            messages.success(request, f"Processing Staff account for '{user.username}' provisioning complete.")
            return redirect("accounts:admin_dashboard")
    else:
        form = StaffCreationForm()
    
    return render(request, "accounts/admin_create_staff.html", {"form": form})

from django.contrib.auth import views as auth_views
from django.urls import reverse_lazy
from django.utils.decorators import method_decorator
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.cache import never_cache
from .forms import RegisterForm, ProfileEditForm, CustomPasswordResetForm, CustomSetPasswordForm, StaffCreationForm
from .models import User, PasswordResetAttempt

# FORGOT PASSWORD FLOW

def get_client_ip(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip

class CustomPasswordResetView(auth_views.PasswordResetView):
    template_name = 'accounts/password_reset_form.html'
    email_template_name = 'accounts/password_reset_email.html'
    subject_template_name = 'accounts/password_reset_subject.txt'
    success_url = reverse_lazy('accounts:password_reset_done')
    form_class = CustomPasswordResetForm

    def form_valid(self, form):
        # Audit Logging
        email = form.cleaned_data.get('email')
        user = User.objects.filter(email=email).first()
        
        attempt = PasswordResetAttempt.objects.create(
            user=user,
            email=email,
            ip_address=get_client_ip(self.request),
            user_agent=self.request.META.get('HTTP_USER_AGENT', ''),
            status='sent' if user else 'invalid_email'
        )
        
        # Django's form_valid handles the actual email sending
        response = super().form_valid(form)
        return response

class CustomPasswordResetDoneView(auth_views.PasswordResetDoneView):
    template_name = 'accounts/password_reset_done.html'

class CustomPasswordResetConfirmView(auth_views.PasswordResetConfirmView):
    template_name = 'accounts/password_reset_confirm.html'
    success_url = reverse_lazy('accounts:password_reset_complete')
    form_class = CustomSetPasswordForm

    def form_valid(self, form):
        # Log successful reset
        user = form.user
        # Find the latest reset attempt for this user to mark it as used
        last_attempt = PasswordResetAttempt.objects.filter(user=user).order_by('-created_at').first()
        if last_attempt:
            last_attempt.token_used = True
            last_attempt.save()
            
        messages.success(self.request, "Your password has been successfully reset!")
        return super().form_valid(form)

class CustomPasswordResetCompleteView(auth_views.PasswordResetCompleteView):
    template_name = 'accounts/password_reset_complete.html'


from django.db.models import Prefetch

@login_required
def staff_search_suggestions(request):
    """
    API endpoint for staff dashboard smart search.
    Returns JSON suggestions for claims, policies, and user names.
    """
    if not (request.user.role == "staff" or request.user.is_superuser):
        return JsonResponse({"error": "Unauthorized"}, status=403)

    query = request.GET.get('q', '').strip()
    if not query or len(query) < 2:
        return JsonResponse([], safe=False)

    search_type = request.GET.get('search_type', 'all').strip()
    suggestions = []

    # 1. Search Claims
    if search_type in ('all', 'claim'):
        claims = Claim.objects.filter(claim_number__icontains=query).select_related('policy', 'created_by')[:5]
        for c in claims:
            suggestions.append({
                "text": f"Claim: {c.claim_number}",
                "type": "claim",
                "value": c.claim_number,
                "status": c.status,
                "claim_type": c.claim_type
            })

    # 2. Search Policies
    if search_type in ('all', 'policy'):
        policies = Policy.objects.filter(policy_number__icontains=query)[:5]
        for p in policies:
            suggestions.append({
                "text": f"Policy: {p.policy_number}",
                "type": "policy",
                "value": p.policy_number,
                "status": "",
                "claim_type": ""
            })

    # 3. Search Members
    if search_type in ('all', 'name'):
        users = User.objects.filter(
            Q(username__icontains=query) |
            Q(first_name__icontains=query) |
            Q(last_name__icontains=query)
        )[:5]
        for u in users:
            suggestions.append({
                "text": f"Member: {u.get_full_name() or u.username}",
                "type": "name",
                "value": u.username,
                "status": "",
                "claim_type": ""
            })

    return JsonResponse(suggestions[:10], safe=False)
@admin_only
def kyc_dashboard(request):
    """
    Enterprise KYC Command Center View.
    Aggregates identity verification analytics, fraud signals, and review operations.
    """
    from django.utils import timezone
    from datetime import timedelta
    from django.db.models import Count
    
    today = timezone.now().date()
    
    # ðŸ›¡ï¸ Date Range Analytics Logic
    range_type = request.GET.get('range', '7')
    full_verifications = AadhaarKYCVerification.objects.all()
    
    if range_type == 'today':
        verifications = full_verifications.filter(created_at__date=today)
        range_label = "Today"
    elif range_type == '30':
        verifications = full_verifications.filter(created_at__date__gte=today - timedelta(days=30))
        range_label = "Last 30 Days"
    elif range_type == 'all':
        verifications = full_verifications
        range_label = "All Time"
    else:
        verifications = full_verifications.filter(created_at__date__gte=today - timedelta(days=7))
        range_label = "Last 7 Days"

    # KPI Cards always show "Today" for the specific 'Today' slots, but range for others
    # Actually, standardizing: KPIs reflect the RANGE, except for 'Verified Today' specifically.
    
    # 1. Executive KPI Cards with Deduplication (Fix Step 6)
    # Using .values().distinct() ensures we count unique persons, not duplicate event logs
    # Card always shows 'Today' for this specific metric
    verified_today_count = full_verifications.filter(
        status__in=['verified', 'approved_override'], 
        created_at__date=today
    ).values('submitted_aadhaar_number').distinct().count()
    
    pending_reviews = verifications.filter(
        status__in=['manual_review', 'escalated']
    ).values('submitted_aadhaar_number').distinct().count()
    
    mismatch_cases = verifications.filter(
        status__in=['rejected', 'rejected_override']
    ).exclude(details__manual_action__in=['reject', 'approve']).values('submitted_aadhaar_number').distinct().count()
    
    # Avg Confidence (Legacy Fallback Support - Requirement 4 & 5)
    all_details = verifications.values_list('details', flat=True)
    valid_scores = []
    for d in all_details:
        if not isinstance(d, dict): continue
        if 'ocr_confidence' in d:
             valid_scores.append(float(d['ocr_confidence']))
        elif 'confidence' in d:
             # Legacy data was 0-1 scale, normalize to 100
             valid_scores.append(float(d['confidence']) * 100)
             
    avg_confidence = (sum(valid_scores) / len(valid_scores)) if valid_scores else 0.0
    
    # 2. Suspicious Repeat IDs (Enterprise Rolling Window Analytics)
    # Deduplicate attempts within a rolling 5-minute window per Aadhaar
    from django.db.models import Count
    
    # Get all potential candidates (IDs with more than 1 record total)
    candidates = verifications.values('submitted_aadhaar_number').annotate(
        raw_count=Count('id')
    ).filter(raw_count__gt=1)
    
    repeat_id_flags = []
    for entry in candidates:
        num = entry['submitted_aadhaar_number']
        if not num or len(num) < 4: continue
        
        # Fetch timeline for this identity
        history = verifications.filter(submitted_aadhaar_number=num).order_by('created_at')
        if not history.exists(): continue
        
        # Rolling 5-Minute Window Deduplication
        unique_attempts_logs = []
        current_session_start = history[0].created_at
        unique_attempts_logs.append(history[0])
        
        for i in range(1, len(history)):
            # If the gap between current log and start of session is > 5 mins, it's a new attempt
            delta = history[i].created_at - current_session_start
            if delta.total_seconds() > 300: # 5 Minutes
                unique_attempts_logs.append(history[i])
                current_session_start = history[i].created_at
        
        attempt_count = len(unique_attempts_logs)
        if attempt_count <= 1:
            continue # Effectively deduplicated to a single event
            
        # Analysis for Risk Scoring (Requirement: Attempt Velocity)
        last_attempt = history.last()
        first_attempt = history.first()
        is_registered = history.filter(status='verified').exists()
        fail_count = history.filter(status='rejected').count()
        
        # Calculate time span of unique sessions
        time_span_seconds = (last_attempt.created_at - first_attempt.created_at).total_seconds()
        
        # Velocity-Based Risk Scoring
        if attempt_count >= 5 and time_span_seconds <= 86400: # 5+ in 24h
            risk, risk_color = "CRITICAL", "danger"
        elif attempt_count >= 3 and time_span_seconds <= 3600: # 3+ in 1h
            risk, risk_color = "HIGH", "danger"
        elif attempt_count >= 3 or is_registered:
            risk, risk_color = "MEDIUM", "warning"
        else:
            risk, risk_color = "LOW", "secondary" # Spread out attempts
            
        repeat_id_flags.append({
            "raw_num": num,
            "masked_aadhaar": f"XXXX XXXX {num[-4:]}",
            "unique_attempts": attempt_count,
            "last_attempt": last_attempt.created_at,
            "is_registered": is_registered,
            "risk": risk,
            "risk_color": risk_color
        })

    # Sort by urgency (attempt count descending)
    repeat_id_flags.sort(key=lambda x: (x['risk'] == 'CRITICAL', x['risk'] == 'HIGH', x['unique_attempts']), reverse=True)

    # 3. Manual Review Queue (Deduplicated)
    raw_reviews = verifications.filter(status='manual_review').order_by('-created_at')
    review_queue = []
    seen_review = set()
    for r in raw_reviews:
        if r.submitted_aadhaar_number not in seen_review:
            review_queue.append(r)
            seen_review.add(r.submitted_aadhaar_number)
        if len(review_queue) >= 15: break

    # 4. Status Distribution (Deduplicated)
    status_counts = {
        'verified': full_verifications.filter(status__in=['verified', 'approved_override']).values('submitted_aadhaar_number').distinct().count(),
        'manual': full_verifications.filter(status='manual_review').values('submitted_aadhaar_number').distinct().count(),
        'rejected': full_verifications.filter(status__in=['rejected', 'rejected_override']).values('submitted_aadhaar_number').distinct().count(),
        'escalated': full_verifications.filter(status='escalated').values('submitted_aadhaar_number').distinct().count(),
    }

    # 5. OCR Score Histogram
    ocr_scores = []
    for d in all_details:
        if isinstance(d, dict):
            score = d.get('ocr_confidence') or d.get('confidence', 0)
            try:
                score = float(score)
                if 0 < score <= 1.0: score *= 100
                ocr_scores.append(score)
            except (ValueError, TypeError):
                continue
    
    score_buckets = [0, 0, 0, 0, 0]
    for s in ocr_scores:
        if s <= 20: score_buckets[0] += 1
        elif s <= 40: score_buckets[1] += 1
        elif s <= 60: score_buckets[2] += 1
        elif s <= 80: score_buckets[3] += 1
        else: score_buckets[4] += 1

    # 5. Trend Chart (Last 7 Days)
    days_labels = []
    success_trend = []
    failed_trend = []
    review_trend = []
    
    for i in range(6, -1, -1):
        d = today - timedelta(days=i)
        days_labels.append(d.strftime("%b %d"))
        day_vs = verifications.filter(created_at__date=d)
        success_trend.append(day_vs.filter(status__in=['verified', 'approved_override']).count())
        failed_trend.append(day_vs.filter(status__in=['rejected', 'rejected_override']).count())
        review_trend.append(day_vs.filter(status__in=['manual_review', 'escalated']).count())

    # 6. Live Feed (Deduplicated activity)
    live_feed = verifications.exclude(status='rejected').order_by('-created_at')
    feed_items = []
    seen_feed = set()
    last_feed_time = {} # {aadhaar: latest_seen_time}
    for v in live_feed:
        num = v.submitted_aadhaar_number or "UNKNOWN"
        curr_time = v.created_at
        
        # ðŸ›¡ï¸ Rolling 5-Minute Session Deduplication for Feed
        if num in last_feed_time:
            delta = last_feed_time[num] - curr_time
            if delta.total_seconds() <= 300: # 5 Minutes
                continue 
                
        last_feed_time[num] = curr_time
        
        name = v.submitted_full_name or "Applicant"
        if v.status in ['verified', 'approved_override']:
            msg, color = f"{name} verified successfully", "success"
        elif v.status in ['manual_review', 'pending', 'escalated']:
            msg, color = f"Manual review created for {name}", "warning"
        elif v.status == 'rejected_override' or (isinstance(v.details, dict) and v.details.get('manual_action') == 'reject'):
            msg, color = f"Manually REJECTED: {name}", "danger"
        else:
            msg, color = f"Mismatch blocked for {name}", "danger"
            
        feed_items.append({
            "msg": msg, 
            "time": v.created_at, 
            "color": color, 
            "record_id": v.public_id
        })
        if len(feed_items) >= 12: break

    context = {
        "verified_today": verified_today_count,
        "range_label": range_label,
        "current_range": range_type,
        "pending_reviews": pending_reviews,
        "avg_confidence": round(avg_confidence, 1),
        "mismatch_cases": mismatch_cases,
        "total_suspicious": len(repeat_id_flags),
        "repeat_id_flags": repeat_id_flags,
        "review_queue": review_queue,
        "status_distribution": [status_counts['verified'], status_counts['manual'], status_counts['rejected'], status_counts['escalated']],
        "score_buckets": score_buckets,
        "days_labels": days_labels,
        "success_trend": success_trend,
        "failed_trend": failed_trend,
        "review_trend": review_trend,
        "feed_items": feed_items,
    }
    
    return render(request, "accounts/kyc_dashboard.html", context)
@admin_only
def kyc_detail(request, verification_id):
    """
    Enterprise Forensic Detail View.
    Allows for manual investigation and override with high-fidelity telemetry.
    """
    verification = get_object_or_404(AadhaarKYCVerification, public_id=verification_id)
    details = verification.details if isinstance(verification.details, dict) else {}
    
    # Forensic Action Handler (Approve/Reject Override)
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "approve":
            verification.status = "approved_override" # or "verified"
            verification.verified_at = timezone.now()
            details["manual_action"] = "approve"
            verification.details = details
            
            # Synchronize User and Profile
            if verification.user:
                verification.user.is_verified = True
                verification.user.verified_at = timezone.now()
                verification.user.save()
            
            if verification.profile:
                verification.profile.is_verified = True
                verification.profile.verification_status = 'VERIFIED'
                verification.profile.save()

            messages.success(request, f"Forensic Override: {verification.submitted_full_name} manually approved.")
        elif action == "reject":
            verification.status = "rejected_override"
            details["manual_action"] = "reject"
            verification.details = details
            if verification.user:
                verification.user.is_verified = False
                verification.user.save()
            messages.warning(request, f"Forensic Override: {verification.submitted_full_name} manually rejected.")
        elif action == "revoke":
            verification.status = "rejected_override"
            details["manual_action"] = "revoke"
            verification.details = details
            if verification.user:
                verification.user.is_verified = False
                verification.user.save()
            if verification.profile:
                verification.profile.is_verified = False
                verification.profile.verification_status = 'MISMATCH'
                verification.profile.save()
            messages.error(request, f"Governance: Approval revoked for {verification.submitted_full_name}.")
        elif action == "escalate":
            verification.status = "escalated"
            details["manual_action"] = "escalate"
            verification.details = details
            messages.info(request, f"Governance: {verification.submitted_full_name} escalated to Manual Review.")
        elif action == "reopen":
            verification.status = "manual_review"
            details["manual_action"] = "reopen"
            verification.details = details
            messages.info(request, f"Governance: Case reopened for {verification.submitted_full_name}.")
        
        verification.save()
        return redirect("accounts:kyc_dashboard")

    # Robust Forensic Extraction (Supports Legacy & Standardized Keys)
    # OCR Confidence (Scale 0-100)
    ocr_conf = details.get("ocr_confidence")
    if ocr_conf is None:
        ocr_conf = details.get("confidence", 0)
        if float(ocr_conf) <= 1.0 and float(ocr_conf) > 0:
            ocr_conf = float(ocr_conf) * 100
            
    # Name Similarity (Scale 0-100)
    name_sim = details.get("name_similarity")
    if name_sim is None:
        name_sim = details.get("name_score", 0)
        if float(name_sim) <= 1.0 and float(name_sim) > 0:
            name_sim = float(name_sim) * 100

    # Match Flags
    # number_match logic uses exact flag if exists, otherwise tries to infer from reason_code
    number_match = details.get("aadhaar_match")
    if number_match is None:
        number_match = details.get("reason_code") != "AADHAAR_NUMBER_MISMATCH"

    print(f"DEBUG: Serving KYC Detail for {verification_id} from accounts/views.py")
    
    context = {
        "verification": verification,
        "details": details,
        "live_marker": "LIVE_ROUTING_VERIFIED_V1.1", # Forensic marker for UI verification
        "name_similarity_percent": round(float(name_sim), 1),
        "confidence_percent": round(float(ocr_conf), 1),
        "name_match": float(name_sim) >= 90, # Decision label threshold
        "number_match": number_match,
        "reason_code": details.get("reason_code", "UNKNOWN"),
        "reason_text": details.get("reason_text", "No detailed explanation available."),
    }
    return render(request, "accounts/kyc_detail.html", context)


@admin_only
def kyc_logs_api(request):
    """
    High-Fidelity AI Audit Feed.
    Returns detailed forensic metrics for the administrative dashboard.
    """
    filter_type = request.GET.get('filter', 'all')
    verifications = AadhaarKYCVerification.objects.all().distinct()
    
    today = timezone.now().date()
    
    if filter_type == 'verified_today':
        verifications = verifications.filter(status='verified', created_at__date=today)
    elif filter_type == 'manual_reviews':
        # Backward compatibility for 'pending' legacy rows
        verifications = verifications.filter(status__in=['manual_review', 'pending'])
    elif filter_type == 'mismatches':
        verifications = verifications.filter(status__in=['rejected', 'failed']).exclude(details__manual_action__in=['reject', 'approve'])
    elif filter_type == 'low_confidence':
        verifications = verifications.filter(details__ocr_confidence__lt=60).exclude(status__in=['rejected', 'failed'])
    else:
        verifications = verifications.exclude(status__in=['rejected', 'failed'])

    verifications = verifications.order_by('-created_at')[:100]
    
    data = []
    seen_ids = set() 
    
    for v in verifications:
        num = v.submitted_aadhaar_number or "UNKNOWN"
        # Rolling 5-min dedupe
        dedupe_key = f"{num}_{v.created_at.strftime('%Y%m%d%H%M')[:11]}" # 1 minute window for API
        if dedupe_key in seen_ids: continue
        seen_ids.add(dedupe_key)
        
        details = v.details if isinstance(v.details, dict) else {}
        
        # Standardize Extraction for API results
        api_ocr = details.get("ocr_confidence")
        if api_ocr is None:
            api_ocr = details.get("confidence", 0)
            if api_ocr <= 1.0 and api_ocr > 0:
                api_ocr = float(api_ocr) * 100
        
        api_name = details.get("name_similarity", 0)
        
        data.append({
            "id": str(v.public_id),
            "name": v.submitted_full_name or "Applicant",
            "number": num,
            "status": v.status,
            "name_similarity": round(float(api_name), 1),
            "ocr_confidence": round(float(api_ocr), 1),
            "reason_code": details.get("reason_code", "N/A"),
            "display_time": v.created_at.strftime("%b %d, %H:%M")
        })
        
    return JsonResponse({"logs": data, "filter": filter_type, "count": len(data)})

@admin_only
def kyc_history_api(request):
    """Fetch history for a specific Aadhaar number."""
    num = request.GET.get('num')
    if not num: 
        return JsonResponse({"error": "Missing number"}, status=400)
        
    verifications = AadhaarKYCVerification.objects.filter(submitted_aadhaar_number=num).exclude(status='failed').order_by('-created_at')
    data = []
    seen_keys = set()
    for v in verifications:
        # UI Deduplication: Hide jitter/duplicate logs within the same 60s window
        time_key = v.created_at.strftime("%Y-%m-%d %H:%M")
        key = (v.status, time_key) 
        
        if key in seen_keys:
            continue
        seen_keys.add(key)
        
        data.append({
            "id": str(v.public_id),
            "name": v.submitted_full_name or "Unknown",
            "status": v.status,
            "confidence": v.details.get("confidence", 0) if isinstance(v.details, dict) else 0,
            "time": v.created_at.strftime("%Y-%m-%d %H:%M:%S")
        })
    return JsonResponse({"history": data})

from django.http import JsonResponse

@role_required(allowed_roles=['user'])
def pdf_user_report_data_api(request):
    """Fetches comprehensive live data for the User PDF Report."""
    from claims.models import Claim
    from policy.models import UserPolicy, Payment
    from django.db.models import Sum

    # Fetching all base user policies
    user_policies = UserPolicy.objects.filter(
        user=request.user,
    ).exclude(status='cancelled').select_related("policy")

    # Metrics
    active_policies = user_policies.filter(status__in=['active', 'grace']).count()
    claims = Claim.objects.filter(created_by=request.user)
    open_claims = claims.filter(status__in=['submitted', 'under_review', 'investigation', 'partially_approved']).count()
    total_claims = claims.count()

    total_sum = user_policies.aggregate(total=Sum('sum_insured_remaining'))['total'] or 0
    total_settled = claims.filter(status__in=['approved', 'settled']).aggregate(total=Sum('settled_amount'))['total'] or 0

    # Policy details
    policy_details = []
    for up in user_policies:
        policy_details.append({
            "policy_number": up.policy.policy_number if up.policy else "Unknown",
            "type": up.policy.policy_type.upper() if (up.policy and up.policy.policy_type) else "Unknown",
            "coverage": float(up.sum_insured_remaining or 0),
            "premium": float(up.premium_amount or 0) if hasattr(up, 'premium_amount') else float(up.final_premium or 0),
            "status": up.get_status_display()
        })

    # Claims History
    claims_history = []
    for c in claims.order_by('-created_at')[:10]:
        claims_history.append({
            "claim_id": c.claim_number,
            "date": c.created_at.strftime("%Y-%m-%d"),
            "type": c.claim_type.upper() if c.claim_type else "OTHER",
            "requested": float(c.claimed_amount or 0),
            "approved": float(c.authoritative_payout or 0),
            "status": c.status.upper()
        })

    # Billing History
    payments = Payment.objects.filter(user_policy__user=request.user).order_by('-created_at')[:10]
    billing_history = []
    for p in payments:
        billing_history.append({
            "txn_id": p.transaction_id,
            "date": p.created_at.strftime("%Y-%m-%d"),
            "amount": float(p.amount or 0),
            "status": p.payment_status.upper()
        })

    return JsonResponse({
        "executive_summary": {
            "active_policies": active_policies,
            "total_claims": total_claims,
            "open_claims": open_claims,
            "total_coverage": float(total_sum),
            "total_payouts": float(total_settled),
        },
        "policy_details": policy_details,
        "claims_history": claims_history,
        "billing_history": billing_history,
        "timestamp": timezone.now().strftime("%Y-%m-%d %H:%M:%S"),
        "user_name": request.user.get_full_name() or request.user.username
    })
