"""
TextBee SMS Service for ClaimIQ
================================
Production-grade SMS dispatch using the TextBee API (https://textbee.dev).
Sends messages via an Android device bridge, making it ideal for Indian
mobile numbers without requiring a Twilio sender number.

Configuration is read exclusively from Django settings:
    TEXTBEE_API_KEY   – Bearer token for API authentication
    TEXTBEE_DEVICE_ID – Registered Android device ID
    TEXTBEE_BASE_URL  – API base URL (default: https://api.textbee.dev/api/v1)
"""

import logging
import requests
from django.conf import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# SMS Message Templates
# ---------------------------------------------------------------------------
SMS_TEMPLATES = {
    'welcome': (
        "Welcome to ClaimIQ, {name}! Your account is active. "
        "Explore policies & manage claims at claimiq.in"
    ),
    'password_reset_otp': (
        "ClaimIQ Security: Your password reset OTP is {otp_code}. "
        "Valid for 15 minutes. Do NOT share this code."
    ),
    'claim_submitted': (
        "ClaimIQ: Claim {claim_number} submitted successfully. "
        "Our team is reviewing it. Track status in your dashboard."
    ),
    'claim_approved': (
        "ClaimIQ: Great news! Claim {claim_number} has been APPROVED. "
        "Settlement of Rs.{amount} will be processed shortly."
    ),
    'claim_rejected': (
        "ClaimIQ: Claim {claim_number} has been REJECTED. "
        "Reason: {reason}. Login for details."
    ),
    'premium_reminder': (
        "ClaimIQ Billing: Premium of Rs.{amount} for policy "
        "{policy_number} is due on {due_date}. Pay now to avoid lapse."
    ),
    'kyc_approved': (
        "ClaimIQ: Your identity has been successfully verified. "
        "Your account is now fully active."
    ),
    'kyc_rejected': (
        "ClaimIQ: Identity verification failed. "
        "Please re-upload your documents. Reason: {reason}"
    ),
    'email_verify_otp': (
        "ClaimIQ: Your email verification OTP is {otp_code}. "
        "Valid for 10 minutes. Do NOT share this code."
    ),
    'phone_verify_otp': (
        "ClaimIQ: Your phone verification OTP is {otp_code}. "
        "Valid for 10 minutes. Do NOT share this code."
    ),
}


def get_sms_text(template_key, **kwargs):
    """
    Renders a short SMS body from a named template.
    Unknown keys are silently replaced with empty strings.

    Args:
        template_key: One of the keys in SMS_TEMPLATES.
        **kwargs:     Values to interpolate (e.g. name, otp_code).

    Returns:
        str – The rendered SMS body, or a generic fallback.
    """
    template = SMS_TEMPLATES.get(template_key)
    if not template:
        logger.warning(f"SMS template '{template_key}' not found. Using fallback.")
        return f"ClaimIQ: {kwargs.get('message', 'You have a new notification. Login for details.')}"

    class SafeDict(dict):
        """Returns '' for any missing key so .format_map never raises."""
        def __missing__(self, key):
            return ''

    return template.format_map(SafeDict(**kwargs))


class TextBeeSMSService:
    """
    Stateless service class for dispatching SMS via TextBee API.

    Usage::

        from notifications.services.sms_service import TextBeeSMSService
        success = TextBeeSMSService.send_sms("+919876543210", "Hello!")
    """

    # Timeout for the HTTP request (connect, read) in seconds
    REQUEST_TIMEOUT = (5, 15)

    @staticmethod
    def send_sms(phone_number, message):
        """
        Sends an SMS to the given phone number via TextBee.

        Args:
            phone_number (str): Recipient number in E.164 format (e.g. +919876543210).
            message (str):      The SMS body (max ~160 chars recommended).

        Returns:
            bool: True if the API accepted the message, False otherwise.
        """
        api_key = getattr(settings, 'TEXTBEE_API_KEY', '')
        device_id = getattr(settings, 'TEXTBEE_DEVICE_ID', '')
        base_url = getattr(settings, 'TEXTBEE_BASE_URL', 'https://api.textbee.dev/api/v1')

        # ── Guard: Missing configuration ──────────────────────────────────
        if not api_key or not device_id:
            logger.error(
                "TextBee SMS not configured. "
                "Set TEXTBEE_API_KEY and TEXTBEE_DEVICE_ID in your .env file."
            )
            return False

        if not phone_number:
            logger.warning("SMS dispatch skipped: No phone number provided.")
            return False

        # ── Build request ─────────────────────────────────────────────────
        url = f"{base_url.rstrip('/')}/gateway/devices/{device_id}/sendSMS"
        headers = {
            'x-api-key': api_key,
            'Content-Type': 'application/json',
        }
        payload = {
            'receivers': [phone_number],
            'smsBody': message,
        }

        # ── Dispatch ──────────────────────────────────────────────────────
        try:
            response = requests.post(
                url,
                json=payload,
                headers=headers,
                timeout=TextBeeSMSService.REQUEST_TIMEOUT,
            )

            if response.status_code in (200, 201):
                logger.info(
                    f"TextBee SMS sent to {phone_number} "
                    f"[HTTP {response.status_code}]"
                )
                return True
            else:
                # Log the full response for debugging
                logger.error(
                    f"TextBee SMS failed for {phone_number}: "
                    f"HTTP {response.status_code} – {response.text}"
                )
                return False

        except requests.ConnectionError:
            logger.error(f"TextBee SMS failed: Could not connect to {base_url}")
            return False
        except requests.Timeout:
            logger.error(f"TextBee SMS timed out for {phone_number}")
            return False
        except requests.RequestException as e:
            logger.error(f"TextBee SMS unexpected error for {phone_number}: {e}")
            return False
