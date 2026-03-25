from django.urls import path
from . import views

app_name = "premiums"

urlpatterns = [
    path("", views.premium_list, name="list"),
    path("create/", views.premium_create, name="create"),
    path("<int:id>/", views.premium_detail, name="detail"),
    path("pay/<int:payment_id>/", views.premium_pay, name="pay"),
    path("history/", views.premium_history, name="history"),
    path("api/get-policy-details/<int:policy_id>/", views.get_policy_premium_details, name="get_policy_details"),
]
