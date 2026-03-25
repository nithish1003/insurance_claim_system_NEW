from decimal import Decimal
from django.db import models
from django.conf import settings


# ------------------------------
# User Profile
# ------------------------------


class UserProfile(models.Model):

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE
    )

    phone = models.CharField(max_length=15, blank=True, default="")
    address = models.TextField(blank=True, default="")

    city = models.CharField(max_length=100, blank=True, default="")
    state = models.CharField(max_length=100, blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.user.username

    class Meta:
        db_table = "policy_userprofile"
        verbose_name_plural = "User Profiles"


# ------------------------------
# Policy Holder (Join Table)
# ------------------------------


class PolicyHolder(models.Model):

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="policy_purchases"
    )

    policy = models.ForeignKey(
        "Policy",
        on_delete=models.CASCADE,
        related_name="purchases"
    )

    purchased_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} - {self.policy.policy_number}"

    class Meta:
        db_table = "policy_policyholder"
        verbose_name_plural = "Policy Purchases"
        constraints = [
            models.UniqueConstraint(
                fields=["user", "policy"],
                name="unique_user_policy_purchase"
            )
        ]


# ------------------------------
# User Policy  (Approved policy ownership — NO duplicate Policy creation)
# ------------------------------


class UserPolicy(models.Model):
    """
    Represents an approved policy owned by a user.
    Links a User to an existing admin-created Policy plan.
    A unique certificate number is generated for identification.
    NO new Policy record is created — only this join record.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='owned_policies'
    )

    policy = models.ForeignKey(
        'Policy',
        on_delete=models.CASCADE,
        related_name='user_policies'
    )

    # Unique certificate number for this user's coverage (e.g. CERT-XXXXXX)
    certificate_number = models.CharField(
        max_length=30,
        unique=True,
        help_text='Auto-generated unique certificate number for this user\'s coverage'
    )

    status = models.CharField(
        max_length=20,
        default='active',
        choices=[
            ('active',    'Active'),
            ('grace',     'Grace Period'),
            ('lapsed',    'Lapsed'),
            ('expired',   'Expired'),
            ('cancelled', 'Cancelled'),
        ]
    )

    assigned_at = models.DateTimeField(auto_now_add=True)

    # Coverage period (set at approval time)
    start_date = models.DateField(null=True, blank=True)
    end_date   = models.DateField(null=True, blank=True)

    # Motor-specific fields (copied from application if applicable)
    vehicle_number = models.CharField(max_length=20, blank=True, null=True)
    rc_upload      = models.FileField(upload_to='userpolicy_rc/', blank=True, null=True)

    def sync_status_with_premiums(self):
        """Logic to maintain policy status based on financial health."""
        if self.status in ['expired', 'cancelled']:
            return self.status

        # 🛡️ Coverage Exhaustion Priority Check:
        # If the sum insured is 100% used, the policy is essentially dead for claims.
        if self.remaining_sum_insured <= 0:
            self.status = 'expired'
            self.save(update_fields=['status'])
            return self.status

        # Access the linked schedule
        schedule = getattr(self, 'premium_schedule', None)
        if not schedule:
            return self.status

        from django.utils import timezone
        from datetime import timedelta
        
        today = timezone.now().date()
        grace_period = schedule.grace_period_days
        
        # Get all outstanding installments
        overdue_payments = schedule.payments.exclude(status='paid').filter(due_date__lt=today)
        
        # 🟥 Lapsed Check: Any payment past due + grace period
        if any(p.due_date + timedelta(days=grace_period) < today for p in overdue_payments):
            self.status = 'lapsed'
        # 🟨 Grace Period Check: Any payment past due but within grace
        elif overdue_payments.exists():
            self.status = 'grace'
        # 🟩 Active Check
        else:
            self.status = 'active'
        
        self.save(update_fields=['status'])
        return self.status

    @property
    def total_settled_amount(self):
        """Returns total amount paid out for claims under this user's policy instantiation."""
        from claims.models import Claim
        from django.db.models import Sum, Q
        from decimal import Decimal
        
        # Heuristic to find claims belonging to this specific user instantiation
        claims_qs = Claim.objects.filter(policy=self.policy, status='settled')
        
        if self.vehicle_number:
            # For motor, must match vehicle OR be created by user
            claims_qs = claims_qs.filter(
                Q(vehicle_number=self.vehicle_number) | Q(created_by=self.user)
            )
        else:
            # Fallback for non-motor: assume it's this user if they are the owner
            # (In a multi-user plan, this remains a challenge without a direct FK)
            claims_qs = claims_qs.filter(created_by=self.user)
            
        result = claims_qs.aggregate(total=Sum('settled_amount'))
        return result['total'] or Decimal('0.00')

    @property
    def remaining_sum_insured(self):
        """Returns how much money is left for future claims."""
        from decimal import Decimal
        return max(Decimal('0.00'), self.policy.sum_insured - self.total_settled_amount)

    @property
    def coverage_usage_percentage(self):
        """Returns what percentage of the sum insured has been exhausted."""
        if not self.policy.sum_insured or self.policy.sum_insured == 0:
            return 0
        usage = (self.total_settled_amount / self.policy.sum_insured) * 100
        return float(usage)

    def __str__(self):
        return f"{self.certificate_number} — {self.user.username} | {self.policy.policy_number}"

    class Meta:
        db_table = 'policy_userpolicy'
        verbose_name = 'User Policy'
        verbose_name_plural = 'User Policies'
        ordering = ['-assigned_at']
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'policy'],
                name='unique_user_policy_ownership'
            )
        ]


