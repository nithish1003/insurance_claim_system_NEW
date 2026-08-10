from django.urls import path
from . import views

app_name = 'assistant'

urlpatterns = [
    path('api/chat/', views.chat_api, name='chat_api'),
    path('api/feedback/', views.submit_feedback, name='submit_feedback'),
    path('api/autocomplete/', views.autocomplete_search, name='autocomplete_search'),
    path('admin-panel/', views.admin_panel, name='admin_panel'),
    path('documents/policy/<int:policy_id>/download/', views.download_policy, name='download_policy'),
    path('documents/invoice/<int:payment_id>/download/', views.download_receipt, name='download_receipt'),
]


