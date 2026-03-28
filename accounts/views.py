from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from .forms import RegisterForm, ProfileEditForm, CustomPasswordResetForm, CustomSetPasswordForm
from .models import User, UserProfile
from .decorators import admin_only, staff_or_admin, role_required, staff_only
from policy.models import Policy, PolicyHolder, PolicyApplication, UserPolicy, Payment
from premiums.models import PremiumSchedule, PremiumPayment
from django.core.exceptions import ValidationError
from django.db import models

from django.db.models import Sum, Count, Prefetch, Q, Value
from django.db.models.functions import Coalesce
from datetime import date, timedelta
from django.utils import timezone
from typing import Any
from django.urls import reverse
from claims.models import Claim, ClaimNote, ClaimAuditLog, ClaimSettlement


# REGISTER

def register_view(request):

    if request.method == "POST":

        form = RegisterForm(request.POST, request.FILES)

        if form.is_valid():
            from django.db import transaction
            try:
                with transaction.atomic():
                    user = form.save(commit=False)

                    # 🛡️ SECURITY: Force lowest privilege role for public registration
                    # This prevents any attempt at role escalation via untrusted forms/APIs
                    user.role = 'user'
                    user.is_staff = False
                    user.is_superuser = False

                    password = form.cleaned_data["password"]
                    user.set_password(password)

                    # Ensure phone and address are saved to the User model
                    user.phone = form.cleaned_data.get("phone", "")
                    user.address = form.cleaned_data.get("address", "")

                    user.save()

                    # 🛡️ Create associated UserProfile
                    profile = UserProfile.objects.create(
                        user=user,
                        full_name=form.cleaned_data.get("full_name"),
                        aadhaar_number=form.cleaned_data.get("aadhaar_number"),
                        id_proof=request.FILES.get("id_proof")
                    )

                    # 🔍 Automated Identity Verification via OCR (Hardened Governance)
                    if profile.id_proof:
                        from ai_features.services.ocr_service import verify_identity
                        results = verify_identity(
                            profile.id_proof.path, 
                            profile.full_name, 
                            profile.aadhaar_number
                        )
                        
                        if results.get("verified"):
                            profile.is_verified = True
                            profile.verification_status = 'VERIFIED'
                            profile.save()
                            messages.success(request, f"Registration Successful. Identity Verified: Aadhaar {profile.masked_aadhaar} linked.")
                            return redirect("accounts:login")
                        else:
                            # 🛡️ MISMATCH FLOW: Rollback user creation
                            # Pass OCR extraction back to the form for field-level error display
                            form = RegisterForm(
                                request.POST, 
                                request.FILES, 
                                ocr_value=results.get('extracted_number'), 
                                ocr_name=results.get('extracted_name')
                            )
                            # This triggers the form's 'clean' logic with OCR context
                            form.is_valid()
                            # Raising ANY exception here triggers the transaction rollback
                            raise ValidationError("Dossier verification failed.")

                return redirect("accounts:login")

            except ValidationError as e:
                # Deduplicate: only add the error message if it's not already reported via form.clean()
                if not any(error == str(e) for error in form.non_field_errors()):
                    form.add_error(None, e.message)
            except Exception as e:

                # Generic fallback if AI service fails - permit manual verification
                messages.info(request, "Registration successful. ID verification will be handled by staff manually.")
                return redirect("accounts:login")

        else:


            messages.warning(request, "Please fix the errors below")

    else:

        form = RegisterForm()

    return render(request, "accounts/register.html", {"form": form})
    

# DASHBOARDS

