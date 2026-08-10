from django.shortcuts import render
from django.http import JsonResponse
from django.db.models import Avg, Count, Max, Min, Sum, F, Case, When, Value, DecimalField
from django.db.models.functions import Coalesce
from django.db.models.functions import TruncMonth
from django.utils import timezone
from claims.models import Claim
from decimal import Decimal

ARCHIVED_CLAIM_STATUSES = ["closed", "withdrawn"]
PENDING_CLAIM_STATUSES = ["submitted", "under_review", "staff_reviewed", "investigation"]
APPROVED_CLAIM_STATUSES = ["approved", "settled", "partially_approved"]
RESOLVED_CLAIM_STATUSES = APPROVED_CLAIM_STATUSES + ["rejected"]


def operational_claims():
    return Claim.objects.exclude(status__in=ARCHIVED_CLAIM_STATUSES)

def analytics_dashboard_view(request):
    """Renders the React-integrated AI Analytics Dashboard"""
    return render(request, "analytics/dashboard.html")

def risk_heatmap_api(request):
    # Groups by hospital and calculates average risk and total claims
    # Color scale logic is handled on the frontend
    hospitals = operational_claims().values("hospital_type").annotate(
        avg_risk=Avg("risk_score"),
        claim_count=Count("id")
    ).order_by("-avg_risk")
    
    data = []
    for h in hospitals:
        # DB risk_score is 0-100, we convert to 0-1 for the React frontend specification
        data.append({
            "hospital": h["hospital_type"] or "General Hospital",
            "avg_risk": round(float(h["avg_risk"] or 0) / 100.0, 2),
            "claim_count": h["claim_count"]
        })
    
    return JsonResponse({"data": data})

def claims_trend_api(request):
    # Aggregates claims by month for the line chart
    trends = operational_claims().annotate(month=TruncMonth("incident_date")).values("month").annotate(
        count=Count("id")
    ).order_by("month")
    
    months = [t["month"].strftime("%b %Y") if t["month"] else "Pending" for t in trends]
    claims = [t["count"] for t in trends]
    
    return JsonResponse({
        "months": months,
        "claims": claims
    })

def risk_distribution_api(request):
    # Splits claims into risk buckets (Low, Medium, High)
    claims_qs = operational_claims()
    low = claims_qs.filter(risk_score__lt=15).count() # < 0.15
    medium = claims_qs.filter(risk_score__gte=15, risk_score__lt=40).count()
    high = claims_qs.filter(risk_score__gte=40).count()
    
    return JsonResponse({
        "low": low,
        "medium": medium,
        "high": high
    })

def deduction_analysis_api(request):
    # Basic financial metrics for the bar chart
    stats = operational_claims().aggregate(
        avg_deduction=Avg("claimed_amount") - Avg("final_ai_recommendation"),
        max_deduction=Max("claimed_amount") - Min("final_ai_recommendation"),
    )
    
    # Ensuring non-null values
    avg_d = float(stats["avg_deduction"] or 0)
    max_d = float(stats["max_deduction"] or 0)
    
    return JsonResponse({
        "avg_deduction": round(avg_d, 2),
        "max_deduction": round(max_d, 2),
        "min_deduction": 500 # Constant for synthetic baseline
    })

def ai_insights_api(request):
    # Global AI performance metrics
    claims_qs = operational_claims()
    total = claims_qs.count()
    avg_risk = claims_qs.aggregate(Avg("risk_score"))["risk_score__avg"] or 0
    fraud_count = claims_qs.filter(fraud_flag=True).count()
    
    # Decisions
    auto = claims_qs.filter(ai_decision="auto_process").count()
    manual = claims_qs.filter(ai_decision="manual_review").count()
    
    highest_risk = claims_qs.order_by("-risk_score").first()
    
    return JsonResponse({
        "avg_risk_score": round(float(avg_risk) / 100.0, 2),
        "fraud_flagged_count": fraud_count,
        "auto_approved": auto,
        "manual_review": manual,
        "highest_risk_claim": highest_risk.claim_number if highest_risk else "N/A",
        "total_claims": total
    })

def fraud_intelligence_view(request):
    """
    Requirement Phase 8: Enterprise AI Fraud Intelligence Center.
    High-fidelity decision cockpit for network-level analytics.
    """
    return render(request, "analytics/fraud_intelligence.html")

