from django.db import models
from django.contrib.auth.models import AbstractUser
from django.core.validators import RegexValidator, MinLengthValidator


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

    def __str__(self):
        return f"{self.username} [{self.role.upper()}]"

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


    @property
    def full_name(self):
        """Returns full name from profile or falls back to first/last name or username."""
        if hasattr(self, 'profile') and self.profile.full_name:
            return self.profile.full_name
        
        fname = self.get_full_name()
        if fname:
            return fname
            
        return self.username

    @property
    def aadhaar_masked(self):
        """Returns masked Aadhaar from profile or 'MISSING' if no profile exists."""
        if hasattr(self, 'profile'):
            return self.profile.masked_aadhaar
        return "MISSING"


class UserProfile(models.Model):
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

    @property
    def masked_aadhaar(self):
        """Returns Aadhaar in format XXXX-XXXX-1234"""
        if self.aadhaar_number and len(self.aadhaar_number) == 12:
            return f"XXXX-XXXX-{self.aadhaar_number[-4:]}"
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