@admin_only
def admin_dashboard(request):

    total_policies = Policy.objects.count()
    # 🔥 Governance FIX: Unfiltered base count for absolute totals
    total_claims = Claim.objects.count()
    settled_claims = Claim.objects.filter(status="settled").count()
    
    # Debug Output for verification
    print(f"[AI Audit] Dashboard Sync - Total: {total_claims} | Settled: {settled_claims}")

    # Admin dashboard should summarize all claims that are still in-process
    submitted_claims = Claim.objects.filter(status="submitted").count()
    review_claims = Claim.objects.filter(status="under_review").count()
    investigation_claims = Claim.objects.filter(status="investigation").count()
    
    # "Approved Claims" should include all claims that passed approval (legacy label)
    approved_claims = Claim.objects.filter(status__in=["approved", "partially_approved"]).count()
    settled_claims_count = Claim.objects.filter(status="settled").count()
    rejected_claims = Claim.objects.filter(status="rejected").count()

    total_staffs = User.objects.filter(role="staff").count()
    total_premium = PremiumSchedule.objects.aggregate(
        total=Sum("gross_premium")
    )["total"] or 0

    # Show all recent claims, sorted by AI priority score for review
    recent_claims = Claim.objects.all().select_related('created_by', 'policy').order_by('-priority_score', '-created_at')[:8]
    
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

    # ── AI Model Performance Tracking ─────────────────────────────────────────
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

    # ── Policy Application data ──────────────────────────────────────────────
    pending_applications = PolicyApplication.objects.filter(status='pending').count()
    pending_policy_applications = PolicyApplication.objects.filter(
        status='pending'
    ).select_related("user", "policy").order_by("-created_at")[:8]

    # 💰 Calculate Total Settled Amount (Ensuring legacy NULL fields are handled)
    total_settled_amount = Claim.objects.filter(status="settled").aggregate(
        total=Sum(Coalesce("settled_amount", "approved_amount", Value(0, output_field=models.DecimalField())))
    )["total"] or 0

    # ✅ Calculate Total Approved Amount (Excluding rejected, including settled)
    total_approved_amount = Claim.objects.filter(
        status__in=["approved", "partially_approved", "settled"]
    ).aggregate(
        total=Sum(Coalesce("approved_amount", "ai_predicted_amount", Value(0, output_field=models.DecimalField())))
    )["total"] or 0

    # 💳 Payment Statistics (Summing only successful transactions for actual revenue)
    # Using Payment model as the Unified Source of Truth to avoid double-counting installments
    successful_payments_qs = Payment.objects.filter(payment_status='completed', direction='CREDIT')
    
    successful_payment_value = successful_payments_qs.aggregate(total=Sum("amount"))["total"] or 0
    successful_payments_count = successful_payments_qs.count()
    
    total_payments = successful_payment_value
    failed_payments = Payment.objects.filter(payment_status='failed').count()


    # Recent payment history for dashboard
    recent_payments = Payment.objects.select_related(
        'user_policy', 
        'user_policy__user', 
        'user_policy__policy'
    ).order_by('-created_at')[:10]

    recent_settlements = ClaimSettlement.objects.select_related(
        'claim', 'claim__policy', 'claim__created_by'
    ).order_by('-settlement_date')[:10]

    # 💳 Unified Transaction Ledger (Clean Source of Truth)
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
            'audit_url': reverse('policy:manage_payment', args=[p.id])
        })

    context = {
        "total_users": User.objects.count(),
        "total_staffs": total_staffs,
        "total_policies": total_policies,
        "total_claims": total_claims,
        "submitted_claims": submitted_claims,
        "review_claims": review_claims,
        "investigation_claims": investigation_claims,
        "settled_claims": settled_claims_count,
        "approved_claims": approved_claims,
        "rejected_claims": rejected_claims,
        "total_premium": total_premium,
        "total_settled_amount": total_settled_amount,
        "total_approved_amount": total_approved_amount,
        "total_payments": total_payments,
        "successful_payments": successful_payments_count,
        "successful_payment_value": successful_payment_value,
        "failed_payments": failed_payments,
        "recent_claims": recent_claims,
        "recent_policies": recent_policies,
        "recent_financial_transactions": recent_financial_transactions,
        "pending_applications": pending_applications,
        "pending_policy_applications": pending_policy_applications,
        "current_user": request.user,
        "ai_metrics": latest_ai_metrics,
        "ai_performance_trend": performance_trend,
        "ai_performance_trend_abs": performance_trend_abs,
    }

    return render(request, "accounts/dashboard_admin.html", context)


