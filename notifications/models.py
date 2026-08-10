import uuid
from django.db import models
from django.conf import settings
from django.utils import timezone

class Notification(models.Model):
    TYPE_CHOICES = [
        ('info', 'Information'),
        ('success', 'Success'),
        ('warning', 'Warning'),
        ('error', 'Error'),
    ]

    ROLE_CHOICES = [
        ('admin', 'Administrator'),
        ('staff', 'Staff Auditor'),
        ('policyholder', 'Policyholder'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='notifications')
    title = models.CharField(max_length=255)
    message = models.TextField()
    
    # 🎨 Visual & Logic Categorization
    type = models.CharField(max_length=20, choices=TYPE_CHOICES, default='info')
    role_target = models.CharField(max_length=20, choices=ROLE_CHOICES, default='policyholder')
    
    # 📬 State Management
    is_read = models.BooleanField(default=False, db_index=True)
    is_cleared = models.BooleanField(default=False, db_index=True)
    
    # 🔗 Context Links
    related_claim_id = models.UUIDField(null=True, blank=True, help_text="Reference to a Claim public_id")
    related_payment_id = models.UUIDField(null=True, blank=True, help_text="Reference to a PremiumPayment public_id")
    
    # ⏱️ Temporal Tracking
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    read_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True, db_index=True)

    # 📊 Enterprise Auditing & Analytics
    delivered_email = models.BooleanField(default=False, db_index=True)
    delivered_sms = models.BooleanField(default=False, db_index=True)
    delivered_push = models.BooleanField(default=False, db_index=True)
    delivery_error = models.TextField(null=True, blank=True, help_text="Stores specific error messages from SMTP/Twilio")

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'is_read', 'is_cleared']),
            models.Index(fields=['created_at']),
        ]

    def mark_as_read(self):
        self.is_read = True
        self.read_at = timezone.now()
        self.save(update_fields=['is_read', 'read_at'])

    def clear(self):
        self.is_cleared = True
        self.save(update_fields=['is_cleared'])

    def __str__(self):
        status = "READ" if self.is_read else "UNREAD"
        return f"[{status}] {self.user.username} - {self.title}"


class NotificationPreference(models.Model):
    """
    User-specific governance for multi-channel notification delivery.
    Allows individuals to toggle communication streams (Email, SMS, Real-time).
    """
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='notification_preferences')
    
    # 📡 Channel Toggles
    email_enabled = models.BooleanField(default=True, verbose_name="Email Alerts")
    sms_enabled = models.BooleanField(default=False, verbose_name="SMS Alerts")
    realtime_enabled = models.BooleanField(default=True, verbose_name="In-App Real-time")
    
    # 🎭 Event Categories
    claim_updates = models.BooleanField(default=True, verbose_name="Claim Life-cycle")
    kyc_alerts = models.BooleanField(default=True, verbose_name="Identity Verification")
    payment_reminders = models.BooleanField(default=True, verbose_name="Premium Schedules")
    marketing_updates = models.BooleanField(default=False, verbose_name="Newsletter & Offers")

    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Preferences for {self.user.username}"

    class Meta:
        verbose_name = "Notification Preference"
        verbose_name_plural = "Notification Preferences"

# 🚀 AUTO-PROVISIONING SIGNAL
from django.db.models.signals import post_save
from django.dispatch import receiver

@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_user_notification_preferences(sender, instance, created, **kwargs):
    """Ensures every new user has a preference profile on creation."""
    if created:
        NotificationPreference.objects.get_or_create(user=instance)
