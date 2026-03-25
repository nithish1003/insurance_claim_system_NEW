from django.db import models
from django.conf import settings
from django.utils import timezone
from django.core.validators import FileExtensionValidator
from policy.models import Policy


ALLOWED_DOCUMENT_EXTENSIONS = ["pdf", "jpg", "jpeg", "png"]

DOCUMENT_EXTENSION_VALIDATOR = FileExtensionValidator(
    allowed_extensions=ALLOWED_DOCUMENT_EXTENSIONS,
    message="Only PDF or JPG/JPEG/PNG files are allowed."
)


# =============================
# CLAIM MODEL
# =============================

class Claim(models.Model):

    STATUS = [
        ("draft", "Draft"),
        ("submitted", "Submitted"),
        ("under_review", "Under Review"),
        ("investigation", "Investigation"),
        ("approved", "Approved"),
        ("partially_approved", "Partially Approved"),
        ("rejected", "Rejected"),
        ("settled", "Settled"),
        ("closed", "Closed"),
        ("withdrawn", "Withdrawn"),
    ]

    CLAIM_TYPE = [
        ("accident", "Accident"),
        ("medical", "Medical"),   # 🔥 IMPORTANT FIX (added for AI)
        ("theft", "Theft"),
        ("death", "Death"),
        ("maturity", "Maturity"),
        ("surrender", "Surrender"),
        ("disability", "Disability"),
        ("critical_illness", "Critical Illness"),
        ("hospitalization", "Hospitalization"),
        ("property_damage", "Property Damage"),
        ("fire", "Fire"),
        ("natural_disaster", "Natural Disaster"),
        ("third_party", "Third Party Liability"),
        ("other", "Other"),
    ]

    policy = models.ForeignKey(
        Policy,
        on_delete=models.CASCADE,
        related_name="claims"
    )

    claim_number = models.CharField(max_length=50, unique=True, db_index=True)

    claim_type = models.CharField(max_length=30, choices=CLAIM_TYPE)

    status = models.CharField(max_length=30, choices=STATUS, default="draft", db_index=True)

    incident_date = models.DateField()

    reported_date = models.DateField(default=timezone.now)

    description = models.TextField(blank=True)

    # 🚗 Motor Insurance Fields
    vehicle_number = models.CharField(
        max_length=20, 
        blank=True, 
        null=True, 
        help_text="Required for Motor Policy claims. Must match the policy vehicle number."
    )

    claimed_amount = models.DecimalField(max_digits=12, decimal_places=2)

    # 🤖 AI PIPELINE V3 (Full ML State)
    ai_version = models.CharField(max_length=10, default="v3.0")
    ml_model_version = models.CharField(max_length=20, default="xgb_baseline_v1")
    ai_updated_at = models.DateTimeField(null=True, blank=True)
    ai_drift_score = models.FloatField(default=0.0, help_text="Detected confidence drift from baseline")
    ai_decision = models.CharField(
        max_length=30, 
        choices=[
            ("auto_process", "Auto Process"),
            ("manual_review", "Manual Review"),
            ("reject", "Reject"),
        ],
        null=True, blank=True,
        help_text="The final automated decision from the AI pipeline"
    )

    bill_amount = models.DecimalField(
        max_digits=12, 
        decimal_places=2, 
        null=True, blank=True,
        help_text="Total amount extracted from invoices via OCR"
    )

    ai_claim_type = models.CharField(
        max_length=50, 
        null=True, 
        blank=True,
        help_text="Automated classification (motor, health, etc.)"
    )
    
    confidence_score = models.FloatField(
        null=True, 
        blank=True, 
        default=0.0,
        help_text="System confidence in classification (0-100%)"
    )

    ai_predicted_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="AI recommended amount AFTER logic and penalties"
    )

    ai_adjustment_factor = models.FloatField(
        null=True, 
        blank=True, 
        help_text="The weight or multiplier applied by AI (e.g. 0.75 for 75%)"
    )

    # =============================
    # 🤖 AI FIELDS (Legacy/Internal - to be refactored)
    # =============================

    # These fields are kept for now but will be consolidated into the V2 fields above.
    # The 'ai_claim_type' and 'confidence_score' above are the unified versions.
    # 'final_claim_type' and 'recommended_amount' are also candidates for consolidation.

    final_claim_type = models.CharField(
        max_length=30,
        choices=CLAIM_TYPE,
        null=True,
        blank=True
    )

    risk_score = models.FloatField(
        null=True,
        blank=True,
        default=0.0
    )

    fraud_flag = models.BooleanField(default=False)

    fraud_explanation = models.TextField(
        null=True, 
        blank=True, 
        help_text="AI-generated fraud risk justification (Internal only)"
    )

    recommended_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True
    )

    # 🏥 Health Insurance Specific Domain Fields (for AI/ML accuracy)
    HOSPITAL_TYPES = [
        ("private", "Private"),
        ("government", "Government"),
        ("network", "Network Hospital"),
    ]

    PRIORITY_CHOICES = [
        ("HIGH", "High Priority"),
        ("MEDIUM", "Medium Priority"),
        ("LOW", "Low Priority"),
    ]

    patient_age = models.IntegerField(null=True, blank=True, help_text="Age of the patient at the time of claim")
    hospital_type = models.CharField(max_length=20, choices=HOSPITAL_TYPES, default="private")
    admission_days = models.IntegerField(default=0, help_text="Number of days hospitalized")
    diagnosis_severity = models.IntegerField(default=1, help_text="Severity of diagnosis (1: Normal, 5: Critical)")
    number_of_tests = models.IntegerField(default=0, help_text="Number of diagnostic tests performed")
    
    medication_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    room_rent_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    # 🚨 Prioritization Fields
    priority_score = models.FloatField(default=0.0, help_text="Automated weight for admin sorting")
    priority_level = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default="LOW")
    priority_reason = models.CharField(max_length=255, blank=True, null=True)
    emergency_flag = models.BooleanField(default=False, help_text="Flag for immediate attention (e.g. ICU admission)")

    ai_calculation_logic = models.TextField(
        null=True,
        blank=True,
        help_text="Human-readable explanation of how AI arrived at the recommended amount"
    )

    # =============================
    # 💰 FINANCIAL FIELDS
    # =============================

    approved_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    
    net_claimable = models.DecimalField(max_digits=12, decimal_places=2, default=0, help_text="Calculated as claimed_amount - deductible_amount")

    settled_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

    deductible_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    def save(self, *args, **kwargs):
        # 🛡️ Real Insurance Safety Guard: Synchronize Net Claimable
        if self.claimed_amount and self.deductible_amount is not None:
             self.net_claimable = max(0, self.claimed_amount - self.deductible_amount)
        super().save(*args, **kwargs)

    rejection_reason = models.TextField(blank=True)

    # =============================
    # 👨‍💼 STAFF FIELDS
    # =============================

    policy_validity = models.CharField(max_length=20, blank=True, null=True)
    document_verification = models.CharField(max_length=20, blank=True, null=True)
    amount_verification = models.CharField(max_length=20, blank=True, null=True)
    staff_comments = models.TextField(blank=True, null=True)

    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_claims"
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="created_claims"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def user(self):
        """Unified access to the claimant/applicant user."""
        return self.created_by

    @property
    def total_settled_amount(self):
        """Returns settled_amount if available, otherwise approved_amount, fallback to 0."""
        return self.settled_amount or self.approved_amount or 0

    def __str__(self):
        return f"Claim {self.claim_number} — {self.policy.policy_number}"

    class Meta:
        ordering = ["-created_at"]

