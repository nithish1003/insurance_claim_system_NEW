from django.urls import path
from . import views

app_name = 'reports'

urlpatterns = [
    path('', views.reports_dashboard, name='dashboard'),
    path('admin/', views.admin_reports, name='admin'),
    path('staff/', views.staff_reports, name='staff'),
    path('api/activity/', views.get_activity_logs, name='api_activity'),
    path('api/alerts/', views.get_fraud_alerts, name='api_alerts'),
]
