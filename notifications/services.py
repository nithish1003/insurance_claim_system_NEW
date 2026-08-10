import logging
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.conf import settings
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from twilio.rest import Client

logger = logging.getLogger(__name__)

from datetime import timedelta
from django.utils import timezone

class NotificationService:
    """
    Elite multi-channel dispatch service for ClaimIQ notifications.
    Supports Real-time WebSockets, SMTP Email, Twilio SMS, and Smart Grouping.
    """

    @staticmethod
    def notify_user(notification):
        """
        Main entry point: Dispatches a Notification object with optional Smart Grouping.
        """
        user = notification.user
        prefs, _ = NotificationPreference.objects.get_or_create(user=user)
        
        # 🛡️ 0. SMART GROUPING INTELLIGENCE
        grouped_notification = NotificationService.attempt_grouping(notification)
        target_notification = grouped_notification if grouped_notification else notification

        # 1. Real-time WebSocket Push
        if prefs.realtime_enabled:
            NotificationService.send_push(target_notification)

        # 2. Email Delivery
        if prefs.email_enabled:
            NotificationService.send_email(target_notification)

        # 3. SMS Delivery
        if prefs.sms_enabled and user.phone:
            NotificationService.send_sms(target_notification)

    @staticmethod
    def attempt_grouping(new_notification):
        """
        Checks for similar notifications in the last 24h to merge into a Smart Summary.
        """
        if new_notification.related_claim_id or new_notification.related_payment_id:
            return None

        from .models import Notification
        day_ago = timezone.now() - timedelta(hours=24)
        
        similar_alerts = Notification.objects.filter(
            user=new_notification.user,
            type=new_notification.type,
            title=new_notification.title,
            created_at__gte=day_ago,
            is_cleared=False
        ).exclude(id=new_notification.id)

        if similar_alerts.count() >= 2:
            total_count = similar_alerts.count() + 1
            # Merge into a Smart Summary
            new_notification.message = f"You have {total_count} updates regarding: {new_notification.title}. Visit your dashboard for the full chronological audit."
            new_notification.title = f"Smart Summary: {total_count} {new_notification.get_type_display()} Updates"
            new_notification.save(update_fields=['title', 'message'])
            
            # Optionally "Archive" the old ones to keep the HUD clean
            similar_alerts.update(is_cleared=True)
            return new_notification
        
        return None

    @staticmethod
    def send_push(notification):
        """Pushes JSON payload to user's personal WebSocket room."""
        if notification.delivered_push:
            return
            
        channel_layer = get_channel_layer()
        room_group_name = f"notifications_user_{notification.user.id}"
        
        from .models import Notification
        unread_count = Notification.objects.filter(
            user=notification.user,
            is_read=False,
            is_cleared=False,
        ).count()

        payload = {
            'id': str(notification.id),
            'title': notification.title,
            'message': notification.message,
            'type': notification.type,
            'created_at': notification.created_at.strftime("%Y-%m-%d %H:%M:%S"),
            'unread_count': unread_count,
            'url': f"/notifications/redirect/{notification.id}/"
        }

        try:
            async_to_sync(channel_layer.group_send)(
                room_group_name,
                {
                    "type": "send_notification",
                    "payload": payload
                }
            )
            notification.delivered_push = True
            notification.save(update_fields=['delivered_push'])
        except Exception as e:
            notification.delivery_error = f"Push Error: {str(e)}"
            notification.save(update_fields=['delivery_error'])

    @staticmethod
    def send_email(notification):
        """Sends branded HTML email based on notification content."""
        if notification.delivered_email:
            return
            
        subject = f"ClaimIQ Alert: {notification.title}"
        from_email = settings.DEFAULT_FROM_EMAIL
        to = notification.user.email

        context = {
            'user': notification.user,
            'title': notification.title,
            'message': notification.message,
            'type': notification.type,
            'cta_url': f"{settings.BASE_URL}/notifications/redirect/{notification.id}/"
        }

        try:
            html_content = render_to_string('notifications/emails/base_notification.html', context)
            text_content = strip_tags(html_content)

            msg = EmailMultiAlternatives(subject, text_content, from_email, [to])
            msg.attach_alternative(html_content, "text/html")
            msg.send()
            
            notification.delivered_email = True
            notification.save(update_fields=['delivered_email'])
        except Exception as e:
            notification.delivery_error = f"Email Error: {str(e)}"
            notification.save(update_fields=['delivery_error'])

    @staticmethod
    def send_sms(notification):
        """Dispatches Twilio SMS alert using the dedicated TwilioService."""
        if notification.delivered_sms:
            return
            
        
        from .services.twilio_service import TwilioService
        
        # Format a clean, professional SMS body
        sms_body = f"ClaimIQ: {notification.title}. {notification.message[:100]}... Login for details."
        to_number = notification.user.phone

        if not to_number:
            return

        # 🚀 Dispatch via the modular service layer
        result = TwilioService.send_sms(to_number, sms_body)

        # Update Notification Audit Trail
        if result['status'] == 'delivered' or result['status'] == 'test_ready':
            notification.delivered_sms = True
            # Store the Provider SID if available
            if 'sid' in result:
                notification.delivery_error = f"Twilio SID: {result['sid']} ({result['status']})"
            notification.save(update_fields=['delivered_sms', 'delivery_error'])
        elif result['status'] == 'failed':
            notification.delivery_error = f"SMS Error: {result.get('error_message', 'Unknown failure')}"
            notification.save(update_fields=['delivery_error'])

from .models import NotificationPreference
