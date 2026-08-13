from django.db import models
from django.contrib.auth.models import AbstractUser
from django.core.validators import RegexValidator, MinLengthValidator
import uuid as uuid_lib


class User(AbstractUser):

    ROLE_CHOICES = (
        ('admin', 'Admin'),
        ('staff', 'Staff'),
        ('user',  'User'),
    )

    role    = models.CharField(
        max_length=20, 
        choices=ROLE_CHOICES, 
        default='user',
        db_index=True,
        help_text="System-assigned role for RBAC enforcement."
    )
    phone   = models.CharField(max_length=15, blank=True)
    address = models.TextField(blank=True)

    # 💳 Aadhaar Identity Fields (Directly in User model for centralized KYC)
    aadhaar_number = models.CharField(
        max_length=12, 
        blank=True, 
        null=True,
        validators=[
            MinLengthValidator(12),
            RegexValidator(r'^\d{12}$', 'Aadhaar must be exactly 12 numeric digits.')
        ],
        help_text="12-digit numeric Aadhaar number."
    )
    id_proof = models.FileField(
        upload_to='id_proofs/', 
        blank=True, 
        null=True,
        help_text="Official document for identity validation."
    )
    is_verified = models.BooleanField(
        default=False,
        help_text="Indicates if the identity has been officially vetted."
    )
    verified_at = models.DateTimeField(
        null=True, 
        blank=True,
        help_text="The timestamp when verification was completed."
    )

    def __str__(self):
        return f"{self.username} [{self.role.upper()}]"

    def get_masked_aadhaar(self):
        """Returns Aadhaar in format XXXX-XXXX-1234"""
        val = self.aadhaar_number
        if not val and hasattr(self, 'profile'):
            val = self.profile.aadhaar_number
        if val and len(val) == 12:
            return f"XXXX-XXXX-{val[-4:]}"
        return self.aadhaar_number or "NOT PROVIDED"

    # ── SECURITY ENFORCEMENT ──────────────────────────────────────────
    
    def save(self, *args, **kwargs):
        """
        Hardened persistence hook: Synchronizes Django flags with the 'role' field.
        Ensures bidirectional integrity (Flags <=> Role) for proper dashboard routing.
        """
        # 🛡️ 1. IDENTITY SYNC: Priority to Superuser/Staff flags for management tools compatibility
        if self.is_superuser:
            self.role = 'admin'
            self.is_staff = True    # Admin must always be staff
        elif self.is_staff and self.role != 'admin':
            self.role = 'staff'
            self.is_superuser = False
        elif self.role == 'admin':
            self.is_staff = True
            self.is_superuser = True
        elif self.role == 'staff':
            self.is_staff = True
            self.is_superuser = False
        else:
            # Default to User for any other state
            self.role = 'user'
            self.is_staff = False
            self.is_superuser = False
            
        # 🛡️ 2. DATA SANITIZATION: Normalize Aadhaar format
        if self.aadhaar_number:
            self.aadhaar_number = self.aadhaar_number.replace(" ", "").replace("-", "")
            
        super().save(*args, **kwargs)


    @property
    def is_admin(self):
        return self.role == 'admin'

    @property
    def is_staff_member(self):
        return self.role == 'staff'

    @property
    def is_user(self):
        return self.role == 'user'

    @property
    def dashboard_url(self):
        """
        Centralized routing logic: Prioritizes Django permissions flags to ensure
        unfailing redirection for Admins and Staff members.
        """
        if self.is_superuser:
            return 'accounts:admin_dashboard'
        
        if self.is_staff:
            return 'accounts:staff_dashboard'

        mapping = {
            'admin':        'accounts:admin_dashboard',
            'staff':        'accounts:staff_dashboard',
            'user':         'accounts:policyholder_dashboard',
        }
        return mapping.get(self.role, 'accounts:policyholder_dashboard')


    full_name = models.CharField(
        max_length=255, 
        blank=True, 
        null=True,
        help_text="Full legal name as per identity documents."
    )

    @property
    def full_name_display(self):
        """Returns the full name from the model field or falls back to standard fields."""
        if self.full_name:
            return self.full_name
        
        if hasattr(self, 'profile') and self.profile.full_name:
            return self.profile.full_name
        
        fname = self.get_full_name()
        if fname:
            return fname
            
        return self.username

    @property
    def id_proof_url(self):
        """Safely returns the URL of the ID proof from User or Profile."""
        if self.id_proof:
            try:
                return self.id_proof.url
            except ValueError:
                pass
        
        if hasattr(self, 'profile') and self.profile.id_proof:
            try:
                return self.profile.id_proof.url
            except ValueError:
                pass
        return None

    @property
    def identity_verified(self):
        """True if User or Profile is verified."""
        if self.is_verified:
            return True
        if hasattr(self, 'profile'):
            return self.profile.is_verified or self.profile.verification_status == 'VERIFIED'
        return False
        
        fname = self.get_full_name()
        if fname:
            return fname
            
        return self.username

    @property
    def get_full_name_clean(self):
        """Standard Django compatibility."""
        return self.full_name_display

    @property
    def aadhaar_masked(self):
        """Returns the masked Aadhaar number for security."""
        return self.get_masked_aadhaar()


