from django.db import models
from decimal import Decimal
from .utils import safe_money
from django.core.exceptions import ValidationError
from django.conf import settings
from django.utils import timezone
from django.core.validators import FileExtensionValidator
from policy.models import Policy
import uuid as uuid_lib


ALLOWED_DOCUMENT_EXTENSIONS = ["pdf", "jpg", "jpeg", "png"]

DOCUMENT_EXTENSION_VALIDATOR = FileExtensionValidator(
    allowed_extensions=ALLOWED_DOCUMENT_EXTENSIONS,
    message="Only PDF or JPG/JPEG/PNG files are allowed."
)


# =============================
# ML MODEL REGISTRY (Requirements Phase 2)
# =============================

class ClaimModelVersion(models.Model):
    """
    Registry for tracking every ML model iteration deployed in the system.
    Enables auditability and exact reproduction of any score/payout.
    """
    version_id = models.CharField(max_length=50, unique=True, help_text="e.g. XGB_v3.2, HEALTH_v1.0")
    algorithm_type = models.CharField(max_length=100, help_text="XGBoost, RandomForest, Ensemble")
    trained_at = models.DateTimeField()
    dataset_hash = models.CharField(max_length=64, help_text="SHA-256 hash of the training dataset CSV")
    feature_schema_version = models.CharField(max_length=20, help_text="Tracks changes in input feature engineering")
    is_active = models.BooleanField(default=False, help_text="Current production model")
    metrics = models.JSONField(null=True, blank=True, help_text="Snapshot of Precision, Recall, Accuracy")
    
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.version_id

    class Meta:
        verbose_name_plural = "AI Model Registry"
        ordering = ['-created_at']


# =============================
# CLAIM MODEL
# =============================