# ------------------------------
# Payment Model
# ------------------------------


class Payment(models.Model):
    """
    Records payment transactions for policy purchases and renewals.
    Links to UserPolicy for tracking payments against specific user policies.
    """
    
    PAYMENT_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('refunded', 'Refunded'),
        ('cancelled', 'Cancelled'),
    ]
    
    PAYMENT_METHOD_CHOICES = [
        ('credit_card', 'Credit Card'),
        ('debit_card', 'Debit Card'),
        ('net_banking', 'Net Banking'),
        ('upi', 'UPI'),
        ('wallet', 'Digital Wallet'),
        ('cash', 'Cash'),
        ('cheque', 'Cheque'),
        ('neft', 'NEFT/RTGS'),
    ]

    DIRECTION_CHOICES = [
        ('CREDIT', 'Credit (Inflow/Premium)'),
        ('DEBIT',  'Debit (Outflow/Settlement)'),
    ]

    # Links to the user policy this payment is for
    user_policy = models.ForeignKey(
        UserPolicy,
        on_delete=models.CASCADE,
        related_name='payments'
    )

    # 🔗 Link to claim (only for claim settlement payouts)
    claim = models.ForeignKey(
        'claims.Claim',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="payments"
    )

    # Payment details
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        help_text="Total amount paid including taxes"
    )
    
    payment_status = models.CharField(
        max_length=20,
        choices=PAYMENT_STATUS_CHOICES,
        default='pending'
    )
    
    payment_method = models.CharField(
        max_length=20,
        choices=PAYMENT_METHOD_CHOICES,
        default='credit_card'
    )

    # Transaction type to distinguish premiums from claim payouts
    PAYMENT_TYPE_CHOICES = [
        ('PREMIUM_PAYMENT', 'Premium Payment'),
        ('CLAIM_SETTLEMENT', 'Claim Settlement'),
    ]
    payment_type = models.CharField(
        max_length=20,
        choices=PAYMENT_TYPE_CHOICES,
        default='PREMIUM_PAYMENT',
        verbose_name="Transaction Title"
    )

    direction = models.CharField(
        max_length=10,
        choices=DIRECTION_CHOICES,
        default='CREDIT',
        help_text="CREDIT for premiums, DEBIT for claim payouts"
    )

    # Transaction tracking
    transaction_id = models.CharField(
        max_length=100,
        unique=True,
        help_text="Unique transaction identifier from payment gateway"
    )
    
    gateway_reference = models.CharField(
        max_length=200,
        blank=True,
        help_text="Reference ID from payment gateway"
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    # Additional details
    description = models.TextField(
        blank=True,
        help_text="Description of the payment (e.g., 'Policy Premium - Annual')"
    )
    
    notes = models.TextField(
        blank=True,
        help_text="Internal notes about the payment"
    )

    # Metadata for tracking
    payment_metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="Additional payment metadata (gateway response, etc.)"
    )

    def __str__(self):
        return f"Payment {self.transaction_id} - {self.user_policy.certificate_number} - ₹{self.amount}"

    class Meta:
        db_table = 'policy_payment'
        verbose_name = 'Payment'
        verbose_name_plural = 'Payments'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['transaction_id']),
            models.Index(fields=['payment_status']),
            models.Index(fields=['created_at']),
        ]

    def save(self, *args, **kwargs):
        # Generate transaction ID if not provided
        if not self.transaction_id:
            self.transaction_id = self._generate_transaction_id()
        
        # 🔗 Financial Consistency: Synchronize transaction amount with settled claim amount
        if self.payment_type == 'CLAIM_SETTLEMENT' and self.claim:
            # Mandate: Use settled_amount as the source of truth for the ledger
            self.amount = self.claim.settled_amount or Decimal('0.00')

        if self.payment_status == 'completed' and not self.completed_at:
            from django.utils import timezone
            self.completed_at = timezone.now()
        
        super().save(*args, **kwargs)

    def _generate_transaction_id(self):
        """Generate a unique transaction ID based on type"""
        import uuid
        from django.utils import timezone
        
        prefix = "TXN-GEN" # Generic fallback
        if self.payment_type == 'PREMIUM_PAYMENT':
            prefix = "TXN-PREM"
        elif self.payment_type == 'CLAIM_SETTLEMENT':
            prefix = "TXN-SETL"
            
        timestamp = timezone.now().strftime('%Y%m%d%H%M%S')
        unique_suffix = uuid.uuid4().hex[:6].upper()
        
        return f"{prefix}-{timestamp}-{unique_suffix}"


