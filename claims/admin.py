from django.contrib import admin
from .models import (
    Claim,
    Claimant,
    ClaimDocument,
    ClaimAssessment,
    ClaimSettlement,
    ClaimNote,
    ClaimAuditLog
)


# -----------------------------
# Inline Models
# -----------------------------

class ClaimantInline(admin.TabularInline):
    model = Claimant
    extra = 0


class ClaimDocumentInline(admin.TabularInline):
    model = ClaimDocument
    extra = 0


class ClaimNoteInline(admin.TabularInline):
    model = ClaimNote
    extra = 0


class ClaimAuditInline(admin.TabularInline):
    model = ClaimAuditLog
    extra = 0
    readonly_fields = ("action", "performed_by", "created_at")


# -----------------------------
# Claim Admin
# -----------------------------

@admin.register(Claim)
class ClaimAdmin(admin.ModelAdmin):

    list_display = (
        "claim_number",
        "policy",
        "claim_type",
        "status",
        "claimed_amount",
        "display_approved_amount",
        "settled_amount",
        "assigned_to",
        "created_at",
    )

    def display_approved_amount(self, obj):
        from django.utils.html import format_html
        amount = obj.total_settled_amount
        if amount == 0:
            return format_html('<span style="color: #999;">-</span>')
        return f"₹{amount:,.2f}"
    display_approved_amount.short_description = "Approved/Settled Amount"
    display_approved_amount.admin_order_field = 'approved_amount'

    list_filter = (
        "status",
        "claim_type",
        "created_at",
    )

    search_fields = (
        "claim_number",
        "policy__policy_number",
    )

    ordering = ("-created_at",)

    readonly_fields = (
        "created_at",
        "updated_at",
    )

    inlines = [
        ClaimantInline,
        ClaimDocumentInline,
        ClaimNoteInline,
        ClaimAuditInline
    ]


# -----------------------------
# Claim Document Admin
# -----------------------------

@admin.register(ClaimDocument)
class ClaimDocumentAdmin(admin.ModelAdmin):

    list_display = (
        "claim",
        "document_type",
        "uploaded_by",
        "uploaded_at",
    )

    list_filter = (
        "document_type",
        "uploaded_at",
    )

    search_fields = (
        "claim__claim_number",
    )


# -----------------------------
# Claim Assessment Admin
# -----------------------------

@admin.register(ClaimAssessment)
class ClaimAssessmentAdmin(admin.ModelAdmin):

    list_display = (
        "claim",
        "verdict",
        "recommended_amount",
        "assessed_by",
        "assessed_on",
    )

    list_filter = (
        "verdict",
        "assessed_on",
    )


# -----------------------------
# Claim Settlement Admin
# -----------------------------

@admin.register(ClaimSettlement)
class ClaimSettlementAdmin(admin.ModelAdmin):

    list_display = (
        "claim",
        "settled_amount",
        "payment_mode",
        "settlement_date",
        "processed_by",
    )

    list_filter = (
        "payment_mode",
        "settlement_date",
    )


# -----------------------------
# Claim Notes Admin
# -----------------------------

@admin.register(ClaimNote)
class ClaimNoteAdmin(admin.ModelAdmin):

    list_display = (
        "claim",
        "note_type",
        "created_by",
        "created_at",
    )

    list_filter = (
        "note_type",
    )


# -----------------------------
# Claim Audit Logs
# -----------------------------

@admin.register(ClaimAuditLog)
class ClaimAuditLogAdmin(admin.ModelAdmin):

    list_display = (
        "claim",
        "action",
        "performed_by",
        "created_at",
    )

    readonly_fields = (
        "claim",
        "action",
        "performed_by",
        "description",
        "created_at",
    )