class Claim(models.Model):
    public_id = models.UUIDField(default=uuid_lib.uuid4, unique=True, editable=False, db_index=True)

    STATUS = [
        ("submitted", "Submitted"),
        ("under_review", "Under Review"),
        ("staff_reviewed", "Waiting Approval"),
        ("investigation", "Investigation"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
        ("settled", "Settled"),
        ("closed", "Closed"),
        ("withdrawn", "Withdrawn"),
    ]

    CLAIM_TYPE = [
        ("accident", "Accident"),
        ("medical", "Medical"),
        ("theft", "Theft"),
        ("death", "Death"),
        ("disability", "Disability"),
        ("other", "Other"),
    ]

    # 🚑 CLINICAL URGENCY & TRIAGE
    ADMISSION_TYPE_CHOICES = [
        ("routine", "Routine (Scheduled)"),
        ("emergency", "Emergency (Unscheduled)"),
    ]

    PRIORITY_LEVEL_CHOICES = [
        ("critical", "CRITICAL 🔥"),
        ("high", "HIGH 🛡️"),
        ("medium", "MEDIUM 🚑"),
        ("low", "LOW 📄"),
    ]

    policy = models.ForeignKey(Policy, on_delete=models.CASCADE, related_name="claims")
    user_policy = models.ForeignKey('policy.UserPolicy', on_delete=models.CASCADE, related_name='claims', null=True, blank=True)
    
    # 🤖 DECISION ENGINE FLOW (Requirement Phase 4)
    DECISION_ENGINE_VERDICT = [
        ("auto_approve", "Auto Approve ✅"),
        ("manual_review", "Manual Review 🔍"),
        ("investigation", "Flag for Investigation 🚨"),
        ("rejected", "Rejected (Hard Rule) ❌"),
    ]
    decision_engine_verdict = models.CharField(
        max_length=30, 
        choices=DECISION_ENGINE_VERDICT,
        default="manual_review",
        db_index=True
    )
    decision_orchestration_at = models.DateTimeField(null=True, blank=True)
    
    claim_number = models.CharField(max_length=50, unique=True, db_index=True)
    claim_type = models.CharField(max_length=30, choices=CLAIM_TYPE)
    status = models.CharField(max_length=30, choices=STATUS, default="submitted", db_index=True)
    
    # ⚖️ AUDIT & GOVERNANCE FIELDS (Requirement 2 & 4)
    staff_recommendation = models.CharField(
        max_length=20, 
        choices=[("APPROVE", "Approve"), ("REJECT", "Reject"), ("REVIEW", "Review")], 
        null=True, blank=True
    )
    staff_notes = models.TextField(blank=True, help_text="Detailed assessment findings by staff.")
    admin_override = models.JSONField(
        null=True, blank=True, 
        help_text="Records admin decision and justification when it differs from staff recommendation."
    )

    incident_date = models.DateField()

    reported_date = models.DateTimeField(default=timezone.now)
    
    # ── VALIDATION & STATE MACHINE ──────────────────────────────────────────
    
    def validate_status_transition(self, new_status):
        """
        Enforces Regulator-Grade Workflow:
        SUBMITTED → UNDER_REVIEW → INVESTIGATION → APPROVED → SETTLED
        """
        if self._state.adding:
            # Creation phase: Must start at SUBMITTED (or DRAFT)
            if new_status not in ['submitted', 'draft']:
                 raise ValidationError(f"New claims must start in 'submitted' status. Received: {new_status}")
            return

        # Fetch current status from DB to prevent tampering
        old_status = Claim.objects.get(pk=self.pk).status
        if old_status == new_status:
            return

        # Define high-fidelity transition map
        VALID_TRANSITIONS = {
            'draft': ['submitted'],
            'submitted': ['under_review', 'rejected', 'withdrawn'],
            'under_review': ['staff_reviewed', 'investigation', 'approved', 'rejected'],
            'staff_reviewed': ['approved', 'rejected', 'under_review'],
            'investigation': ['staff_reviewed', 'approved', 'rejected'],
            'approved': ['settled'],
            'rejected': ['under_review'], # Permissive for appeals
            'settled': [], # Terminal
            'closed': [], # Terminal
            'withdrawn': ['submitted'],
        }

        allowed_next = VALID_TRANSITIONS.get(old_status, [])
        if new_status not in allowed_next:
            raise ValidationError(
                f"Invalid Workflow Violation: Cannot move dossier from '{old_status}' to '{new_status}'. "
                f"Expected next stages: {', '.join(allowed_next) if allowed_next else 'None (Terminal State)'}"
            )

    def save(self, *args, **kwargs):
        """Final Persistence Hook: Enforces Workflow State and Financial Integrity"""
        
        # 🛡️ 1. Extract Custom Arguments EARLY (Crucial for Django super().save compatibility)
        skip_workflow = kwargs.pop('skip_workflow_check', False)
        performing_user = kwargs.pop('user', None)

        is_new = self._state.adding
        old_status = None

        if not is_new:
            # 🛡️ 1. Workflow validation
            if not skip_workflow:
                self.validate_status_transition(self.status)
            old_status = Claim.objects.get(pk=self.pk).status

        # 🛡️ 2. Hardened Assessment Logic (Requirement #7)
        from .services.claim_assessment_service import ClaimAssessmentService
        ClaimAssessmentService.evaluate(self)

        # 3. Standard Save
        super().save(*args, **kwargs)

        # 4. Post-Save Logic: Synchronize Policy Balance on Settlement
        if self.status == 'settled' and self.user_policy:
            self.user_policy.sync_status_with_premiums()

        # 5. Post-Save Audit Logging (On Status Change)
        if not is_new and old_status and old_status != self.status:
            ClaimAuditLog.objects.create(
                claim=self,
                action=f"Workflow Transition: {old_status.upper()} -> {self.status.upper()}",
                description=f"Automated State Machine validation successful.",
                performed_by=performing_user
            )

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

    ocr_text = models.TextField(
        blank=True, 
        null=True,
        help_text="Full text dump from the dossier (multi-document OCR merger)."
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
        help_text="Overall confidence of the AI classification (0-100)."
    )

    # 🚨 ENTERPRISE FRAUD: AMOUNT INTEGRITY (Requirement Phase 1)
    claim_amount_mismatch_ratio = models.FloatField(
        default=0.0, 
        help_text="ABS(Declared - OCR) / OCR"
    )
    declared_claim_amount = models.DecimalField(
        max_digits=12, decimal_places=2, 
        null=True, blank=True,
        help_text="User-entered amount at submission"
    )
    ocr_verified_bill_total = models.DecimalField(
        max_digits=12, decimal_places=2, 
        default=0.0,
        help_text="Sum of all validated amounts from OCR"
    )
    mismatch_risk_score = models.FloatField(
        default=0.0,
        help_text="Derived risk penalty for amount variance"
    )
    mismatch_flag = models.BooleanField(
        default=False,
        help_text="True if mismatch > threshold (e.g., 15%)"
    )
    additional_bill_requested = models.BooleanField(
        default=False,
        help_text="Automated trigger for more evidence"
    )

    # ── PAYOUT CONTROL ENGINE (Requirement Phase 2) ─────────────────────
    PAYOUT_SOURCE_CHOICES = [
        ('DECLARED', 'Declared Amount'),
        ('OCR', 'OCR Verified'),
        ('MANUAL', 'Manual Override'),
        ('AI_RECOMMENDED', 'AI Recommended'),
    ]

    INTEGRITY_STATUS_CHOICES = [
        ('PASS', 'Pass (Verified)'),
        ('MINOR', 'Minor Variance'),
        ('MEDIUM', 'Medium Variance (Amber)'),
        ('HIGH', 'High Variance'),
        ('CRITICAL', 'Critical Anomaly (Red)'),
    ]

    payout_basis_amount = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
        help_text="The authoritative amount chosen as basis for payout calculation."
    )
    payout_basis_source = models.CharField(
        max_length=20, choices=PAYOUT_SOURCE_CHOICES, default='DECLARED',
        help_text="Where the payout payout_basis_amount originated from."
    )
    integrity_status = models.CharField(
        max_length=20, choices=INTEGRITY_STATUS_CHOICES, default='PASS',
        help_text="Classification of the amount mismatch severity."
    )
    manual_amount_confirmed = models.BooleanField(
        default=False, help_text="True if a human has explicitly confirmed the payout basis."
    )
    review_hold_flag = models.BooleanField(
        default=False, help_text="Prevents automated settlement until review is cleared."
    )
    critical_mismatch_flag = models.BooleanField(
        default=False, help_text="Trigger for high-level fraud escalation."
    )

    @property
    def mismatch_ratio_percentage(self):
        return self.claim_amount_mismatch_ratio * 100

    def derive_integrity_status(self, mismatch_ratio=None):
        """
        Classify amount integrity severity using the regulator-grade threshold ladder.
        PASS (<5%), MEDIUM (5-15%), CRITICAL (>15%)
        """
        ratio = float(safe_money(self.claim_amount_mismatch_ratio)) if mismatch_ratio is None else float(mismatch_ratio)
        if ratio <= 0.05:
            return "PASS"
        if ratio <= 0.15:
            return "MINOR"
        if ratio <= 0.30:
            return "MEDIUM"
        if ratio <= 0.50:
            return "HIGH"
        return "CRITICAL"

    def get_integrity_required_action(self):
        """
        Returns the required operational response for the current integrity status.
        """
        mapping = {
            "PASS": "Auto payout permitted",
            "MINOR": "Use lower verified basis and monitor variance",
            "MEDIUM": "Manual review recommended",
            "HIGH": "Auto payout hold",
            "CRITICAL": "Escalate fraud queue immediately",
        }
        return mapping.get(self.integrity_status, "Review integrity state")

    def resolve_payout_basis(self, declared=None, verified=None, manual_amount=None):
        """
        Apply the authoritative payout-basis policy (Priority: Manual > OCR > Declared).
        """
        declared_val = safe_money(declared if declared is not None else (self.declared_claim_amount or self.claimed_amount or 0))
        verified_val = safe_money(verified if verified is not None else (self.ocr_verified_bill_total or 0))
        
        # SSoT Logic: We trust verified bills over customer declarations
        # If mismatch is significant, we MUST use the verified basis.
        base_denominator = verified_val if verified_val > 0 else Decimal("1")
        ratio = abs(declared_val - verified_val) / base_denominator

        if manual_amount is not None:
            amount = safe_money(manual_amount)
            self.payout_basis_amount = amount
            self.payout_basis_source = "MANUAL"
            self.manual_amount_confirmed = True
        elif verified_val > 0:
            # Phase 1: Authoritative SSoT uses OCR if available
            self.payout_basis_amount = verified_val
            self.payout_basis_source = "OCR"
            self.manual_amount_confirmed = False
        else:
            # Fallback to declared if no OCR available
            self.payout_basis_amount = declared_val
            self.payout_basis_source = "DECLARED"
            self.manual_amount_confirmed = False

        self.integrity_status = self.derive_integrity_status(ratio)
        self.claim_amount_mismatch_ratio = float(ratio)
        self.critical_mismatch_flag = ratio > Decimal("0.15") # Regulator-grade trigger
        self.review_hold_flag = ratio > Decimal("0.05")
        
        return self.payout_basis_amount

    @property
    def mismatch_amount(self):
        """Absolute variance between declared and verified amounts."""
        declared = safe_money(self.declared_claim_amount or self.claimed_amount or 0)
        verified = safe_money(self.ocr_verified_bill_total or 0)
        return abs(declared - verified)

    @property
    def integrity_required_action(self):
        return self.get_integrity_required_action()

    fraud_probability = models.FloatField(
        null=True, 
        blank=True, 
        default=0.0,
        help_text="The Raw probability score from the XGBoost model (0-1)"
    )

    # ── VERSIONED PAYOUT ARCHITECTURE (replaces ai_predicted_amount) ──────
    initial_ai_prediction = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
        help_text="FROZEN first estimate captured at claim submission time."
    )
    final_ai_recommendation = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
        help_text="Latest authoritative AI payout after full pipeline execution."
    )
    human_override_amount = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
        help_text="Manual auditor override amount (takes display priority over AI)."
    )
    ai_engine_version = models.CharField(
        max_length=50, default="v2.0",
        help_text="Engine version that produced final_ai_recommendation."
    )
    prediction_generated_at = models.DateTimeField(
        null=True, blank=True,
        help_text="Timestamp when the AI recommendation was generated."
    )

    ai_adjustment_factor = models.FloatField(
        null=True, 
        blank=True, 
        help_text="The weight or multiplier applied by AI (e.g. 0.75 for 75%)"
    )

    # consolidated fields
    final_claim_type = models.CharField(
        max_length=30,
        choices=CLAIM_TYPE,
        null=True,
        blank=True
    )

    # ── NEXT GEN RISK ARCHITECTURE (Requirement Phase 1) ─────────────────
    fraud_risk_score = models.FloatField(
        default=0.0, help_text="Probability of intentional fraud (0-1)"
    )
    leakage_risk_score = models.FloatField(
        default=0.0, help_text="Probability of overbilling/waste (0-1)"
    )
    documentation_risk_score = models.FloatField(
        default=0.0, help_text="OCR quality / missing docs score (0-1)"
    )
    payout_uncertainty_score = models.FloatField(
        default=0.0, help_text="Confidence interval around recommendation (0-1)"
    )

    # ── VERSIONED AI ENGINE (Requirement Phase 2) ────────────────────────
    model_version = models.ForeignKey(
        'ClaimModelVersion', 
        on_delete=models.SET_NULL, 
        null=True, blank=True,
        related_name="claims",
        help_text="The exact ML model version used for this specific assessment."
    )

    # ── EXPLAINABILITY 2.0 (Requirement Phase 3) ─────────────────────────
    shap_narrative = models.TextField(
        null=True, blank=True, 
        help_text="Human-readable summary of influencing factors."
    )
    top_features = models.JSONField(
        null=True, blank=True,
        help_text="Key features and their SHAP contributions (positive/negative)."
    )

    risk_score = models.FloatField(
        null=True,
        blank=True,
        default=0.0
    )

    risk_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        help_text="The monetary value of the AI risk reserve (deduction)."
    )

    # 🚨 TRIAGE & PRIORITY (Unified Metrics)
    admission_type = models.CharField(
        max_length=20,
        choices=ADMISSION_TYPE_CHOICES,
        default='routine',
        help_text="Clinical urgency identifier for AI triage."
    )
    
    priority_level = models.CharField(
        max_length=20,
        choices=PRIORITY_LEVEL_CHOICES,
        default='low',
        db_index=True
    )
    
    priority_reason = models.TextField(
        blank=True,
        help_text="AI-generated justification for the assigned priority level."
    )

    # 📝 AUDIT & GOVERNANCE LOGS
    ai_audit_note = models.TextField(
        blank=True,
        help_text="Deterministic AI generated audit note for the dossier."
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
    non_medical_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    diagnostics_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    # Allowed Limits (for deviation calculation)
    allowed_room_rent = models.DecimalField(max_digits=12, decimal_places=2, default=5000)
    allowed_diagnostics = models.DecimalField(max_digits=12, decimal_places=2, default=10000)

    # 🚨 Prioritization Fields
    priority_score = models.FloatField(default=0.0, help_text="Automated weight for admin sorting")
    priority_level = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default="LOW")
    priority_reason = models.CharField(max_length=255, blank=True, null=True)
    emergency_flag = models.BooleanField(default=False, help_text="Flag for immediate attention (e.g. ICU admission)")

    # AI Risk Scores (0-1)
    hospital_risk_score = models.FloatField(default=0.1, help_text="Risk score of the provider")
    user_risk_score = models.FloatField(default=0.05, help_text="Historical behavior score of the claimant")

    ai_calculation_logic = models.TextField(
        null=True,
        blank=True,
        help_text="Human-readable explanation of how AI arrived at the recommended amount"
    )

    # =============================
    # 💰 FINANCIAL FIELDS
    # =============================

    approved_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    manual_override = models.BooleanField(default=False, help_text="Set to True if staff/admin manually changed the AI recommendation")
    override_reason = models.TextField(null=True, blank=True, help_text="Mandatory justification for manual overrides")
    ai_payout_backup = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True, help_text="AI Final Payable value before any human intervention")
    
    net_claimable = models.DecimalField(max_digits=12, decimal_places=2, default=0, help_text="Calculated as claimed_amount - deductible_amount")
    
    ocr_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True, help_text="Total amount extracted from documents via OCR engine")

    settled_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

    deductible_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    rejection_reason = models.TextField(blank=True)

    # =============================
    # 👨‍💼 STAFF FIELDS
    # =============================

    policy_validity = models.CharField(max_length=20, blank=True, null=True)
    document_verification = models.CharField(max_length=20, blank=True, null=True)
    amount_verification = models.CharField(max_length=20, blank=True, null=True)
    staff_recommendation = models.CharField(max_length=50, blank=True, null=True, help_text="Auditor's initial decision (Approve/Reject/Review).")
    staff_notes = models.TextField(blank=True, null=True, help_text="Internal notes from the auditing staff.")
    staff_comments = models.TextField(blank=True, null=True)

    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_claims"
    )
    assigned_at = models.DateTimeField(null=True, blank=True, help_text="Timestamp when the dossier was assigned to a staff member.")
    
    # 📉 AUDITOR PERFORMANCE LINKAGE
    deviation_score = models.FloatField(default=0.0, help_text="Calculated deviation between AI and Human recommendations.")
    
    managed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="managed_dossiers"
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="created_claims"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    @property
    def authoritative_payout(self):
        """
        Single Source of Truth for the Payout amount across all surfaces.
        Priority: Human Override > AI Final Recommendation > Initial Prediction
        """
        from .services.claim_payout_service import ClaimPayoutService
        return ClaimPayoutService.get_authoritative_payout(self)

    @property
    def payout_label(self):
        """Standardized label for display based on payout priority."""
        from .services.claim_payout_service import ClaimPayoutService
        return ClaimPayoutService.get_payout_label(self)

    @property
    def review_payload(self):
        """
        Authoritative SSoT payload for UI/API consumption.
        Centralizes risk scoring and settlement math.
        """
        from .services.claim_review_service import ClaimReviewService
        return ClaimReviewService.get_review_payload(self)

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
        indexes = [
            models.Index(fields=["claim_amount_mismatch_ratio"], name="claim_mismatch_idx"),
            models.Index(fields=["integrity_status"], name="claim_integrity_idx"),
            models.Index(fields=["review_hold_flag"], name="claim_review_hold_idx"),
            models.Index(fields=["critical_mismatch_flag"], name="claim_critical_mismatch_idx"),
            models.Index(fields=["payout_basis_source"], name="claim_payout_basis_idx"),
        ]

