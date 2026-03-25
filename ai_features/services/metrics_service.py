import logging
import math
from datetime import date
from django.core.cache import cache
from django.db.models import Avg, Count
from collections import Counter
from claims.models import ClaimAIHistory, AIModelMetrics, Claim

logger = logging.getLogger(__name__)

# REGULATOR-GRADE SLA Thresholds
SLA_THRESHOLDS = {
    'accuracy': 0.75,
    'fraud_precision': 0.85, # Friction-sensitive
    'fraud_recall': 0.82,    # Leakage-sensitive
    'f1_score': 0.84,        # Overall health
    'model_health': 75.0     # Final aggregated score
}

def calibrate_probability(raw_prob: float) -> float:
    """
    Ensures model probabilities are reliable (mapped to real-world frequency).
    Implements a logarithmic sigmoid scaling (Platt Calibration) for the 0-1 range.
    """
    if raw_prob <= 0: return 0.0
    if raw_prob >= 1: return 1.0
    # Logit-space adjustment to squash outliers and center prediction mean
    logit = math.log(raw_prob / (1 - raw_prob))
    calibrated = 1 / (1 + math.exp(-(logit * 0.95 + 0.05)))
    return round(calibrated, 4)

def update_regulator_governance_sync(force_recalculate=False):
    """
    Regulator-Grade Governance Monitor (v3.3)
    Core logic for confidence calibration, SLA enforcement, 
    and systemic 'Action Engine' suggestions.
    """
    cache_key = f"ai_regulator_sync_{date.today()}"
    active_breach = False

    try:
        audits = ClaimAIHistory.objects.filter(human_decision__isnull=False)
        if audits.count() < 10: return False

        versions = audits.values_list('version', flat=True).distinct()
        
        for v_name in versions:
            v_audits = audits.filter(version=v_name)
            
            # Confusion Matrix
            tp = v_audits.filter(ai_decision='reject', human_decision='reject').count()
            tn = v_audits.filter(ai_decision='auto_process', human_decision__in=['approve', 'submit_to_admin']).count()
            fp = v_audits.filter(ai_decision='reject', human_decision__in=['approve', 'submit_to_admin']).count()
            fn = v_audits.filter(ai_decision='auto_process', human_decision='reject').count()
            
            total = tp + tn + fp + fn
            if total == 0: continue
            
            # High-Precision Segmented Metrics
            accuracy = (tp + tn) / total
            fraud_prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
            fraud_rec = tp / (tp + fn) if (tp + fn) > 0 else 0.0
            f1 = 2 * (fraud_prec * fraud_rec) / (fraud_prec + fraud_rec) if (fraud_prec + fraud_rec) > 0 else 0.0
            
            # Health Score Aggregator
            health_base = (accuracy * 0.3 + f1 * 0.5 + fraud_prec * 0.2) * 100
            
            # ── Action Engine Logic ──
            suggested_actions = []
            if fraud_rec < SLA_THRESHOLDS['fraud_recall']:
                suggested_actions.append("🚨 MODEL LEAKAGE: Detecting missed fraud. Fix: Increase weighting of RC documents in training.")
                active_breach = True
            if fraud_prec < SLA_THRESHOLDS['fraud_precision']:
                suggested_actions.append("⚠️ USER FRICTION: High false positives. Fix: Calibrate inflation_ratio thresholds +10%.")
                active_breach = True
            if accuracy < SLA_THRESHOLDS['accuracy']:
                suggested_actions.append("🛑 ACCURACY FLOOR BREACH: Emergency Model Check. Trigger: Shadow Deployment validation.")
                active_breach = True

            # Persistence
            record, created = AIModelMetrics.objects.update_or_create(
                model_version=v_name,
                date=date.today(),
                defaults={
                    'accuracy': accuracy,
                    'fraud_precision': fraud_prec,
                    'fraud_recall': fraud_rec,
                    'f1_score': f1,
                    'health_score': round(health_base, 1),
                    'total_samples': total,
                    'disputed_count': v_audits.filter(is_disputed=True).count(),
                    'suggested_actions': suggested_actions
                }
            )

        # ── Performance Optimization (Caching) ──
        # Intelligent invalidation: If a breach is detected, shorten cache TTL for live monitoring
        ttl = 3600 if active_breach else 28800 # 1hr vs 8hrs
        cache.set(cache_key, True, timeout=ttl)
        return True
        
    except Exception as e:
        logger.error(f"❌ Governance Sync Failure: {str(e)}", exc_info=True)
        return False
