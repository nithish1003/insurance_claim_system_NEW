import re
import logging

logger = logging.getLogger(__name__)

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

def log_sensitive_data_access(user, accessed_user, fields):
    """
    Audit log for sensitive data access.
    """
    logger.info(f"AUDIT | User {user.username} (ID: {user.id}) accessed sensitive data of User {accessed_user.username} (ID: {accessed_user.id}). Fields: {', '.join(fields)}")
