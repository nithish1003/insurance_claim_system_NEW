from django.urls import path
from . import views

app_name = "accounts"

urlpatterns = [

path("register/",views.register_view,name="register"),
path("login/",views.login_view,name="login"),
path("logout/",views.logout_view,name="logout"),

path("admin-dashboard/",views.admin_dashboard,name="admin_dashboard"),
path("admin-create-staff/", views.admin_create_staff, name="admin_create_staff"),
path("staff-dashboard/",views.staff_dashboard,name="staff_dashboard"),
path("policyholder-dashboard/",views.policyholder_dashboard,name="policyholder_dashboard"),
path("profile/",views.profile_view,name="profile"),
path("profile/edit/",views.edit_profile,name="edit_profile"),

    path("password-reset/", views.CustomPasswordResetView.as_view(), name="password_reset"),
    path("password-reset/done/", views.CustomPasswordResetDoneView.as_view(), name="password_reset_done"),
    path("password-reset-confirm/<uidb64>/<token>/", views.CustomPasswordResetConfirmView.as_view(), name="password_reset_confirm"),
    path("password-reset-complete/", views.CustomPasswordResetCompleteView.as_view(), name="password_reset_complete"),

    path("staff-search-suggestions/", views.staff_search_suggestions, name="staff_search_suggestions"),
]