class UserProfile(models.Model):
    public_id = models.UUIDField(default=uuid_lib.uuid4, unique=True, editable=False, db_index=True)
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    full_name = models.CharField(max_length=255)
    
    # 💳 Aadhaar Validation: 12 numeric digits
    aadhaar_number = models.CharField(
        max_length=12, 
        unique=True,
        validators=[
            MinLengthValidator(12),
            RegexValidator(r'^\d{12}$', 'Aadhaar must be exactly 12 numeric digits.')
        ]
    )
    
    id_proof = models.FileField(upload_to='id_proofs/')
    VERIFICATION_STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('VERIFIED', 'Verified'),
        ('MISMATCH', 'Mismatch'),
    ]

    is_verified = models.BooleanField(default=False)
    verification_status = models.CharField(
        max_length=20,
        choices=VERIFICATION_STATUS_CHOICES,
        default='PENDING',
        help_text="State machine for identity auditing."
    )
    created_at = models.DateTimeField(auto_now_add=True)


    def __str__(self):
        return f"Profile of {self.user.username}"

    def save(self, *args, **kwargs):
        # 🛡️ DATA SANITIZATION: Normalize Aadhaar format for humans
        if self.aadhaar_number:
            self.aadhaar_number = str(self.aadhaar_number).replace(" ", "").replace("-", "")
        super().save(*args, **kwargs)

    @property
    def masked_aadhaar(self):
        """Returns Aadhaar in format XXXX-XXXX-1234"""
        val = self.aadhaar_number
        if not val and hasattr(self, 'profile'):
            val = self.profile.aadhaar_number
        if val and len(val) == 12:
            return f"XXXX-XXXX-{val[-4:]}"
        return self.aadhaar_number


class PasswordResetAttempt(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    email = models.EmailField()
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=(
        ('requested', 'Requested'),
        ('sent', 'Email Sent'),
        ('invalid_email', 'Invalid Email'),
        ('failed', 'Failed'),
    ), default='requested')
    created_at = models.DateTimeField(auto_now_add=True)
    token_used = models.BooleanField(default=False)

    def __str__(self):
        return f"Reset attempt for {self.email} at {self.created_at}"


class AadhaarKYCVerification(models.Model):
    STATUS_CHOICES = [
        ("verified", "Verified"),
        ("manual_review", "Manual Review"),
        ("rejected", "Rejected"),
        ("approved_override", "Approved by Admin"),
        ("rejected_override", "Rejected by Admin"),
        ("escalated", "Escalated to Manual Review"),
    ]

    public_id = models.UUIDField(default=uuid_lib.uuid4, unique=True, editable=False, db_index=True)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="kyc_verifications")
    profile = models.ForeignKey(UserProfile, on_delete=models.SET_NULL, null=True, blank=True, related_name="kyc_verifications")
    submitted_full_name = models.CharField(max_length=255, blank=True)
    submitted_aadhaar_number = models.CharField(max_length=12, blank=True)
    extracted_name = models.CharField(max_length=255, blank=True)
    extracted_number = models.CharField(max_length=12, blank=True)
    source_document_name = models.CharField(max_length=255, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="manual_review")
    details = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    verified_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Aadhaar KYC Verification"
        verbose_name_plural = "Aadhaar KYC Verifications"

    def __str__(self):
        target = self.user.username if self.user else self.submitted_full_name or "KYC Attempt"
        return f"{target} [{self.public_id}]"


class OTPVerification(models.Model):
    PURPOSE_CHOICES = [
        ('email_verify', 'Email Verification'),
        ('phone_verify', 'Phone Verification'),
    ]
    
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=15, blank=True)
    otp_code = models.CharField(max_length=128)
    purpose = models.CharField(max_length=20, choices=PURPOSE_CHOICES)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    is_verified = models.BooleanField(default=False)
    verified_at = models.DateTimeField(null=True, blank=True)
    attempts = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    session_key = models.CharField(max_length=64, db_index=True)

    def __str__(self):
        return f"{self.purpose} OTP for {self.email or self.phone} ({'Verified' if self.is_verified else 'Pending'})"
