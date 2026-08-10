import logging
from celery import shared_task
from django.utils import timezone
from claims.models import Claim

logger = logging.getLogger(__name__)

@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def process_claim_intelligence_task(self, claim_id):
    """
    Asynchronous task to run the AI Intelligence Pipeline.
    Implements Phase 10: Production Engineering with retry logic.
    """
    try:
        claim = Claim.objects.get(public_id=claim_id)
        
        # Avoid redundant processing if already high status
        if claim.status in ['approved', 'rejected', 'settled']:
             return f"Claim {claim.claim_number} already in terminal state."

        from ai_features.services.ai_pipeline_service import run_intelligence_pipeline
        
        logger.info(f"Starting async AI pipeline for {claim.claim_number}")
        results = run_intelligence_pipeline(claim)
        
        if "error" in results:
             raise Exception(f"Pipeline error: {results['message']}")
             
        return f"AI scoring complete for {claim.claim_number}. Verdict: {claim.decision_engine_verdict}"
        
    except Claim.DoesNotExist:
        logger.error(f"Claim ID {claim_id} not found.")
        return "FATAL: Claim not found"
    except Exception as exc:
        logger.error(f"Retry: Failed to process claim {claim_id}: {exc}")
        raise self.retry(exc=exc)
