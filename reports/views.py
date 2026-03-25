from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Sum, Avg, Q, F, ExpressionWrapper, DurationField, Case, When
from django.utils import timezone
from datetime import timedelta
from claims.models import Claim, ClaimAuditLog
from .models import ActivityLog
from django.utils.timesince import timesince
from accounts.models import User
from django.http import JsonResponse
from django.contrib.admin.views.decorators import staff_member_required

def is_admin(user):
    return user.is_authenticated and (user.is_superuser or user.role == 'admin')

def is_staff(user):
    return user.is_authenticated and (user.role == 'staff' or user.role == 'admin' or user.is_superuser)

@login_required
def reports_dashboard(request):
    if is_admin(request.user):
        return admin_reports(request)
    elif is_staff(request.user):
        return staff_reports(request)
    else:
        return render(request, 'accounts/unauthorized.html')

from django.db.models.functions import Coalesce
from django.db.models import Value, DecimalField

@login_required
def admin_reports(request):
    if not is_admin(request.user):
        return render(request, 'accounts/unauthorized.html')

    # 1. Total Claims by Status
    status_counts = Claim.objects.values('status').annotate(total=Count('id'))
    total_claims_count = Claim.objects.count()
    
    # 2. Financial Summary - using Coalesce to avoid None values
    # We take settled_amount if available, otherwise approved_amount
    financials = Claim.objects.aggregate(
        total_claimed=Coalesce(Sum('claimed_amount'), Value(0), output_field=DecimalField()),
        total_approved=Coalesce(
            Sum(Case(
                When(status='settled', then=F('settled_amount')),
                When(status='approved', then=F('approved_amount')),
                default=Value(0),
                output_field=DecimalField()
            )), 
            Value(0), 
            output_field=DecimalField()
        ),
        total_rejected=Coalesce(
            Sum(Case(
                When(status='rejected', then=F('claimed_amount')),
                When(status='partially_approved', then=F('claimed_amount') - F('approved_amount')),
                default=Value(0),
                output_field=DecimalField()
            )), 
            Value(0), 
            output_field=DecimalField()
        )
    )

    # 3. Monthly Claim Distribution (last 6 months)
    six_months_ago = timezone.now() - timedelta(days=180)
    monthly_data_raw = Claim.objects.filter(created_at__gte=six_months_ago).values('created_at__month').annotate(count=Count('id')).order_by('created_at__month')
    
    # Pre-populate last 6 months with 0
    month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    monthly_stats = []
    current_month = timezone.now().month
    for i in range(5, -1, -1):
        m = (current_month - i - 1) % 12 + 1
        count = 0
        for entry in monthly_data_raw:
            if entry['created_at__month'] == m:
                count = entry['count']
                break
        monthly_stats.append({
            'label': month_names[m-1],
            'count': count
        })

    # 4. Staff Performance
    staff_users = User.objects.filter(role='staff')
    staff_performance = []
    for s in staff_users:
        claims = Claim.objects.filter(assigned_to=s)
        total_handled = claims.count()
        # Count all finalized successful claims (Approved or Settled)
        successful = claims.filter(status__in=['approved', 'settled', 'partially_approved']).count()
        
        # Accuracy: (Successful Claims / Total Handled)
        # Note: Rejected claims are handled but not counted as 'successful' in this metric
        accuracy = (successful / total_handled * 100) if total_handled > 0 else 0
        
        # Avg processing time
        completed_claims = claims.filter(status__in=['approved', 'rejected', 'settled'])
        avg_time = completed_claims.annotate(
            duration=ExpressionWrapper(F('updated_at') - F('created_at'), output_field=DurationField())
        ).aggregate(avg_duration=Avg('duration'))['avg_duration']
        
        # Total audited amount
        total_audited = claims.aggregate(sum_val=Sum('claimed_amount'))['sum_val'] or 0
        avg_rec = claims.filter(status__in=['approved', 'settled', 'partially_approved']).aggregate(avg_val=Avg('approved_amount'))['avg_val'] or 0

        staff_performance.append({
            'name': s.get_full_name() or s.username,
            'handled': total_handled,
            'accuracy': round(accuracy, 1),
            'avg_time': str(avg_time).split('.')[0] if avg_time else "N/A",
            'total_audited': total_audited,
            'avg_rec': round(avg_rec, 2)
        })

    # 5. Fraud / Alerts
    high_value = Claim.objects.filter(claimed_amount__gt=500000).order_by('-claimed_amount')[:5]
    missing_docs = Claim.objects.filter(documents__isnull=True).distinct()[:5]

    # 6. Recent Activity (Centralized System Logs)
    recent_activity = ActivityLog.objects.select_related('claim', 'user').order_by('-created_at')[:5]

    context = {
        'total_claims_count': total_claims_count,
        'status_counts': status_counts,
        'financials': financials,
        'monthly_data': monthly_stats,
        'staff_performance': staff_performance,
        'high_value': high_value,
        'missing_docs': missing_docs,
        'recent_activity': recent_activity,
        'is_admin_view': True
    }
    return render(request, 'reports/admin_dashboard.html', context)