# ------------------------------
# Categories & Insurers
# ------------------------------


class PolicyType(models.Model):
    name = models.CharField(max_length=100)
    code = models.SlugField(max_length=50, unique=True)
    description = models.TextField(blank=True)

    def __str__(self):
        return self.name


class Insurer(models.Model):
    name = models.CharField(max_length=150)
    address = models.TextField(blank=True)
    contact_email = models.EmailField(blank=True)

    def __str__(self):
        return self.name


# ------------------------------
# Policy Plan
# ------------------------------


class PolicyPlan(models.Model):
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)

    policy_type = models.ForeignKey(
        PolicyType,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )

    insurer = models.ForeignKey(
        Insurer,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )

    sum_insured = models.DecimalField(
        max_digits=12,
        decimal_places=2
    )

    premium = models.DecimalField(
        max_digits=10,
        decimal_places=2
    )

    deductible = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0
    )

    coverage_details = models.TextField(
        blank=True,
        help_text="Details about what is covered"
    )

    terms_and_conditions = models.TextField(
        blank=True,
        help_text="Terms and conditions for this plan"
    )

    is_active = models.BooleanField(
        default=True,
        help_text="Whether this plan is available for purchase"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        if self.sum_insured:
            # Calculated Deductible = 3% of Sum Insured
            calc_deductible = Decimal(str(self.sum_insured)) * Decimal('0.03')
            # Min 5000, Max 25000
            self.deductible = max(Decimal('5000'), min(Decimal('25000'), calc_deductible))
        super().save(*args, **kwargs)

    class Meta:
        verbose_name = "Policy Plan"
        verbose_name_plural = "Policy Plans"
        ordering = ["-created_at"]


# ------------------------------
# Policy
# ------------------------------


class Policy(models.Model):

    STATUS = [
        ('pending', 'Pending Review'),
        ('active', 'Active'),
        ('rejected', 'Rejected'),
        ('expired', 'Expired'),
        ('cancelled', 'Cancelled'),
    ]

    policy_number = models.CharField(max_length=30, unique=True)

    plan = models.ForeignKey(
        PolicyPlan,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="purchased_policies"
    )

    policy_type = models.CharField(
        max_length=50,
        blank=True,
        null=True
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS,
        default='pending'
    )

    # 🚗 Motor specific fields
    vehicle_number = models.CharField(max_length=20, blank=True, null=True, help_text="Required for Motor Policies")
    rc_upload = models.FileField(upload_to="policy_rc/", blank=True, null=True, help_text="Required for Motor Policies")

    insurer_name = models.CharField(max_length=150, blank=True, null=True)

    start_date = models.DateField()
    end_date = models.DateField()

    is_active = models.BooleanField(default=True)

    sum_insured = models.DecimalField(
        max_digits=12,
        decimal_places=2
    )

    deductible = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0
    )

    # Coverage percentage for ML models
    coverage_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('80.00'),
        help_text="Coverage percentage for claims (e.g., 80.00 for 80%)"
    )

    created_at = models.DateTimeField(auto_now_add=True)

    # Premium Fields
    base_premium = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00')
    )
    gst_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('18.00')
    )
    gst_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0.00
    )
    gross_premium = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0.00
    )

    def save(self, *args, **kwargs):
        # 🛡️ Deductible Calculation
        if self.sum_insured:
            # Calculated Deductible = 3% of Sum Insured
            calc_deductible = Decimal(str(self.sum_insured)) * Decimal('0.03')
            # Min 5000, Max 25000
            self.deductible = max(Decimal('5000'), min(Decimal('25000'), calc_deductible))

            # 💰 Auto-calculate Base Premium if not manually set or being initialized
            # Logic: Health 3%, Motor 2%, Home 1.2%, Else 1%
            if self.base_premium == 0:
                rate = Decimal('0.01')
                ptype = (self.policy_type or "").lower()
                if 'health' in ptype:
                    rate = Decimal('0.03')
                elif 'motor' in ptype or 'vehicle' in ptype:
                    rate = Decimal('0.02')
                elif 'home' in ptype:
                    rate = Decimal('0.012')
                
                self.base_premium = Decimal(str(self.sum_insured)) * rate

        # 📊 GST and Gross Premium Calculation
        if self.base_premium:
            self.gst_amount = (self.base_premium * self.gst_percentage) / Decimal('100')
            self.gross_premium = self.base_premium + self.gst_amount

        super().save(*args, **kwargs)

    def __str__(self):
        return self.policy_number

    class Meta:
        db_table = 'policy_policy'
        verbose_name_plural = "Policies"


