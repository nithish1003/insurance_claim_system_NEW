from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'api/alerts', views.NotificationViewSet, basename='notification')

urlpatterns = [
    path('', include(router.urls)),
    
    # 🎨 Platform UI Paths
    path('settings/', views.notification_settings_view, name='settings'),
    path('inbox/', views.notification_list_view, name='history'),
    path('redirect/<uuid:pk>/', views.notification_redirect, name='redirect'),
    
    # 📊 Executive Mission Control
    path('admin-center/', views.admin_notification_center, name='admin_center'),
]