class ClaimAIHistory(models.Model):
    """
    Adaptive learning ledger for AI Pipeline v3.
    Captures 'AI Thoughts' vs 'Human Reality' for future model retraining.
    """
    claim = models.ForeignKey('Claim', on_delete=models.CASCADE, related_name="ai_history")
    version = models.CharField(max_length=10, default="v3.0")
    
    # Snapshot of AI logic at processing time
    ai_claim_type = models.CharField(max_length=50)
    ai_predicted_amount = models.DecimalField(max_digits=12, decimal_places=2)
    ai_risk_score = models.FloatField()
    ai_decision = models.CharField(max_length=30)
    ai_confidence = models.FloatField()
    
    # SHAP Audit Trace (v3.3)
    shap_values = models.JSONField(null=True, blank=True, help_text="Local feature importance values")
    
    # Shadow Deployment Fields (v3.3)
    shadow_decision = models.CharField(max_length=30, null=True, blank=True)
    shadow_predicted_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    
    # Feature Vector (JSON for easy retraining parsing)
    feature_vector = models.JSONField(null=True, blank=True)
    
    # Human Feedback Loop (Updated when staff approves/rejects)
    human_decision = models.CharField(max_length=30, null=True, blank=True)
    human_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    is_disputed = models.BooleanField(default=False)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
        verbose_name_plural = "Claim AI History"

    def __str__(self):
        return f"v{self.version} Audit for {self.claim.claim_number}"
