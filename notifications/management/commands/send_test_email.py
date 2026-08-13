from django.core.management.base import BaseCommand
from notifications.services import NotificationService

class Command(BaseCommand):
    help = 'Sends a test email to verify SMTP configuration'

    def add_arguments(self, parser):
        parser.add_argument('email', type=str, help='The recipient email address')

    def handle(self, *args, **kwargs):
        email = kwargs['email']
        
        self.stdout.write(self.style.WARNING(f"Attempting to send test email to {email}..."))
        
        context = {
            'user': type('MockUser', (object,), {'get_full_name': lambda self: 'Test User', 'username': 'test_user'})(),
            'title': 'SMTP Configuration Test',
            'message': 'This is a test email sent from the ClaimIQ management command. If you are reading this, your SMTP configuration is perfectly set up and production-ready!',
            'type': 'success',
            'cta_url': '#'
        }
        
        success = NotificationService.send_html_email(
            subject='ClaimIQ - SMTP Test Successful',
            template_name='notifications/emails/base_notification.html',
            context=context,
            recipient_list=[email]
        )
        
        if success:
            self.stdout.write(self.style.SUCCESS(f"Successfully sent test email to {email}"))
        else:
            self.stdout.write(self.style.ERROR(f"Failed to send test email to {email}. Check logs for details."))
