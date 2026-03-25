from django.db import models
from django.contrib.auth.models import AbstractUser
from django.core.validators import RegexValidator, MinLengthValidator


class User(AbstractUser):

    ROLE_CHOICES = (
        ('admin', 'Admin'),
        ('staff', 'Staff'),
        ('policyholder', 'Policyholder'),
    )

    role    = models.CharField(max_length=20, choices=ROLE_CHOICES, default='policyholder')
    phone   = models.CharField(max_length=15, blank=True)
    address = models.TextField(blank=True)

    def __str__(self):
        return f"{self.username} ({self.get_role_display()})"

    # ── Convenience helpers ──────────────────────────────────────────
    @property
    def is_admin(self):
        return self.role == 'admin'

    @property
    def is_staff_member(self):
        return self.role == 'staff'

    @property
    def is_policyholder(self):
        return self.role == 'policyholder'

    @property
    def dashboard_url(self):
        """Return the correct dashboard URL name for this user's role."""
        mapping = {
            'admin':        'admin_dashboard',
            'staff':        'staff_dashboard',
            'policyholder': 'policyholder_dashboard',
        }
        return mapping.get(self.role, 'policyholder_dashboard')

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
    is_verified = models.BooleanField(default=False)
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
