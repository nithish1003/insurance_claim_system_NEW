import random
import hashlib
import hmac
import string
import logging
from datetime import timedelta
from django.utils import timezone
from django.contrib.auth.hashers import make_password, check_password
from .models import OTPVerification

logger = logging.getLogger(__name__)

class OTPService:
    OTP_LENGTH = 6
    OTP_EXPIRY_MINUTES = 10
    MAX_ATTEMPTS = 5

    @staticmethod
    def hash_otp(otp: str) -> str:
        return make_password(otp)

    @staticmethod
    def verify_hashed_otp(raw_otp: str, stored_hash: str) -> bool:
        if stored_hash.startswith('pbkdf2_') or stored_hash.startswith('argon2'):
            return check_password(raw_otp, stored_hash)
        else:
            calculated = hashlib.sha256(raw_otp.encode()).hexdigest()
            return hmac.compare_digest(calculated, stored_hash)

    @staticmethod
    def generate_otp() -> str:
        """Generates a secure numeric OTP."""
        return ''.join(random.choices(string.digits, k=OTPService.OTP_LENGTH))

    @staticmethod
    def _create_otp(email, phone, purpose, session_key, ip_address=None, user_agent='') -> OTPVerification:
        """Core method to create and save a new OTP instance."""

        # Invalidate any previous pending OTPs for this session/purpose
        OTPVerification.objects.filter(
            session_key=session_key,
            purpose=purpose,
            is_verified=False
        ).update(expires_at=timezone.now())

        otp_code_plain = OTPService.generate_otp()
        otp_code_hashed = OTPService.hash_otp(otp_code_plain)
        expires_at = timezone.now() + timedelta(minutes=OTPService.OTP_EXPIRY_MINUTES)
        
        otp_obj = OTPVerification.objects.create(
            email=email,
            phone=phone,
            otp_code=otp_code_hashed,
            purpose=purpose,
            session_key=session_key,
            ip_address=ip_address,
            user_agent=user_agent,
            expires_at=expires_at
        )
        logger.info("OTP Generated")
        return otp_obj, otp_code_plain

    @staticmethod
    def send_email_otp(email, session_key, ip_address=None, user_agent='') -> bool:
        """Generates and sends an OTP via Email."""
        try:
            otp_obj, plain_otp = OTPService._create_otp(email=email, phone="", purpose='email_verify', session_key=session_key, ip_address=ip_address, user_agent=user_agent)
            
            from notifications.services import NotificationService
            success = NotificationService.send_html_email(
                subject="ClaimIQ Email Verification",
                template_name="emails/email_verification_otp.html",
                context={'otp_code': plain_otp},
                recipient_list=[email]
            )
            logger.info("Email OTP Sent")
            return success
        except Exception as e:
            logger.error(f"Error sending email OTP to {email}: {e}")
            return False

    @staticmethod
    def send_sms_otp(phone, session_key, ip_address=None, user_agent='') -> bool:
        """Generates and sends an OTP via SMS."""
        try:
            otp_obj, plain_otp = OTPService._create_otp(email="", phone=phone, purpose='phone_verify', session_key=session_key, ip_address=ip_address, user_agent=user_agent)
            
            from notifications.sms_service import TextBeeSMSService, get_sms_text
            sms_body = get_sms_text('phone_verify_otp', otp_code=plain_otp)
            
            success = TextBeeSMSService.send_sms(phone, sms_body)
            logger.info("SMS OTP Sent")
            return success
        except Exception as e:
            logger.error(f"Error sending SMS OTP to {phone}: {e}")
            return False

    @staticmethod
    def verify_otp(identifier, otp_code, purpose, session_key) -> tuple[bool, str]:
        """
        Verifies an OTP code.
        Returns: (success_boolean, error_message)
        """
        try:
            otp_obj = OTPVerification.objects.filter(
                session_key=session_key,
                purpose=purpose,
                is_verified=False
            ).order_by('-created_at').first()

            if not otp_obj:
                return False, "No pending OTP found. Please request a new one."

            if purpose == 'email_verify' and otp_obj.email != identifier:
                return False, "Email address mismatch."
            if purpose == 'phone_verify' and otp_obj.phone != identifier:
                return False, "Phone number mismatch."

            if timezone.now() > otp_obj.expires_at:
                logger.info("OTP Expired")
                return False, "OTP has expired. Please request a new one."

            if otp_obj.attempts >= OTPService.MAX_ATTEMPTS:
                logger.warning("OTP Locked")
                return False, "Maximum attempts reached. Please request a new OTP."

            if otp_obj.otp_code.startswith('pbkdf2_') or otp_obj.otp_code.startswith('argon2'):
                is_match = check_password(otp_code, otp_obj.otp_code)
            elif len(otp_obj.otp_code) == 64:
                calculated = hashlib.sha256(otp_code.encode()).hexdigest()
                is_match = hmac.compare_digest(calculated, otp_obj.otp_code)
            else:
                is_match = hmac.compare_digest(otp_obj.otp_code, otp_code)

            if not is_match:
                otp_obj.attempts += 1
                otp_obj.save(update_fields=['attempts'])
                logger.info("OTP Failed")
                
                if otp_obj.attempts >= OTPService.MAX_ATTEMPTS:
                    logger.warning("OTP Locked")
                    return False, "Maximum attempts reached. Please request a new OTP."
                    
                remaining = OTPService.MAX_ATTEMPTS - otp_obj.attempts
                return False, f"Invalid OTP code. {remaining} attempts remaining."

            logger.info("OTP Verified")
            otp_obj.delete()
            return True, ""

        except Exception as e:
            logger.error(f"Error verifying OTP: {e}")
            return False, "A system error occurred while verifying the OTP."