# ------------------------------
# Coverage
# ------------------------------


class Coverage(models.Model):

    policy = models.ForeignKey(
        Policy,
        on_delete=models.CASCADE,
        related_name="coverages"
    )

    coverage_type = models.CharField(max_length=100)

    limit_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2
    )

    deductible = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0
    )

    description = models.TextField(blank=True)

    def __str__(self):
        return f"{self.coverage_type} - {self.policy.policy_number}"


# ------------------------------
# Beneficiary
# ------------------------------


class Beneficiary(models.Model):

    policy = models.ForeignKey(
        Policy,
        on_delete=models.CASCADE,
        related_name="beneficiaries"
    )

    name = models.CharField(max_length=150)

    relationship = models.CharField(max_length=100)

    share_percentage = models.IntegerField()

    phone = models.CharField(max_length=15)

    def __str__(self):
        return self.name


# ------------------------------
# Premium
# ------------------------------


class Premium(models.Model):

    STATUS = [
        ('pending', 'Pending'),
        ('paid', 'Paid'),
        ('failed', 'Failed'),
    ]

    policy = models.ForeignKey(
        Policy,
        on_delete=models.CASCADE,
        related_name="premiums"
    )

    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2
    )

    due_date = models.DateField()

    paid_date = models.DateField(
        null=True,
        blank=True
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS,
        default='pending'
    )

    transaction_id = models.CharField(
        max_length=100,
        blank=True
    )

    def __str__(self):
        return f"{self.policy.policy_number} - {self.amount}"


# ------------------------------
# Policy Document
# ------------------------------


class PolicyDocument(models.Model):

    policy = models.ForeignKey(
        Policy,
        on_delete=models.CASCADE,
        related_name="documents"
    )

    document_name = models.CharField(max_length=200)

    file = models.FileField(upload_to="policy_documents/")

    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.document_name


# ------------------------------
# Policy Audit Log
# ------------------------------


class PolicyAuditLog(models.Model):

    policy = models.ForeignKey(
        Policy,
        on_delete=models.CASCADE,
        related_name="logs"
    )

    action = models.CharField(max_length=200)

    performed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True
    )

    created_at = models.DateTimeField(auto_now_add=True)

    description = models.TextField(blank=True)

    def __str__(self):
        return f"{self.policy.policy_number} - {self.action}"


# ------------------------------
# Policy Application
# ------------------------------


class PolicyApplication(models.Model):

    STATUS_CHOICES = [
        ('pending', 'Pending Review'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='policy_applications'
    )

    policy = models.ForeignKey(
        Policy,
        on_delete=models.CASCADE,
        related_name='applications'
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending'
    )

    created_at = models.DateTimeField(auto_now_add=True)

    reviewed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text='Timestamp when admin reviewed this application'
    )

    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reviewed_applications',
        help_text='Admin who approved or rejected this application'
    )

    # Optional admin notes / rejection reason
    admin_remarks = models.TextField(
        blank=True,
        help_text='Reason for rejection or additional notes from admin'
    )

    # Motor-specific fields (stored directly on the application)
    vehicle_number = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        help_text='Vehicle registration number (Motor policies only)'
    )
    rc_upload = models.FileField(
        upload_to='application_rc/',
        blank=True,
        null=True,
        help_text='RC document upload (Motor policies only)'
    )

    def __str__(self):
        return f"{self.user.username} → {self.policy.policy_number} ({self.get_status_display()})"

    class Meta:
        db_table = 'policy_policyapplication'
        verbose_name = 'Policy Application'
        verbose_name_plural = 'Policy Applications'
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'policy'],
                name='unique_user_policy_application'
            )
        ]