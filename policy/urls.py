from django.urls import path
from . import views

app_name = "policy"

urlpatterns = [

    path("", views.policy_list, name="list"),
    path("my/", views.policy_list, name="my_policies"),
    path("admin/", views.admin_policy_list, name="admin_list"),
    path("create/", views.create_policy, name="create"),
    path("<uuid:id>/", views.policy_detail, name="detail"),
    path("edit/<uuid:id>/", views.edit_policy, name="edit"),
    path("status/<uuid:id>/", views.update_policy_status, name="update_status"),
    path("delete/<uuid:id>/", views.delete_policy, name="delete"),
    path("browse/", views.browse_policies, name="browse"),
    path("apply/<uuid:policy_id>/", views.apply_policy, name="apply"),
    path("buy-policy/<uuid:policy_id>/", views.buy_policy, name="buy_policy"),

    # ── Category Management ─────────────────────────────────────────
    path("categories/", views.manage_categories, name="manage_categories"),
    path("api/categories/", views.CategoryAPIView.as_view(), name="api_categories"),
    path("api/categories/<int:pk>/", views.CategoryDetailAPIView.as_view(), name="api_category_detail"),

    # ── Application Workflow ────────────────────────────────────────
    path("applications/my/", views.my_applications, name="my_applications"),
    path("applications/detail/<uuid:application_id>/", views.user_application_detail, name="application_detail"),
    path("applications/admin/", views.admin_applications_list, name="admin_applications"),
    path("applications/review/<uuid:application_id>/", views.admin_review_application, name="admin_review"),
    path("api/applications/review/generate-note/<uuid:application_id>/", views.api_generate_admin_note, name="api_generate_note"),

    # ── Payment Management ──────────────────────────────────────────
    path("payments/", views.payment_list, name="payment_list"),
    path("payments/manage/<uuid:payment_id>/", views.manage_payment, name="manage_payment"),
    path("make-payment/<uuid:user_policy_id>/", views.make_payment, name="make_payment"),
    path("plans/", views.plan_list, name="plan_list"),
]