class ClaimAIHistory(models.Model):
    """
    Adaptive learning ledger for AI Pipeline v3.
    Captures 'AI Thoughts' vs 'Human Reality' for future model retraining.
    """
    public_id = models.UUIDField(default=uuid_lib.uuid4, unique=True, editable=False, db_index=True)
    claim = models.ForeignKey('Claim', on_delete=models.CASCADE, related_name="ai_history")
    version = models.CharField(max_length=50, default="v3.0")
    
    # Snapshot of AI logic at processing time
    ai_claim_type = models.CharField(max_length=50)
    ai_recommendation = models.DecimalField(max_digits=12, decimal_places=2)
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


class PayoutRecommendationLog(models.Model):
    """
    Immutable audit trail for every AI recommendation or human override.
    Captures before/after values, who made the change, and why.
    """
    public_id = models.UUIDField(default=uuid_lib.uuid4, unique=True, editable=False)
    claim = models.ForeignKey('Claim', on_delete=models.CASCADE, related_name='payout_logs')
    previous_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    new_amount = models.DecimalField(max_digits=12, decimal_places=2)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL
    )
    change_reason = models.CharField(max_length=500)
    engine_version = models.CharField(max_length=50)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Payout Recommendation Log"
        verbose_name_plural = "Payout Recommendation Logs"

    def __str__(self):
        return f"Payout Log: {self.claim.claim_number} — ₹{self.new_amount} ({self.engine_version})"


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
    public_id = models.UUIDField(default=uuid_lib.uuid4, unique=True, editable=False, db_index=True)
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

    # 🛡️ FRAUD DETECTION (Requirement Phase 5)
    ocr_hash = models.CharField(
        max_length=64, 
        blank=True, null=True, 
        db_index=True,
        help_text="SHA-256 hash of extracted text to detect duplicate invoices."
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
    public_id = models.UUIDField(default=uuid_lib.uuid4, unique=True, editable=False, db_index=True)

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
            # Prevent Decimal vs float type mismatches by converting operands explicitly to Decimal
            bill_dec = Decimal(str(self.bill_amount))
            cov_dec = Decimal(str(self.coverage))
            ded_dec = Decimal(str(self.deductible))
            calculated_amount = (bill_dec * cov_dec / Decimal('100')) - ded_dec
            
            # Ensure recommended_amount is not negative
            self.recommended_amount = max(Decimal('0'), calculated_amount)
        elif self.bill_amount and self.coverage:
            bill_dec = Decimal(str(self.bill_amount))
            cov_dec = Decimal(str(self.coverage))
            self.recommended_amount = bill_dec * cov_dec / Decimal('100')
        elif self.claim.claimed_amount:
            # Fallback to claimed amount if no calculation possible
            self.recommended_amount = Decimal(str(self.claim.claimed_amount))
        
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.claim.claim_number} — {self.verdict}"


