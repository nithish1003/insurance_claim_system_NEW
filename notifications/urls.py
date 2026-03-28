from django.urls import path
from . import views

app_name = 'notifications'

urlpatterns = [
    path('mark-read/<int:pk>/', views.mark_as_read, name='mark_as_read'),
    path('mark-all-read/', views.mark_all_as_read, name='mark_all_as_read'),
]