@staff_or_admin
def staff_dashboard(request):

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
    total_claims = Claim.objects.count()
    status_counts = Claim.objects.values('status').annotate(count=Count('id'))
    
    # Specific KPI for top cards (Workflow aligned)
    kpi = {
        'total_claims': total_claims,
        'submitted_claims': Claim.objects.filter(status="submitted").count(),
        'review_claims': Claim.objects.filter(status="under_review").count(),
        'investigation_claims': Claim.objects.filter(status="investigation").count(),
        'settled_claims': Claim.objects.filter(status="settled").count(),
        'processed_claims': Claim.objects.filter(status__in=["approved", "rejected", "settled"]).count(),
    }
    
    claim_status_summary = []
    for s in status_counts:
        status = s['status']
        count = s['count']
        pct = (count / total_claims * 100) if total_claims > 0 else 0
        
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

    # Policy information for the inventory screen
    all_policies = Policy.objects.all().order_by("-created_at")

    # Efficiency Rate
    total_handled = Claim.objects.exclude(status='draft').count()
    success_count = Claim.objects.filter(status__in=['approved', 'settled', 'partially_approved']).count()
    efficiency = (success_count / total_handled * 100) if total_handled > 0 else 0

    # Monthly performance
    six_months_ago = timezone.now() - timedelta(days=180)
    monthly_perf_raw = Claim.objects.filter(created_at__gte=six_months_ago).values('created_at__month').annotate(count=Count('id')).order_by('created_at__month')
    
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

    # Enhancing claims with SLA tracking
    now = timezone.now()
    enhanced_claims = []
    for claim in claims_qs:
        # SLA tracking (Ensuring type safety for date subtraction)
        days_old = (now.date() - claim.reported_date.date()).days

        sla_status = 'on-track'
        if days_old > 7: sla_status = 'overdue'
        elif days_old > 3: sla_status = 'warning'
        
        claim.sla_days = days_old
        claim.sla_status = sla_status
        
        # Policy & Payment Validation (Correct logic)
        user_policy = UserPolicy.objects.filter(user=claim.created_by, policy=claim.policy, status='active').first()
        claim.is_policy_active = user_policy is not None
        
        # Check for successful payments
        payments_completed = Payment.objects.filter(user_policy=user_policy, payment_status='completed').exists() if user_policy else False
        claim.is_premium_paid = payments_completed

        # Dynamic AI Refresh (If missing)
        if not claim.ai_predicted_amount:
            try:
                from ai_features.services.amount_service import predict_recommended_amount
                claim.ai_predicted_amount = predict_recommended_amount(claim)
                # Persist the prediction so it's consistent across all views
                claim.save(update_fields=['ai_predicted_amount'])
            except Exception:
                # Fallback: simple 85% of claimed amount if AI service fails
                claim.ai_predicted_amount = float(claim.claimed_amount) * 0.85
        
        enhanced_claims.append(claim)

    # Staff Performance Data (Enhanced with Process Time)
    from django.db.models import Avg, F, ExpressionWrapper, fields
    from django.contrib.auth import get_user_model
    User = get_user_model()
    
    # Get all staff members (role='staff') to ensure no empty state
    staff_users = User.objects.filter(role='staff')
    staff_analytics = []
    
    for staff_user in staff_users:
        s_claims = Claim.objects.filter(assigned_to=staff_user)
        
        # 1. Total Handled
        total_audit = s_claims.count()
        if total_audit == 0:
            staff_analytics.append({
                'user': staff_user,
                'total_audit': 0,
                'accuracy': 0,
                'avg_process_time': 0,
                'avg_rec': 0
            })
            continue

        # 2. Approval Accuracy
        approvals = s_claims.filter(status__in=['approved', 'settled']).count()
        accuracy = (approvals / total_audit * 100)
        
        # 3. Avg. Rec Payout
        avg_rec = s_claims.aggregate(Avg('recommended_amount'))['recommended_amount__avg'] or 0
        
        # 4. Avg. Process Time (Difference between created_at and updated_at for non-pending)
        processed_claims = s_claims.exclude(status__in=['submitted', 'under_review'])
        if processed_claims.exists():
            duration_qs = processed_claims.annotate(
                duration=ExpressionWrapper(F('updated_at') - F('created_at'), output_field=fields.DurationField())
            ).aggregate(Avg('duration'))
            avg_duration = duration_qs['duration__avg']
            avg_hours = avg_duration.total_seconds() / 3600 if avg_duration else 0
        else:
            avg_hours = 0
            
        # New Metrics: Total Audited and Avg Rec
        total_audited = s_claims.aggregate(sum_val=Sum('claimed_amount'))['sum_val'] or 0
        avg_rec = s_claims.filter(status__in=['approved', 'settled', 'partially_approved']).aggregate(avg_val=Avg('approved_amount'))['avg_val'] or 0

        staff_analytics.append({
            'user': staff_user,
            'total_audit': total_audit,
            'accuracy': round(accuracy, 1),
            'avg_process_time': round(avg_hours, 1),
            'avg_rec': round(float(avg_rec), 0),
            'total_audited': round(float(total_audited), 0)
        })

    # Separate claims for different dashboard sections
    waiting_claims = [c for c in enhanced_claims if c.status in ["submitted", "under_review", "investigation"]]
    processed_claims = [c for c in enhanced_claims if c.status in ["approved", "rejected", "settled", "closed", "partially_approved"]]
    workspace_metrics = {
        'pending_count': len(waiting_claims),
        'completed_count': len(processed_claims),
        'overdue_count': sum(1 for c in waiting_claims if getattr(c, 'sla_status', '') == 'overdue'),
        'attention_count': sum(
            1
            for c in waiting_claims
            if (
                getattr(c, 'sla_status', '') != 'on-track'
                or not getattr(c, 'is_policy_active', False)
                or not getattr(c, 'is_premium_paid', False)
                or getattr(c, 'fraud_flag', False)
            )
        ),
    }

    context = {
        'claims': waiting_claims,  # Primary actionable list
        'waiting_claims': waiting_claims,
        'processed_claims': processed_claims,
        'recent_claims': processed_claims[:10], # Only show actually processed claims in history
        'workspace_metrics': workspace_metrics,
        'kpi': kpi,
        'efficiency': round(efficiency, 1),
        'monthly_perf': monthly_perf,
        'staff_analytics': sorted(staff_analytics, key=lambda x: x['total_audit'], reverse=True),
        'claim_status_summary': claim_status_summary,
        'all_policies': all_policies,
        'status_choices': Claim.STATUS,
        'type_choices': Claim.CLAIM_TYPE,
    }

    return render(request, "accounts/dashboard_staff.html", context)