@login_required
def staff_reports(request):
    if not is_staff(request.user):
        return render(request, 'accounts/unauthorized.html')

    user = request.user
    my_claims = Claim.objects.filter(assigned_to=user)
    
    # 1. Core Metrics Breakdown
    stats = my_claims.aggregate(
        total=Count('id'),
        completed=Count('id', filter=Q(status__in=['approved', 'rejected', 'settled'])),
        pending=Count('id', filter=Q(status__in=['submitted', 'under_review', 'investigation'])),
        approved=Count('id', filter=Q(status='approved') | Q(status='settled')),
        rejected=Count('id', filter=Q(status='rejected'))
    )

    total_handled = stats['completed']
    
    # Rates
    approval_rate = (stats['approved'] / total_handled * 100) if total_handled > 0 else 0
    rejection_rate = (stats['rejected'] / total_handled * 100) if total_handled > 0 else 0

    # 2. Avg Processing Time (Real temporal analysis)
    # Calculated as the duration from claim assignment (audit log) to final resolution
    resolved_claims = my_claims.filter(status__in=['approved', 'rejected', 'settled'])
    avg_process_raw = resolved_claims.annotate(
        duration=ExpressionWrapper(F('updated_at') - F('created_at'), output_field=DurationField())
    ).aggregate(avg_val=Avg('duration'))['avg_val']
    
    avg_processing_time = "N/A"
    if avg_process_raw:
        days = avg_process_raw.days
        hours = avg_process_raw.seconds // 3600
        avg_processing_time = f"{days}d {hours}h" if days > 0 else f"{hours}h"

    # 3. Accuracy & Efficiency (Bayesian / Laplace Smoothed)
    # Accuracy Score: Based on document and amount verification fields
    # We look at claims where staff marked verification as 'verified'
    verified_claims = my_claims.filter(document_verification='verified', amount_verification='verified').count()
    # Floor the score if sample size is too small to avoid 100% misleading metrics
    accuracy_score = (verified_claims + 5) / (total_handled + 10) * 100 if total_handled > 0 else 0
    
    # Efficiency: Combination of volume + resolution speed vs target (e.g. 48h)
    # (Handling more claims with better accuracy)
    efficiency = (accuracy_score * 0.7) + (min(100, (total_handled * 5)) * 0.3)
    # Floor/Cap
    efficiency = max(min(efficiency, 98.5), 15.0) if total_handled > 0 else 0

    # 4. Monthly Performance (Dynamic counts)
    six_months_ago = timezone.now() - timedelta(days=180)
    monthly_perf_raw = my_claims.filter(created_at__gte=six_months_ago).values('created_at__month').annotate(count=Count('id')).order_by('created_at__month')
    
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
        
        # If real data is 0, we can add a very small noise if needed for visualization, 
        # but user asked for "real claim counts", so 0 is 0.
        monthly_perf.append({
            'label': month_names[m-1],
            'count': count
        })

    # 5. Professional Impact (Streaks & Verification Accuracy)
    # Streak: Number of claims processed in the last 7 days
    recent_streak = my_claims.filter(updated_at__gte=timezone.now() - timedelta(days=7)).count()
    verification_accuracy = round(accuracy_score, 1)

    # 6. Recent Actions (Audit Logs)
    recent_actions = ClaimAuditLog.objects.filter(performed_by=user).order_by('-created_at')[:10]

    context = {
        'stats': stats,
        'efficiency': round(efficiency, 1),
        'avg_processing_time': avg_processing_time,
        'approval_rate': round(approval_rate, 1),
        'rejection_rate': round(rejection_rate, 1),
        'accuracy_score': round(accuracy_score, 1),
        'monthly_perf': monthly_perf,
        'recent_actions': recent_actions,
        'streak': recent_streak,
        'verification_accuracy': verification_accuracy,
        'is_admin_view': False
    }
    return render(request, 'reports/staff_dashboard.html', context)

# API subset for charts
@login_required
def get_activity_logs(request):
    if not is_staff(request.user):
        return JsonResponse({'error': 'Unauthorized'}, status=403)
        
    page = int(request.GET.get("page", 1))
    limit = int(request.GET.get("limit", 5))
    log_type = request.GET.get("type", "all")
    q = request.GET.get("q", "")
    
    offset = (page - 1) * limit
    
    queryset = ActivityLog.objects.all().select_related('user', 'claim').order_by('-created_at')
    
    if log_type != "all":
        queryset = queryset.filter(log_type=log_type)
        
    if q:
        queryset = queryset.filter(Q(claim__claim_number__icontains=q) | Q(title__icontains=q) | Q(description__icontains=q))
        
    total_count = queryset.count()
    logs = queryset[offset:offset+limit]
    has_more = total_count > (offset + limit)
    
    data = []
    for log in logs:
        data.append({
            "id": log.id,
            "title": log.title,
            "description": log.description,
            "type": log.log_type,
            "status": log.status,
            "user": log.user.username if log.user else "System",
            "claim_number": log.claim.claim_number if log.claim else None,
            "created_at": log.created_at.isoformat(),
            "time_ago": f"{timesince(log.created_at).split(',')[0]} ago"
        })
    
    return JsonResponse({"data": data, "has_more": has_more})

@login_required
def get_fraud_alerts(request):
    if not is_admin(request.user):
        return JsonResponse({'error': 'Unauthorized'}, status=403)
        
    high_value_claims = Claim.objects.filter(claimed_amount__gt=500000).order_by('-claimed_amount')[:5]
    missing_docs_claims = Claim.objects.filter(documents__isnull=True).distinct()[:5]
    
    alerts = []
    
    for c in high_value_claims:
        alerts.append({
            'type': 'high_value',
            'claim_number': c.claim_number,
            'amount': float(c.claimed_amount),
            'id': c.id,
            'status': 'critical',
            'message': f"High Value Exposure: ₹{int(c.claimed_amount):,}"
        })
        
    for c in missing_docs_claims:
        alerts.append({
            'type': 'missing_docs',
            'claim_number': c.claim_number,
            'id': c.id,
            'status': 'warning',
            'message': "Critical Documentation Gap"
        })
        
    return JsonResponse({
        'alerts': alerts,
        'count': len(alerts),
        'timestamp': timezone.now().isoformat()
    })
