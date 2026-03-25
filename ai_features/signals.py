"""
Signals for AI features
Automatically trigger AI predictions when claims are created or updated
"""

from django.db.models.signals import post_save
from django.dispatch import receiver
from django.db import transaction
from claims.models import Claim
from .services.ai_claim_service import predict_claim_type
from .services.fraud_service import predict_fraud_risk
from .services.amount_service import predict_recommended_amount


@receiver(post_save, sender=Claim)
def trigger_ai_predictions(sender, instance, created, update_fields, **kwargs):
    """
    Automatically trigger AI predictions when a claim is created or updated.
    Includes a recursion guard for AI-only field updates.
    """
    # ── 🚨 RECURSION GUARD ─────────────────────────────────────────────
    # If the save was specifically for AI fields, do NOT re-trigger
    ai_fields = {
        'ai_claim_type', 'confidence_score', 'risk_score', 'fraud_flag', 
        'fraud_explanation', 'recommended_amount', 'ai_predicted_amount', 
        'ai_adjustment_factor', 'ai_calculation_logic',
        'priority_score', 'priority_level', 'priority_reason', 'emergency_flag'
    }
    if update_fields and all(f in ai_fields for f in update_fields):
        return

    # Only process if the claim has a description and is not a draft
    if instance.description and instance.status != 'draft':
        try:
            # Use transaction.on_commit to ensure the claim is fully saved
            transaction.on_commit(lambda: run_ai_predictions(instance))
        except Exception as e:
            # Log error but don't fail the save
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error triggering AI predictions for claim {instance.id}: {e}")


def run_ai_predictions(claim):
    """
    Run all AI predictions for a claim securely
    """
    try:
        # 1. Predict claim type
        from .services.ai_claim_service import predict_claim_type
        ai_claim_type, type_confidence = predict_claim_type(claim.description)
        claim.ai_claim_type = ai_claim_type
        
        # 2. Predict fraud risk
        from .services.fraud_service import predict_fraud_risk
        risk_score, fraud_flag, risk_level, fraud_explanation = predict_fraud_risk(claim)
        claim.risk_score = risk_score
        claim.fraud_flag = fraud_flag
        claim.fraud_explanation = fraud_explanation
        
        # 3. Predict recommended amount (Updates in-memory features like logic and adjustment)
        from .services.amount_service import predict_recommended_amount
        recommended_amount = predict_recommended_amount(claim)
        claim.recommended_amount = recommended_amount
        
        # 4. Update Priority (Sorting urgency for admin)
        from .services.prioritization_service import update_claim_priority
        update_claim_priority(claim)
        
        # Save all AI predicted fields
        claim.save(update_fields=[
            'ai_claim_type', 
            'confidence_score',
            'risk_score', 
            'fraud_flag',
            'fraud_explanation',
            'recommended_amount',
            'ai_predicted_amount',
            'ai_adjustment_factor',
            'ai_calculation_logic',
            'priority_score',
            'priority_level',
            'priority_reason',
            'emergency_flag'
        ])
        
        # Log results to System Activity (Centralized Logger)
        from reports.models import ActivityLog
        ActivityLog.objects.create(
            title=f"AI Audit Complete: {claim.claim_number}",
            description=f"Predicted type: {claim.ai_claim_type}, Risk: {claim.risk_score}%",
            log_type='claim',
            status='success',
            claim=claim
        )
        
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"❌ Critical AI Audit failure for claim {claim.id}: {e}")
        
        # Log AI Failure to System Activity
        try:
            from reports.models import ActivityLog
            ActivityLog.objects.create(
                title=f"AI Prediction Failed",
                description=f"Critical error for claim {claim.id}: {str(e)}",
                log_type='error',
                status='error',
                claim=claim
            )
        except:
            pass