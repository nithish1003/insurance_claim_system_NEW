"""
Data Migration: Migrate legacy ai_predicted_amount values to versioned payout fields.

Rules:
1. Copy ai_predicted_amount → initial_ai_prediction (if final_ai_recommendation is empty)
2. Compute final_ai_recommendation using authoritative formula
3. Preserve original ai_predicted_amount for rollback safety (do NOT null it)
"""

from django.db import migrations
from decimal import Decimal


def migrate_legacy_predictions(apps, schema_editor):
    """
    Forward migration: Populate versioned payout fields from legacy data.
    """
    Claim = apps.get_model('claims', 'Claim')
    
    claims = Claim.objects.filter(
        final_ai_recommendation__isnull=True,
    ).exclude(
        claimed_amount__isnull=True,
    )
    
    updated_count = 0
    for claim in claims.iterator(chunk_size=500):
        # 1. Archive legacy value as initial estimate
        if claim.ai_predicted_amount and not claim.initial_ai_prediction:
            claim.initial_ai_prediction = claim.ai_predicted_amount
        
        # 2. Compute authoritative final recommendation
        claimed = Decimal(str(claim.claimed_amount or 0))
        deductible = Decimal(str(claim.deductible_amount or 0))
        net = max(Decimal('0'), claimed - deductible)
        risk_pct = Decimal(str(claim.risk_score or 0)) / Decimal('100')
        computed = (net - (net * risk_pct)).quantize(Decimal('0.01'))
        
        claim.final_ai_recommendation = computed
        claim.ai_engine_version = "v2.0-migrated"
        
        claim.save(update_fields=[
            'initial_ai_prediction',
            'final_ai_recommendation',
            'ai_engine_version',
        ])
        updated_count += 1
    
    if updated_count:
        print(f"\n    [SUCCESS] Migrated {updated_count} claims to versioned payout architecture.")


def reverse_migration(apps, schema_editor):
    """
    Reverse migration: Clear versioned fields (legacy ai_predicted_amount is preserved).
    """
    Claim = apps.get_model('claims', 'Claim')
    Claim.objects.filter(
        ai_engine_version="v2.0-migrated"
    ).update(
        initial_ai_prediction=None,
        final_ai_recommendation=None,
        ai_engine_version="v2.0",
    )
    print("\n    [REVERSE] Reversed versioned payout migration.")


class Migration(migrations.Migration):

    dependencies = [
        ('claims', '0047_versioned_payout_architecture'),
    ]

    operations = [
        migrations.RunPython(
            migrate_legacy_predictions,
            reverse_code=reverse_migration,
        ),
    ]
