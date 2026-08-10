def create_notification(user, title, message, type='info', role_target='policyholder', related_claim_id=None, related_payment_id=None, expires_at=None, **kwargs):
    """
    Enterprise-grade helper to generate system-wide notifications.
    Supports role-based targeting, claim linking, and payment integration.
    Handles legacy keyword arguments for backward compatibility.
    """
    from .models import Notification
    
    # 🔄 Backward Compatibility Mapping
    if 'notification_type' in kwargs and not type:
        type = kwargs['notification_type']
    if 'related_entity_id' in kwargs and not related_claim_id:
        related_claim_id = kwargs['related_entity_id']
        
    return Notification.objects.create(
        user=user,
        title=title,
        message=message,
        type=type,
        role_target=role_target,
        related_claim_id=related_claim_id,
        related_payment_id=related_payment_id,
        expires_at=expires_at
    )