# =============================
# 💸 CLAIM SETTLEMENT MODEL
# =============================

class ClaimSettlement(models.Model):
    public_id = models.UUIDField(default=uuid_lib.uuid4, unique=True, editable=False, db_index=True)

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


# =============================
# 🎯 AUDITOR PERFORMANCE MODEL
# =============================

class AuditorReview(models.Model):
    """
    Captures formal auditor decisions and recommendation vs AI data 
    for performance metrics and tiering.
    """
    DECISION_CHOICES = [
        ('APPROVE', 'Proceed with AI Recommendation'),
        ('MODIFY', 'Manual Override / Adjustment'),
        ('REJECT', 'Formal Rejection'),
    ]
    
    claim = models.ForeignKey(Claim, on_delete=models.CASCADE, related_name='auditor_reviews')
    auditor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='auditor_reviews')
    
    decision = models.CharField(max_length=15, choices=DECISION_CHOICES)
    recommended_amount = models.DecimalField(max_digits=12, decimal_places=2)
    ai_original_amount = models.DecimalField(max_digits=12, decimal_places=2)
    remarks = models.TextField(null=True, blank=True)
    
    # Financial Throughput Linkage (Original Claim Amount at time of review)
    throughput_value = models.DecimalField(max_digits=12, decimal_places=2, help_text="Carried value of the original claim submission.")
    
    # SLA Metrics
    assigned_at = models.DateTimeField(null=True)
    reviewed_at = models.DateTimeField(null=True)
    process_duration_seconds = models.IntegerField(null=True, blank=True)
    is_within_sla = models.BooleanField(default=True)

    # Accuracy / Deviation
    accuracy_score = models.FloatField(default=0.0)
    deviation_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0.0)

    def save(self, *args, **kwargs):
        # Calculate Accuracy: (1 - ABS(ai - human) / ai) * 100
        if self.ai_original_amount and self.ai_original_amount > 0:
            diff = abs(self.ai_original_amount - self.recommended_amount)
            self.deviation_amount = self.recommended_amount - self.ai_original_amount
            orig_val = float(safe_money(self.ai_original_amount))
            if orig_val > 0:
                self.accuracy_score = round(max(0, (1 - (float(diff) / orig_val))) * 100, 2)
            else:
                self.accuracy_score = 0
        else:
            self.accuracy_score = 100.0
            
        # Calculate SLA: Standard is 7 days (604800 seconds)
        if self.assigned_at:
            # We use reviewed_at as now if not set yet (auto_now_add hasn't fired)
            duration = (timezone.now() - self.assigned_at).total_seconds()
            self.process_duration_seconds = int(duration)
            self.is_within_sla = duration <= 604800 # 7 Days SLA
            
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Review: {self.claim.claim_number} by {self.auditor.username} ({self.accuracy_score}%)"