@role_required(allowed_roles=['user'])
def policyholder_dashboard(request):
    """
    Enforces policyholder/user role access while allowing Admins to access for support.
    """


    context: dict[str, Any] = {}

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

        # 🔥 DYNAMIC SYNC: Re-evaluate policy health (Overdue/Grace/Lapsed) before calculations
        # This ensures the KPI cards and Tables show accurate REAL-TIME status.
        for up in user_policies_qs:
            up.sync_status_with_premiums()
        
        # Fresh queryset with updated statuses from DB
        user_policies = user_policies_qs.all()

        # Claims relevant to this user
        # Heuristic: User identifies themselves as 'created_by' 
        # OR they own the policy instance (UserPolicy) and the claim matches that policy (+ vehicle if motor)
        user_policy_list = list(user_policies.values('policy_id', 'vehicle_number'))
        owned_policy_ids = [up['policy_id'] for up in user_policy_list]
        owned_vehicles = [up['vehicle_number'] for up in user_policy_list if up['vehicle_number']]

        # Base filter: User submitted OR policy matches one of their owned plans
        claims_q = Q(created_by=request.user) | Q(policy_id__in=owned_policy_ids)
        claims = Claim.objects.filter(claims_q).distinct()

        # Refine: For motor claims, only show if vehicle number matches user's policy
        # For staff-submitted claims, we assume it's for this user if they hold that unique policy plan
        # (This aligns with the 'Self' identity logic in admin review)
        if owned_vehicles:
            # Keep claims where (not motor) OR (motor AND vehicle matches) OR (submitted by user)
            claims = claims.filter(
                Q(created_by=request.user) | 
                Q(vehicle_number__isnull=True) | 
                Q(vehicle_number="") |
                Q(vehicle_number__in=owned_vehicles)
            )

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

        context['kpi'] = {
            'total_policies':   user_policies.count(),
            'active_policies':  active_user_policies.count(),
            'total_claims':     claims.count(),
            'open_claims':      open_claims.count(),
            'total_sum_insured': total_sum,
            'total_settled':    total_settled,
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
        context['settled_claims'] = claims.filter(status='settled').select_related('settlement').order_by('-updated_at')

        # ── Policy Applications ───────────────────────────────────────────────
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

            # 🔥 DYNAMIC STATUS UPDATE: Ensure overdue/lapsed states are captured before rendering
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
            'total_claims': 0, 'open_claims': 0,
            'total_sum_insured': 0, 'total_settled': 0,
        }
        context['policies'] = []
        context['expiring_policies'] = []
        context['claim_status_summary'] = []
        context['recent_claims'] = []
        context['premium_payments'] = []

    return render(request, "accounts/dashboard_policyholder.html", context)


@login_required
def profile_view(request):
    if request.user.is_admin:
        return render(request, "accounts/profile_admin.html")
    elif request.user.is_staff_member:
        return render(request, "accounts/profile_staff.html")
    elif request.user.is_user:
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


# LOGIN

def login_view(request):

    if request.method == "POST":

        username = request.POST.get("username")
        password = request.POST.get("password")

        user = authenticate(request,username=username,password=password)

        if user is not None:
            # 🛡️ IDENTITY GATING: Enforce Aadhaar verification status
            if hasattr(user, 'profile'):
                if user.profile.verification_status == 'MISMATCH':
                    messages.error(request, "Your account verification failed due to Aadhaar mismatch. Please contact support or register again.")
                    return render(request, "accounts/login.html")
                
                if not user.profile.is_verified and user.profile.verification_status == 'PENDING':
                    messages.warning(request, "Account verification is currently pending. Please check back later.")
                    return render(request, "accounts/login.html")

            login(request,user)
            return redirect(user.dashboard_url)


        else:

            messages.error(request,"Invalid username or password")

    return render(request,"accounts/login.html")


# LOGOUT

def logout_view(request):

    logout(request)

    return redirect("accounts:login")


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
            
            # 🛡️ Hardened Staff Assignment (Forces role, prevents shadow escalation)
            user.role = 'staff'
            user.is_staff = True
            user.is_superuser = False
            
            user.set_password(form.cleaned_data["password"])
            user.save()
            
            # 🏙️ Create Staff Profile (Admin Provisioned)
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


from django.http import JsonResponse
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

    suggestions = []

    # 1. Search Claims
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
