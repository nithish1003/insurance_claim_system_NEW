from django.urls import path
from . import views

app_name = "premiums"

urlpatterns = [
    path("", views.premium_list, name="list"),
    path("create/", views.premium_create, name="create"),
    path("policies/dues-summary/", views.policy_dues_summary_api, name="dues_summary_api"),
    path("policies/<uuid:user_policy_id>/dues/", views.policy_dues_detail, name="policy_dues_detail"),
    path("policies/<uuid:user_policy_id>/dues/api/", views.policy_dues_api, name="policy_dues_api"),
    path("<uuid:id>/", views.premium_detail, name="detail"),
    path("pay/<uuid:payment_id>/", views.premium_pay, name="pay"),
    path("pay/<uuid:payment_id>/razorpay/create/", views.api_create_razorpay_order, name="razorpay_create"),
    path("pay/<uuid:payment_id>/razorpay/verify/", views.api_verify_payment, name="razorpay_verify"),
    path("history/", views.premium_history, name="history"),
    path("api/get-policy-details/<uuid:policy_id>/", views.get_policy_premium_details, name="get_policy_details"),
]