class AIModelMetrics(models.Model):
    """
    Daily performance ledger for ML Models.
    Tracks Precision, Recall, and Accuracy against human ground truth.
    """
    model_version = models.CharField(max_length=50)
    date = models.DateField(auto_now_add=True)
    
    # Core Classification Metrics
    accuracy = models.FloatField(default=0.0)
    precision = models.FloatField(default=0.0)
    recall = models.FloatField(default=0.0)
    f1_score = models.FloatField(default=0.0)
    
    # Per-Class High Fidelity Metrics (v3.2)
    fraud_precision = models.FloatField(default=0.0)
    fraud_recall = models.FloatField(default=0.0)
    non_fraud_precision = models.FloatField(default=0.0)
    non_fraud_recall = models.FloatField(default=0.0)
    
    # Governance & Risk (v3.2)
    health_score = models.FloatField(default=0.0, help_text="Consolidated 0-100 indicator")
    suggested_actions = models.JSONField(null=True, blank=True, help_text="Actionable fixes based on root cause")
    top_error_features = models.JSONField(null=True, blank=True, help_text="Features contributing most to disputes")
    
    # Operational Counts
    total_samples = models.IntegerField(default=0)
    disputed_count = models.IntegerField(default=0)
    
    # Drift Indicators
    average_drift = models.FloatField(default=0.0)
    
    class Meta:
        ordering = ['-date']
        verbose_name_plural = "AI Model Metrics"
        unique_together = ['model_version', 'date']

    def __str__(self):
        return f"{self.model_version} Metrics for {self.date}"

class Claimant(models.Model):

    RELATIONSHIP = [
        ("self", "Self"),
        ("spouse", "Spouse"),
        ("parent", "Parent"),
        ("child", "Child"),
        ("nominee", "Nominee"),
        ("legal_heir", "Legal Heir"),
        ("other", "Other"),
    ]

    claim = models.ForeignKey(
        Claim,
        on_delete=models.CASCADE,
        related_name="claimants"
    )

    full_name = models.CharField(max_length=200)

    relationship = models.CharField(
        max_length=30,
        choices=RELATIONSHIP
    )

    contact_number = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)

    def __str__(self):
        return f"{self.full_name} — {self.claim.claim_number}"


# =============================
# 📎 CLAIM DOCUMENT MODEL
# =============================

class ClaimDocument(models.Model):
    ALLOWED_EXTENSIONS = ALLOWED_DOCUMENT_EXTENSIONS

    DOCUMENT_TYPE = [
        ("claim_form", "Claim Form"),
        ("identity_proof", "Identity Proof (Aadhaar)"),
        ("address_proof", "Address Proof"),
        ("bank_proof", "Bank Proof"),
        ("policy_copy", "Policy Copy"),
        ("rc_document", "Registration Certificate (RC)"),
        ("death_certificate", "Death Certificate"),
        ("property_proof", "Property/Ownership Proof"),
        ("damage_proof", "Damage Proof (Photos/Survey)"),
        ("hospital_bill", "Hospital/Medical Bill"),
        ("repair_bill", "Repair/Diagnostic Bill"),
        ("photos", "Photos / Evidence"),
        ("other", "Other Documents"),
    ]

    claim = models.ForeignKey(
        Claim,
        on_delete=models.CASCADE,
        related_name="documents"
    )

    document_type = models.CharField(
        max_length=30,
        choices=DOCUMENT_TYPE
    )

    file = models.FileField(
        upload_to="claims/documents/",
        validators=[DOCUMENT_EXTENSION_VALIDATOR]
    )

    description = models.CharField(max_length=255, blank=True)

    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True
    )

    uploaded_at = models.DateTimeField(auto_now_add=True)

    # Verification flag — set by staff after document review
    is_verified = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.claim.claim_number} — {self.document_type}"


