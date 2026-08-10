from django.db import models
from django.conf import settings
import uuid

class AssistantSession(models.Model):
    """Stores metadata for a specific chat interaction session."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True)
    role_context = models.CharField(max_length=20, default='customer') # customer, staff, admin
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)
    is_escalated = models.BooleanField(default=False)
    
    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Session {self.id} - {self.user.username if self.user else 'Guest'}"

class AssistantMessage(models.Model):
    """Individual dialogue entries."""
    session = models.ForeignKey(AssistantSession, related_name='messages', on_delete=models.CASCADE)
    sender = models.CharField(max_length=10, choices=[('ai', 'AI Assistant'), ('user', 'User')])
    content = models.TextField()
    intent_detected = models.CharField(max_length=100, null=True, blank=True)
    confidence_score = models.FloatField(default=1.0)  # 0.0 to 1.0
    feedback_value = models.IntegerField(null=True, blank=True, choices=[(1, 'Positive'), (-1, 'Negative')])
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['timestamp']

class EscalationTicket(models.Model):
    # ... as before ...
    session = models.OneToOneField(AssistantSession, on_delete=models.CASCADE)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    status = models.CharField(max_length=20, default='open', choices=[
        ('open', 'Open'), 
        ('in_progress', 'In Progress'), 
        ('resolved', 'Resolved')
    ])
    transcript_summary = models.TextField()
    priority = models.CharField(max_length=10, default='medium')
    created_at = models.DateTimeField(auto_now_add=True)

class SupportTicket(models.Model):
    """Real customer support tickets created via AI Assistant."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    subject = models.CharField(max_length=255)
    category = models.CharField(max_length=100, choices=[
        ('claims', 'Claims help'),
        ('premium', 'Premium/Payments'),
        ('policy', 'Policy Inquiry'),
        ('tech', 'Technical Support'),
        ('other', 'Other')
    ], default='other')
    message = models.TextField()
    priority = models.CharField(max_length=20, default='medium', choices=[
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('urgent', 'Urgent')
    ])
    status = models.CharField(max_length=20, default='open', choices=[
        ('open', 'Open'),
        ('in_progress', 'In Progress'),
        ('resolved', 'Resolved'),
        ('closed', 'Closed')
    ])
    ticket_id = models.CharField(max_length=20, unique=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.ticket_id:
            import random
            num = random.randint(1000, 9999)
            self.ticket_id = f"CIQ-{num}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.ticket_id} - {self.subject}"


class AssistantAuditLog(models.Model):
    """Forensic interactions vault for security and analytics."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    role = models.CharField(max_length=20, default='guest')
    message_text = models.TextField() # Masked
    detected_intent = models.CharField(max_length=100)
    confidence_score = models.FloatField()
    response_source = models.CharField(max_length=50, choices=[
        ('faq', 'Rule Engine'),
        ('db', 'Database Lookup'),
        ('llm', 'Neural Fallback'),
        ('escalation', 'Human Handoff')
    ])
    response_time_ms = models.IntegerField()
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    success_status = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Neural Audit Log"
