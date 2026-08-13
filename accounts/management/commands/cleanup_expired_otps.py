from django.core.management.base import BaseCommand
from django.utils import timezone
from accounts.models import OTPVerification

class Command(BaseCommand):
    help = 'Cleans up expired OTP records from the database.'

    def handle(self, *args, **kwargs):
        deleted_count, _ = OTPVerification.objects.filter(
            expires_at__lt=timezone.now()
        ).delete()
        
        self.stdout.write(
            self.style.SUCCESS(f'Deleted {deleted_count} expired OTP records.')
        )