# =============================
# 📊 CLAIM ASSESSMENT MODEL
# =============================

class ClaimAssessment(models.Model):

    VERDICT = [
        ("approved", "Approved"),
        ("partially_approved", "Partially Approved"),
        ("rejected", "Rejected"),
        ("pending", "Pending Further Info"),
    ]

    claim = models.OneToOneField(
        Claim,
        on_delete=models.CASCADE,
        related_name="assessment"
    )

    assessed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="assessed_claims"
    )

    assessed_on = models.DateField(default=timezone.now)

    verdict = models.CharField(
        max_length=30,
        choices=VERDICT
    )

    # Fields for auto calculation
    bill_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Total bill amount from medical/hospital documents"
    )

    coverage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Coverage percentage (e.g., 80.00 for 80%)"
    )

    deductible = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Deductible amount to be subtracted"
    )

    recommended_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True
    )

    remarks = models.TextField(blank=True)

    investigation_required = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        """
        Auto calculate recommended_amount using formula:
        recommended_amount = (bill_amount * coverage / 100) - deductible
        """
        if self.bill_amount and self.coverage and self.deductible is not None:
            # Calculate: (bill_amount * coverage / 100) - deductible
            calculated_amount = (self.bill_amount * self.coverage / 100) - self.deductible
            
            # Ensure recommended_amount is not negative
            self.recommended_amount = max(0, calculated_amount)
        elif self.bill_amount and self.coverage:
            # If deductible is not provided, just calculate coverage amount
            self.recommended_amount = self.bill_amount * self.coverage / 100
        elif self.claim.claimed_amount:
            # Fallback to claimed amount if no calculation possible
            self.recommended_amount = self.claim.claimed_amount
        
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.claim.claim_number} — {self.verdict}"


# =============================
# 💸 CLAIM SETTLEMENT MODEL
# =============================

class ClaimSettlement(models.Model):

    PAYMENT_MODE = [
        ("neft", "NEFT"),
        ("cheque", "Cheque"),
        ("upi", "UPI"),
        ("cash", "Cash"),
        ("dd", "Demand Draft"),
    ]

    claim = models.OneToOneField(
        Claim,
        on_delete=models.CASCADE,
        related_name="settlement"
    )

    settlement_date = models.DateField(default=timezone.now)

    payment_mode = models.CharField(
        max_length=20,
        choices=PAYMENT_MODE
    )

    transaction_reference = models.CharField(max_length=120, blank=True)

    settled_amount = models.DecimalField(max_digits=12, decimal_places=2)

    payee_name = models.CharField(max_length=200)

    bank_account = models.CharField(max_length=30, blank=True)
    bank_ifsc = models.CharField(max_length=20, blank=True)
    bank_name = models.CharField(max_length=100, blank=True)

    remarks = models.TextField(blank=True)

    processed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="processed_claims"
    )

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.claim.claim_number} — ₹{self.settled_amount}"


# =============================
# 📝 CLAIM NOTE MODEL
# =============================

class ClaimNote(models.Model):

    NOTE_TYPE = [
        ("customer", "Customer Note"),
        ("internal", "Internal Note"),
    ]

    claim = models.ForeignKey(
        Claim,
        on_delete=models.CASCADE,
        related_name="notes"
    )

    note_type = models.CharField(
        max_length=20,
        choices=NOTE_TYPE,
        default="internal"
    )

    message = models.TextField()

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True
    )

    created_at = models.DateTimeField(auto_now_add=True)

    is_visible_to_customer = models.BooleanField(default=False)
    is_important = models.BooleanField(default=False)

    def save(self, *args, **kwargs):
        # Automatically set visibility based on note type
        if self.note_type == "customer":
            self.is_visible_to_customer = True
        else:
            self.is_visible_to_customer = False
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.claim.claim_number} — {self.get_note_type_display()}"

    class Meta:
        ordering = ['-created_at']


# =============================
# 📋 CLAIM AUDIT LOG MODEL
# =============================

class ClaimAuditLog(models.Model):

    claim = models.ForeignKey(
        Claim,
        on_delete=models.CASCADE,
        related_name="audit_logs"
    )

    action = models.CharField(max_length=200)

    performed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True
    )

    description = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.claim.claim_number} — {self.action}"
