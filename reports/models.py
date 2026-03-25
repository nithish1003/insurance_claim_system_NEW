from django.db import models
from django.conf import settings
from claims.models import Claim
# from policy.models import Payment # I'll import carefully in views or use dynamic

class ActivityLog(models.Model):
    LOG_TYPE_CHOICES = [
        ('claim', 'Claim'),
        ('payment', 'Payment'),
        ('error', 'Error'),
        ('system', 'System'),
    ]
    
    STATUS_CHOICES = [
        ('success', 'Success'),
        ('warning', 'Warning'),
        ('error', 'Error'),
        ('info', 'Info'),
    ]
    
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    log_type = models.CharField(max_length=20, choices=LOG_TYPE_CHOICES, default='system')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='info')
    
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    claim = models.ForeignKey(Claim, on_delete=models.SET_NULL, null=True, blank=True)
    # Generic object ID or similar could be useful, but let's keep it simple for now
    related_id = models.CharField(max_length=100, blank=True, null=True)
    
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "System Activity Log"
        verbose_name_plural = "System Activity Logs"

    def __str__(self):
        return f"{self.title} - {self.created_at}"
