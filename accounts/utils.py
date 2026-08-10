import re
import logging
import hashlib
from datetime import timedelta
from django.utils import timezone
from django.conf import settings

logger = logging.getLogger(__name__)

def get_client_ip(request):
    """Extracts client IP from request headers."""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0].strip()
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip

def get_session_fingerprint(request):
    """
    Generates a unique fingerprint for the current session requester
    using IP address and User-Agent.
    """
    ip = get_client_ip(request)
    user_agent = request.META.get('HTTP_USER_AGENT', '')
    fingerprint_raw = f"{ip}|{user_agent}"
    return hashlib.sha256(fingerprint_raw.encode()).hexdigest()

def get_valid_pending_kyc(request):
    """
    Retrieves the KYC record if the session token is valid, not expired,
    and matches the current requester fingerprint.
    """
    from .models import AadhaarKYCVerification
    
    pending_id = request.session.get('pending_kyc_id')
    created_at_str = request.session.get('pending_kyc_created_at')
    stored_fingerprint = request.session.get('pending_kyc_fingerprint')

    if not pending_id:
        return None

    # 1. Check Expiry (15 minutes)
    try:
        if not created_at_str:
            raise ValueError("Missing creation timestamp")
        
        created_at = timezone.datetime.fromisoformat(created_at_str)
        if timezone.is_naive(created_at):
            created_at = timezone.make_aware(created_at)
            
        expiry_window = timedelta(minutes=15)
        if timezone.now() > created_at + expiry_window:
            logger.warning(f"Expired pending_kyc_id {pending_id} cleared (Created: {created_at})")
            cleanup_pending_kyc_session(request)
            return None
    except (ValueError, TypeError) as e:
        logger.error(f"Invalid KYC session metadata: {e}")
        cleanup_pending_kyc_session(request)
        return None

    # 2. Security Hardening: Fingerprint Validation
    current_fingerprint = get_session_fingerprint(request)
    if stored_fingerprint and stored_fingerprint != current_fingerprint:
        logger.warning(f"Rejecting pending_kyc_id {pending_id}: Fingerprint mismatch.")
        cleanup_pending_kyc_session(request)
        return None

    # 3. Database Validation
    try:
        record = AadhaarKYCVerification.objects.get(id=pending_id)
        
        # Ensure it's not already linked to a user
        if record.user_id is not None:
            logger.warning(f"Rejecting pending_kyc_id {pending_id}: Already linked to user {record.user_id}.")
            cleanup_pending_kyc_session(request)
            return None
            
        return record
    except AadhaarKYCVerification.DoesNotExist:
        cleanup_pending_kyc_session(request)
        return None

def cleanup_pending_kyc_session(request):
    """Removes KYC related keys from the session."""
    keys_to_clear = [
        "pending_kyc_id", 
        "pending_kyc_created_at", 
        "pending_kyc_fingerprint"
    ]
    for key in keys_to_clear:
        request.session.pop(key, None)


def mask_phone(phone):
    """
    Masks phone number showing only last 4 digits.
    Example: 9626712955 -> XXXXXX2955
    """
    if not phone:
        return "—"
    clean_phone = re.sub(r'\D', '', str(phone))
    if len(clean_phone) < 4:
        return "****"
    return "XXXXXX" + clean_phone[-4:]

def mask_email(email):
    """
    Masks email username.
    Example: nithishneelamegan@gmail.com -> nith****@gmail.com
    """
    if not email or "@" not in email:
        return "—"
    try:
        username, domain = email.split("@")
        if len(username) <= 4:
            return username[0] + "****@" + domain
        return username[:4] + "****@" + domain
    except ValueError:
        return email

def mask_aadhaar(aadhaar):
    """
    Masks Aadhaar number showing only last 4 digits.
    Example: 123412341234 -> XXXX-XXXX-1234
    """
    if not aadhaar:
        return "—"
    clean_aadhaar = re.sub(r'\D', '', str(aadhaar))
    if len(clean_aadhaar) != 12:
        return "Invalid Aadhaar"
    return "XXXX-XXXX-" + clean_aadhaar[-4:]

def log_sensitive_data_access(user, accessed_user, fields):
    """
    Audit log for sensitive data access.
    """
    logger.info(f"AUDIT | User {user.username} (ID: {user.id}) accessed sensitive data of User {accessed_user.username} (ID: {accessed_user.id}). Fields: {', '.join(fields)}")
