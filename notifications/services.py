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
    def render_email_template(template_name, context):
        """Renders an HTML template and extracts plain text."""
        html_content = render_to_string(template_name, context)
        text_content = strip_tags(html_content)
        return html_content, text_content

    @staticmethod
    def send_html_email(subject, template_name, context, recipient_list):
        """Reusable helper to send HTML emails using EmailMultiAlternatives."""
        from_email = settings.DEFAULT_FROM_EMAIL
        html_content, text_content = NotificationService.render_email_template(template_name, context)
        
        try:
            msg = EmailMultiAlternatives(subject, text_content, from_email, recipient_list)
            msg.attach_alternative(html_content, "text/html")
            msg.send()
            logger.info(f"Successfully sent email to {recipient_list}")
            return True
        except Exception as e:
            logger.error(f"Failed to send email to {recipient_list}: {str(e)}")
            return False

    @staticmethod
    def send_notification_email(notification):
        """Alias for send_email to meet standard helper requirements."""
        return NotificationService.send_email(notification)

    @staticmethod
    def send_email(notification):
        """Sends branded HTML email based on notification content using smart template routing."""
        if notification.delivered_email:
            return
            
        subject = f"ClaimIQ Alert: {notification.title}"
        context = {
            'user': notification.user,
            'title': notification.title,
            'message': notification.message,
            'type': notification.type,
            'cta_url': f"{settings.BASE_URL}/notifications/redirect/{notification.id}/"
        }
        
        # Resolve related models for template context
        if notification.related_claim_id:
            from claims.models import Claim
            claim = Claim.objects.filter(public_id=notification.related_claim_id).first()
            if claim:
                context['claim'] = claim
                context['claim_url'] = context['cta_url']
                
        if notification.related_payment_id:
            from premiums.models import PremiumPayment
            payment = PremiumPayment.objects.filter(public_id=notification.related_payment_id).first()
            if payment:
                context['payment'] = payment
                context['payment_url'] = context['cta_url']
                if payment.schedule and payment.schedule.user_policy:
                    context['policy'] = payment.schedule.user_policy.policy
                    
        # Policy is sometimes embedded without an explicit related ID (e.g. Policy Activated)
        # We can extract from title or rely on generic message if needed.

        # Smart Template Routing
        template_name = 'notifications/emails/base_notification.html'
        title_lower = notification.title.lower()
        
        if 'welcome' in title_lower or 'registration' in title_lower:
            template_name = 'emails/registration.html'
        elif 'claim submitted' in title_lower:
            template_name = 'emails/claim_submitted.html'
        elif 'claim approved' in title_lower:
            template_name = 'emails/claim_approved.html'
        elif 'claim rejected' in title_lower:
            template_name = 'emails/claim_rejected.html'
        elif 'policy activated' in title_lower or 'policy approved' in title_lower:
            template_name = 'emails/policy_approved.html'
        elif 'premium' in title_lower and ('overdue' in title_lower or 'reminder' in title_lower):
            template_name = 'emails/premium_reminder.html'
        elif 'kyc' in title_lower or 'identity' in title_lower:
            template_name = 'emails/kyc_status.html'
            context['status'] = 'approved' if 'verified' in title_lower else 'rejected'
            context['reason'] = notification.message

        success = NotificationService.send_html_email(
            subject=subject,
            template_name=template_name,
            context=context,
            recipient_list=[notification.user.email]
        )
        
        if success:
            notification.delivered_email = True
            notification.save(update_fields=['delivered_email'])
        else:
            notification.delivery_error = "Email Error: SMTP Delivery Failed"
            notification.save(update_fields=['delivery_error'])

    @staticmethod
    def send_sms(notification):
        """
        Dispatches SMS alert using the TextBee SMS gateway.
        Falls back to Twilio if TextBee is not configured.
        """
        if notification.delivered_sms:
            return

        to_number = notification.user.phone
        if not to_number:
            return

        # Build a concise SMS body from the notification
        sms_body = f"ClaimIQ: {notification.title}. {notification.message[:100]}"
        if len(notification.message) > 100:
            sms_body += "..."
        sms_body += " Login for details."

        # ── Primary: TextBee SMS Gateway ──────────────────────────────────
        from .sms_service import TextBeeSMSService

        if getattr(settings, 'TEXTBEE_API_KEY', ''):
            success = TextBeeSMSService.send_sms(to_number, sms_body)

            if success:
                notification.delivered_sms = True
                notification.delivery_error = "TextBee: Delivered"
                notification.save(update_fields=['delivered_sms', 'delivery_error'])
            else:
                notification.delivery_error = "SMS Error: TextBee delivery failed"
                notification.save(update_fields=['delivery_error'])
            return

        # ── Fallback: Twilio (legacy) ─────────────────────────────────────
        from .services.twilio_service import TwilioService

        result = TwilioService.send_sms(to_number, sms_body)

        if result['status'] in ('delivered', 'test_ready'):
            notification.delivered_sms = True
            if 'sid' in result:
                notification.delivery_error = f"Twilio SID: {result['sid']} ({result['status']})"
            notification.save(update_fields=['delivered_sms', 'delivery_error'])
        elif result['status'] == 'failed':
            notification.delivery_error = f"SMS Error: {result.get('error_message', 'Unknown failure')}"
            notification.save(update_fields=['delivery_error'])

    @staticmethod
    def send_notification(user, title, message, notification_type='info',
                          send_email=True, send_sms=False,
                          related_claim_id=None, related_payment_id=None,
                          sms_template=None, sms_kwargs=None):
        """
        High-level helper to create a Notification and dispatch it
        through the requested channels (email, SMS, or both).

        Args:
            user:               Target user instance.
            title (str):        Notification title.
            message (str):      Notification body.
            notification_type:  One of 'info', 'success', 'warning', 'error'.
            send_email (bool):  Whether to send an HTML email.
            send_sms (bool):    Whether to send an SMS via TextBee.
            related_claim_id:   Optional UUID linking to a Claim.
            related_payment_id: Optional UUID linking to a PremiumPayment.
            sms_template (str): Optional key from SMS_TEMPLATES for a richer SMS body.
            sms_kwargs (dict):  Context dict for sms_template interpolation.

        Returns:
            Notification – The created Notification instance.
        """
        from .models import Notification

        notification = Notification.objects.create(
            user=user,
            title=title,
            message=message,
            type=notification_type,
            related_claim_id=related_claim_id,
            related_payment_id=related_payment_id,
        )

        # ── Email channel ─────────────────────────────────────────────────
        if send_email:
            NotificationService.send_email(notification)

        # ── SMS channel ───────────────────────────────────────────────────
        if send_sms and user.phone:
            # If a specific SMS template is requested, override the body
            if sms_template:
                from .sms_service import TextBeeSMSService, get_sms_text
                sms_body = get_sms_text(sms_template, **(sms_kwargs or {}))
                success = TextBeeSMSService.send_sms(user.phone, sms_body)

                if success:
                    notification.delivered_sms = True
                    notification.delivery_error = "TextBee: Delivered"
                else:
                    notification.delivery_error = "SMS Error: TextBee delivery failed"
                notification.save(update_fields=['delivered_sms', 'delivery_error'])
            else:
                # Use the standard send_sms which builds a generic body
                NotificationService.send_sms(notification)

        return notification

from .models import NotificationPreference

