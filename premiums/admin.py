from django.contrib import admin
from .models import PremiumSchedule, PremiumPayment


@admin.register(PremiumSchedule)
class PremiumScheduleAdmin(admin.ModelAdmin):
    list_display = (
        "policy",
        "payment_frequency",
        "gross_premium",
        "total_installments",
        "installment_amount",
        "auto_debit_enabled",
        "start_date",
        "end_date",
    )
    list_filter = ("payment_frequency", "auto_debit_enabled")
    search_fields = ("policy__policy_number",)


@admin.register(PremiumPayment)
class PremiumPaymentAdmin(admin.ModelAdmin):
    list_display = (
        "schedule",
        "installment_number",
        "due_date",
        "amount",
        "status",
        "paid_date",
    )
    list_filter = ("status",)
    search_fields = ("schedule__policy__policy_number",)
