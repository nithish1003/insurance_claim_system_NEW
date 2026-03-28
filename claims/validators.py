from django.core.validators import RegexValidator, MinValueValidator, ValidationError
import re

# 🛡️ AI GOVERNANCE: Input Validation Standards (Refactored for Centralized Use)

class AadhaarValidator(RegexValidator):
    regex = r'^\d{12}$'
    message = "Aadhaar must be exactly 12 numeric digits."

class VehicleNumberValidator(RegexValidator):
    # Standard Indian Vehicle Format: XX 00 XX 0000 (with some variations in parts)
    # This regex is a bit more robust: [A-Z]{2}[0-9]{1,2}[A-Z]{1,2}[0-9]{4}
    regex = r'^[A-Z]{2}[0-9]{1,2}[A-Z]{1,3}[0-9]{4}$'
    message = "Invalid format. Expected like 'MH12AB1234' (Standard Indian Vehicle Format)."

VEHICLE_NUMBER_VALIDATOR = VehicleNumberValidator()

class PositiveAmountValidator(MinValueValidator):
    def __init__(self, *args, **kwargs):
        super().__init__(0, message="Amount must be a positive value.")

NON_NEGATIVE_VALIDATOR = PositiveAmountValidator()

def validate_positive_amount(value):
    if value is not None and value <= 0:
        raise ValidationError("Amount must be a positive value.")

def validate_aadhaar_number(value):
    if not value or not re.match(r'^\d{12}$', str(value)):
        raise ValidationError("Aadhaar must be exactly 12 numeric digits.")

def validate_vehicle_number(value):
    if not value or not re.match(r'^[A-Z]{2}[0-9]{1,2}[A-Z]{1,3}[0-9]{4}$', str(value)):
        raise ValidationError("Invalid vehicle number format. Expected format: MH12AB1234.")

# Garbage Data Prevention Utility
def clean_and_validate_ocr_data(data: dict) -> dict:
    """
    🛡️ Governance: Ensures garbage data extracted via OCR doesn't enter the AI pipeline.
    """
    cleaned = {
        'total_amount': 0.0,
        'patient_name': data.get('patient_name'),
        'aadhaar_number': None,
        'vehicle_number': None,
        'is_valid': True,
        'reason': []
    }

    # 1. Total Amount Validation
    raw_amount = data.get('total_amount', 0.0)
    try:
        val = float(raw_amount)
        if val <= 0:
            cleaned['is_valid'] = False
            cleaned['reason'].append("Extracted amount is non-positive.")
        else:
            cleaned['total_amount'] = val
    except (ValueError, TypeError):
        cleaned['is_valid'] = False
        cleaned['reason'].append("Extracted amount is not a valid number.")

    # 2. Aadhaar Validation (if present)
    if 'aadhaar_number' in data and data['aadhaar_number']:
        val = str(data['aadhaar_number']).replace(" ", "").replace("-", "")
        if not re.match(r'^\d{12}$', val):
            cleaned['is_valid'] = False
            cleaned['reason'].append("Extracted Aadhaar number is invalid.")
        else:
            cleaned['aadhaar_number'] = val

    # 3. Vehicle Number Validation (if present)
    if 'vehicle_number' in data and data['vehicle_number']:
        val = str(data['vehicle_number']).upper().replace(" ", "").replace("-", "")
        if not re.match(r'^[A-Z]{2}[0-9]{1,2}[A-Z]{1,3}[0-9]{4}$', val):
            cleaned['is_valid'] = False
            cleaned['reason'].append("Extracted vehicle number is invalid.")
        else:
            cleaned['vehicle_number'] = val

    return cleaned
