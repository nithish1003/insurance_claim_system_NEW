from django.db import models
from policy.models import Policy


class PremiumSchedule(models.Model):

    PAYMENT_FREQUENCY = [
        ("monthly", "Monthly"),
        ("quarterly", "Quarterly"),
        ("yearly", "Yearly"),
    ]

    user_policy = models.OneToOneField(
        'policy.UserPolicy',
        on_delete=models.CASCADE,
        related_name="premium_schedule",
        null=True, blank=True
    )

    # Keep original policy link as fallback or for template retro-compatibility
    policy = models.ForeignKey(
        'policy.Policy',
        on_delete=models.SET_NULL,
        related_name="premium_schedules",
        null=True, blank=True
    )

    base_premium = models.DecimalField(max_digits=12, decimal_places=2)
    gst_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    gst_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    gross_premium = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    payment_frequency = models.CharField(
        max_length=20,
        choices=PAYMENT_FREQUENCY
    )

    total_installments = models.PositiveIntegerField(default=1)
    installment_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    auto_debit_enabled = models.BooleanField(default=False)
    grace_period_days = models.PositiveIntegerField(default=15)

    start_date = models.DateField()
    end_date = models.DateField()

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        ident = self.user_policy.certificate_number if self.user_policy else self.policy.policy_number
        return f"{ident} - {self.payment_frequency}"


class PremiumPayment(models.Model):

    STATUS = [
        ("upcoming", "Upcoming"),
        ("paid",     "Paid"),
        ("overdue",  "Overdue"),
        ("lapsed",   "Lapsed"),
    ]

    schedule = models.ForeignKey(
        PremiumSchedule,
        on_delete=models.CASCADE,
        related_name="payments"
    )

    installment_number = models.PositiveIntegerField()
    due_date = models.DateField()
    amount = models.DecimalField(max_digits=12, decimal_places=2)

    paid_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS, default="upcoming")

    transaction_reference = models.CharField(max_length=120, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["due_date", "installment_number"]
        unique_together = ("schedule", "installment_number")

    def __str__(self) -> str:
        return f"{self.schedule.policy.policy_number} - #{self.installment_number}"