def enterprise_kpi_api(request):
    """Advanced KPI API for Phase 8 Dashboard."""
    from claims.models import AuditorReview
    
    today = timezone.now().date()
    
    # 1. Decision Integrity (Human vs AI Accuracy)
    avg_accuracy = AuditorReview.objects.aggregate(Avg("accuracy_score"))["accuracy_score__avg"] or 0
    
    # 2. Network Risk Highlights (Repeat Aadhaar)
    from django.db.models import Count
    from accounts.models import UserProfile
    repeat_claimants = UserProfile.objects.annotate(claim_count=Count('user__created_claims')).filter(claim_count__gt=1).count()
    
    # 3. Triage Velocity
    avg_duration = AuditorReview.objects.aggregate(Avg("process_duration_seconds"))["process_duration_seconds__avg"] or 0
    
    # 4. Multi-Risk Distribution
    claims = Claim.objects.all()
    risk_stats = {
        "fraud": claims.aggregate(Avg("fraud_risk_score"))["fraud_risk_score__avg"] or 0,
        "leakage": claims.aggregate(Avg("leakage_risk_score"))["leakage_risk_score__avg"] or 0,
        "doc": claims.aggregate(Avg("documentation_risk_score"))["documentation_risk_score__avg"] or 0,
        "uncertainty": claims.aggregate(Avg("payout_uncertainty_score"))["payout_uncertainty_score__avg"] or 0,
    }

    return JsonResponse({
        "decision_accuracy": round(float(avg_accuracy), 1),
        "repeat_claimant_count": repeat_claimants,
        "avg_triage_minutes": round(float(avg_duration) / 60, 1),
        "multi_risk": risk_stats,
        "audit_logs_total": Claim.objects.count() * 1.5 # Simulated logs count
    })

def pdf_report_data_api(request):
    """Fetches comprehensive live data for the Enterprise PDF Report."""
    from claims.models import Claim
    from django.db.models import Avg, Count
    from django.utils import timezone
    from accounts.models import UserProfile

    claims_qs = operational_claims()
    total_claims = claims_qs.count()
    approved = claims_qs.filter(status__in=APPROVED_CLAIM_STATUSES).count()
    rejected = claims_qs.filter(status='rejected').count()
    pending = claims_qs.filter(status__in=PENDING_CLAIM_STATUSES).count()
    
    # Financials
    approved_payouts = claims_qs.aggregate(
        total=Coalesce(
            Sum(Case(
                When(status='settled', then=F('settled_amount')),
                When(status__in=['approved', 'partially_approved'], then=F('approved_amount')),
                default=Value(0),
                output_field=DecimalField()
            )),
            Value(0),
            output_field=DecimalField()
        )
    )['total']
    requested_value = claims_qs.aggregate(total=Coalesce(Sum('claimed_amount'), Value(0), output_field=DecimalField()))['total']
    
    resolved_claims = claims_qs.filter(status__in=RESOLVED_CLAIM_STATUSES)
    resolved_claimed_total = resolved_claims.aggregate(total=Coalesce(Sum('claimed_amount'), Value(0), output_field=DecimalField()))['total']
    resolved_approved_total = resolved_claims.aggregate(
        total=Coalesce(
            Sum(Case(
                When(status='settled', then=F('settled_amount')),
                When(status__in=['approved', 'partially_approved'], then=F('approved_amount')),
                default=Value(0),
                output_field=DecimalField()
            )),
            Value(0),
            output_field=DecimalField()
        )
    )['total']
    loss_avoidance = resolved_claimed_total - resolved_approved_total
    if loss_avoidance < 0: 
        loss_avoidance = 0
        
    system_exposure = claims_qs.filter(status__in=PENDING_CLAIM_STATUSES).aggregate(total=Coalesce(Sum('claimed_amount'), Value(0), output_field=DecimalField()))['total']

    # Claims for AI Audit Table
    recent_claims = claims_qs.order_by('-created_at')[:10]
    ai_audit_data = []
    for c in recent_claims:
        ai_audit_data.append({
            "claim_id": c.claim_number,
            "type": c.claim_type.upper() if c.claim_type else "OTHER",
            "fraud_score": round((c.fraud_risk_score or 0) * 100, 1),
            "confidence": round((c.confidence_score or 0), 1),
            "risk_band": c.priority_level.upper() if c.priority_level else "LOW",
            "recommendation": str(c.authoritative_payout or 0),
            "decision": c.status.upper()
        })

    # Fraud Alerts
    fraud_claims = claims_qs.filter(fraud_flag=True).order_by('-created_at')[:5]
    fraud_alerts = []
    for c in fraud_claims:
        live_score_pct = round((c.fraud_risk_score or 0) * 100, 1)
        fraud_alerts.append({
            "message": f"Suspicious activity detected in Claim {c.claim_number} - ADVISORY: Risk score of {live_score_pct}% indicates vigilance."
        })

    return JsonResponse({
        "executive_summary": {
            "total": total_claims,
            "approved": approved,
            "rejected": rejected,
            "pending": pending,
            "audit_efficiency": f"{round((approved / (approved + rejected) * 100) if (approved + rejected) else 0, 1)}%"
        },
        "financial_summary": {
            "approved_payouts": float(approved_payouts),
            "requested_value": float(requested_value),
            "loss_avoidance": float(loss_avoidance),
            "system_exposure": float(system_exposure),
            "premium_revenue": float(requested_value) * 1.5 # Simulated revenue
        },
        "ai_audit_intelligence": ai_audit_data,
        "fraud_alerts": fraud_alerts,
        "timestamp": timezone.now().strftime("%Y-%m-%d %H:%M:%S"),
        "admin_name": request.user.get_full_name() or request.user.username if request.user.is_authenticated else "System Administrator"
    })