# =============================
# ⚖️ IMMUTABLE AUDIT LEDGER (Phase 9)
# =============================

class ImmutableAuditLedger(models.Model):
    """
    Regulator-grade (IRDAI) immutable audit trail.
    Once created, this record should NEVER be modified.
    Stores the full context of any financial or status change.
    """
    public_id = models.UUIDField(default=uuid_lib.uuid4, unique=True, editable=False)
    claim = models.ForeignKey(Claim, on_delete=models.CASCADE, related_name="immutable_logs")
    
    event_type = models.CharField(max_length=50, help_text="PAYOUT_CHANGE, STATUS_CHANGE, FRAUD_FLAG")
    previous_value = models.TextField(null=True, blank=True)
    new_value = models.TextField()
    
    change_reason = models.TextField()
    performed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True
    )
    
    # Snapshot metadata
    model_version = models.ForeignKey(ClaimModelVersion, on_delete=models.SET_NULL, null=True, blank=True)
    shap_snapshot = models.JSONField(null=True, blank=True)
    risk_snapshot = models.JSONField(null=True, blank=True)
    
    timestamp = models.DateTimeField(auto_now_add=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        ordering = ['-timestamp']
        verbose_name = "Immutable Audit Ledger"
        verbose_name_plural = "Immutable Audit Ledgers"

    def __str__(self):
        return f"{self.event_type} for {self.claim.claim_number} at {self.timestamp}"
    
    def save(self, *args, **kwargs):
        if self.pk:
            # Prevent modification of existing logs
            raise ValidationError("ImmutableAuditLedger records cannot be modified after creation.")
        super().save(*args, **kwargs)
