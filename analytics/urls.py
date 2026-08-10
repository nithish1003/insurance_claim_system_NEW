from django.urls import path
from . import views

app_name = "analytics"

urlpatterns = [
    path("dashboard/", views.analytics_dashboard_view, name="dashboard"),
    path("risk-heatmap/", views.risk_heatmap_api, name="risk_heatmap"),
    path("claims-trend/", views.claims_trend_api, name="claims_trend"),
    path("risk-distribution/", views.risk_distribution_api, name="risk_distribution"),
    path("deduction-analysis/", views.deduction_analysis_api, name="deduction_analysis"),
    path("ai-insights/", views.ai_insights_api, name="ai_insights"),
    path("fraud-intelligence/", views.fraud_intelligence_view, name="fraud_intelligence"),
    path("enterprise-kpi/", views.enterprise_kpi_api, name="enterprise_kpi"),
    path("pdf-report-data/", views.pdf_report_data_api, name="pdf_report_data"),
]
