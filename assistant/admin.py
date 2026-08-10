from django.contrib import admin
from .models import AssistantSession, AssistantMessage, EscalationTicket, AssistantAuditLog

@admin.register(AssistantSession)
class AssistantSessionAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'role_context', 'is_active', 'is_escalated', 'created_at')
    list_filter = ('role_context', 'is_active', 'is_escalated')
    search_fields = ('id', 'user__username')

@admin.register(AssistantMessage)
class AssistantMessageAdmin(admin.ModelAdmin):
    list_display = ('id', 'session', 'sender', 'intent_detected', 'confidence_score', 'feedback_value', 'timestamp')
    list_filter = ('sender', 'intent_detected', 'feedback_value')
    readonly_fields = ('timestamp',)

@admin.register(EscalationTicket)
class EscalationTicketAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'status', 'priority', 'created_at')
    list_filter = ('status', 'priority')
    search_fields = ('user__username', 'transcript_summary')

@admin.register(AssistantAuditLog)
class AssistantAuditLogAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'user', 'role', 'detected_intent', 'response_source', 'response_time_ms', 'success_status')
    list_filter = ('response_source', 'success_status', 'role', 'detected_intent', 'created_at')
    search_fields = ('message_text', 'user__username', 'ip_address')
    readonly_fields = ('created_at', 'user', 'role', 'message_text', 'detected_intent', 'confidence_score', 'response_source', 'response_time_ms', 'ip_address', 'success_status')
    
    def has_add_permission(self, request):
        return False  # Audit logs should only be created by the system

    def has_change_permission(self, request, obj=None):
        return False  # Audit logs should be immutable
