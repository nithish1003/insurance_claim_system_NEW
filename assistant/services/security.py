import re

def mask_sensitive_data(text):
    """
    Scans and redacts sensitive information such as Aadhaar numbers, 
    credit cards, and payment-related keywords.
    """
    if not text:
        return text

    # Redact Aadhaar Numbers (12 digits)
    # Pattern: 4 digits, space/dash (optional), 4 digits, space/dash (optional), 4 digits
    text = re.sub(r'\b\d{4}[ -]?\d{4}[ -]?\d{4}\b', '[REDACTED AADHAAR]', text)

    # Redact Credit Card / Payment Numbers (typically 13-19 digits)
    text = re.sub(r'\b(?:\d[ -]*?){13,19}\b', '[REDACTED PAYMENT DATA]', text)

    # Redact sensitive keywords (CVV, OTP, PIN)
    sensitive_patterns = [
        (r'\b(?:cvv|cvc|pin|otp)\b\s*[:=-]?\s*\w+', r'[REDACTED SECURITY KEY]')
    ]
    
    for pattern, replacement in sensitive_patterns:
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)

    return text
