from django.contrib import admin
from django.utils import timezone
from .models import (
    UserProfile,
    PolicyHolder,
    UserPolicy,
    Policy,
    Coverage,
    Beneficiary,
    Premium,
    PolicyDocument,
    PolicyAuditLog,
    PolicyType,
    Insurer,
    PolicyPlan,
    PolicyApplication,
    Payment
)

@admin.register(PolicyType)
class PolicyTypeAdmin(admin.ModelAdmin):
    list_display = ("name", "code")

@admin.register(Insurer)
class InsurerAdmin(admin.ModelAdmin):
    list_display = ("name", "contact_email")


@admin.register(PolicyPlan)
class PolicyPlanAdmin(admin.ModelAdmin):
    list_display = ("name", "policy_type", "insurer", "sum_insured", "deductible")
    readonly_fields = ("deductible",)
    search_fields = ("name",)


# -----------------------
# Policy Holder Admin
# -----------------------

@admin.register(PolicyHolder)
class PolicyHolderAdmin(admin.ModelAdmin):

    list_display = ("id", "user", "policy", "purchased_at")

    search_fields = ("user__username", "policy__policy_number")

    list_filter = ("purchased_at",)


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):

    list_display = ("id", "user", "phone", "city", "state", "created_at")

    search_fields = ("user__username", "phone", "city")

    list_filter = ("state",)


# -----------------------
# Policy Admin
# -----------------------

@admin.register(Policy)
class PolicyAdmin(admin.ModelAdmin):

    list_display = (
        "policy_number",
        "policy_type",
        "status",
        "start_date",
        "end_date",
        "sum_insured",
        "gross_premium"
    )

    list_filter = ("policy_type", "status")

    search_fields = ("policy_number", "insurer_name")

    ordering = ("-created_at",)
    readonly_fields = (
        "deductible",
        "base_premium",
        "gst_amount",
        "gross_premium"
    )


# -----------------------
# Coverage Admin
# -----------------------

@admin.register(Coverage)
class CoverageAdmin(admin.ModelAdmin):

    list_display = (
        "coverage_type",
        "policy",
        "limit_amount",
        "deductible"
    )

    search_fields = ("coverage_type",)


# -----------------------
# Beneficiary Admin
# -----------------------

@admin.register(Beneficiary)
class BeneficiaryAdmin(admin.ModelAdmin):

    list_display = (
        "name",
        "policy",
        "relationship",
        "share_percentage"
    )

    search_fields = ("name",)


# -----------------------
# Premium Admin
# -----------------------

@admin.register(Premium)
class PremiumAdmin(admin.ModelAdmin):

    list_display = (
        "policy",
        "amount",
        "due_date",
        "status"
    )

    list_filter = ("status",)

    search_fields = ("transaction_id",)


# -----------------------
# Policy Document Admin
# -----------------------

@admin.register(PolicyDocument)
class PolicyDocumentAdmin(admin.ModelAdmin):

    list_display = (
        "document_name",
        "policy",
        "uploaded_at"
    )

    search_fields = ("document_name",)


# -----------------------
# Audit Log Admin
# -----------------------

@admin.register(PolicyAuditLog)
class PolicyAuditLogAdmin(admin.ModelAdmin):

    list_display = (
        "policy",
        "action",
        "performed_by",
        "created_at"
    )

    search_fields = ("action",)

    readonly_fields = ("created_at",)


# -----------------------
# Policy Application Admin
# -----------------------

def approve_applications(modeladmin, request, queryset):
    """Bulk approve selected pending applications."""
    queryset.filter(status='pending').update(
        status='approved',
        reviewed_at=timezone.now(),
        reviewed_by=request.user
    )
approve_applications.short_description = "✅ Approve selected applications"


def reject_applications(modeladmin, request, queryset):
    """Bulk reject selected pending applications."""
    queryset.filter(status='pending').update(
        status='rejected',
        reviewed_at=timezone.now(),
        reviewed_by=request.user
    )
reject_applications.short_description = "❌ Reject selected applications"


@admin.register(PolicyApplication)
class PolicyApplicationAdmin(admin.ModelAdmin):

    list_display = (
        "id",
        "user",
        "policy",
        "status",
        "created_at",
        "reviewed_at",
        "reviewed_by",
    )

    list_filter = ("status", "created_at")

    search_fields = ("user__username", "policy__policy_number", "admin_remarks")

    readonly_fields = ("created_at", "reviewed_at")

    ordering = ("-created_at",)

    actions = [approve_applications, reject_applications]


# -----------------------
# User Policy Admin
# -----------------------

@admin.register(UserPolicy)
class UserPolicyAdmin(admin.ModelAdmin):

    list_display = (
        "certificate_number",
        "user",
        "policy",
        "status",
        "start_date",
        "end_date",
        "assigned_at",
    )

    list_filter = ("status", "assigned_at")

    search_fields = (
        "certificate_number",
        "user__username",
        "policy__policy_number",
    )

    readonly_fields = ("certificate_number", "assigned_at")

    ordering = ("-assigned_at",)


# -----------------------
# Payment Admin
# -----------------------

@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    
    list_display = (
        "transaction_id",
        "user_policy",
        "amount",
        "payment_status",
        "payment_method",
        "created_at",
        "completed_at"
    )

    list_filter = (
        "payment_status", 
        "payment_method", 
        "created_at",
        "completed_at"
    )

    search_fields = (
        "transaction_id",
        "user_policy__certificate_number",
        "user_policy__user__username",
        "gateway_reference"
    )

    readonly_fields = (
        "transaction_id",
        "created_at",
        "completed_at"
    )

    ordering = ("-created_at",)

    fieldsets = (
        ("Payment Information", {
            'fields': ('user_policy', 'amount', 'payment_status', 'payment_method')
        }),
        ("Transaction Details", {
            'fields': ('transaction_id', 'gateway_reference', 'description', 'notes')
        }),
        ("Timestamps", {
            'fields': ('created_at', 'completed_at')
        }),
        ("Metadata", {
            'fields': ('payment_metadata',)
        }),
    )

    def get_queryset(self, request):
        """Optimize queries by selecting related objects"""
        return super().get_queryset(request).select_related(
            'user_policy', 
            'user_policy__user', 
            'user_policy__policy'
        )
