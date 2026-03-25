from django.urls import path
from . import views

app_name = "policy"

urlpatterns = [

    path("", views.policy_list, name="list"),
    path("my/", views.policy_list, name="my_policies"),
    path("admin/", views.admin_policy_list, name="admin_list"),
    path("create/", views.create_policy, name="create"),
    path("<int:id>/", views.policy_detail, name="detail"),
    path("edit/<int:id>/", views.edit_policy, name="edit"),
    path("status/<int:id>/", views.update_policy_status, name="update_status"),
    path("delete/<int:id>/", views.delete_policy, name="delete"),
    path("browse/", views.browse_policies, name="browse"),
    path("apply/<int:policy_id>/", views.apply_policy, name="apply"),

    # ── Category Management ─────────────────────────────────────────
    path("categories/", views.manage_categories, name="manage_categories"),

    # ── Application Workflow ────────────────────────────────────────
    path("applications/my/", views.my_applications, name="my_applications"),
    path("applications/admin/", views.admin_applications_list, name="admin_applications"),
    path("applications/review/<int:application_id>/", views.admin_review_application, name="admin_review"),

    # ── Payment Management ──────────────────────────────────────────
    path("payments/", views.payment_list, name="payment_list"),
    path("payments/manage/<int:payment_id>/", views.manage_payment, name="manage_payment"),
]
