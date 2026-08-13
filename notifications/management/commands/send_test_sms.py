"""
Management command to test TextBee SMS delivery.

Usage::

    python manage.py send_test_sms +919876543210
"""

from django.core.management.base import BaseCommand
from notifications.sms_service import TextBeeSMSService


class Command(BaseCommand):
    help = 'Sends a test SMS via TextBee to verify SMS gateway configuration.'

    def add_arguments(self, parser):
        parser.add_argument(
            'phone',
            type=str,
            help='Recipient phone number in E.164 format (e.g. +919876543210)',
        )
        parser.add_argument(
            '--message',
            type=str,
            default=None,
            help='Optional custom message body.',
        )

    def handle(self, *args, **kwargs):
        phone = kwargs['phone']
        message = kwargs.get('message') or (
            "ClaimIQ Test SMS: Your TextBee SMS gateway is configured correctly "
            "and production-ready. This is an automated verification message."
        )

        self.stdout.write(self.style.WARNING(
            f"Sending test SMS to {phone} via TextBee..."
        ))

        success = TextBeeSMSService.send_sms(phone, message)

        if success:
            self.stdout.write(self.style.SUCCESS(
                f"SUCCESS: Test SMS delivered to {phone}"
            ))
        else:
            self.stdout.write(self.style.ERROR(
                f"FAILED: Could not send SMS to {phone}. "
                "Check the logs above for API error details."
            ))
