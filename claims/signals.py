from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver

from .models import Claim, ClaimSettlement, ClaimStatusHistory
from .utils import get_claim_subject_user_policy


@receiver(pre_save, sender=Claim)
def capture_old_status(sender, instance, **kwargs):
    """
    Captures the status of the claim before it is saved.
    """
    if instance.pk:
        try:
            old_instance = Claim.objects.get(pk=instance.pk)
            instance._old_status = old_instance.status
        except Claim.DoesNotExist:
            instance._old_status = None
    else:
        instance._old_status = None


@receiver(post_save, sender=Claim)
def track_claim_status_history(sender, instance, created, **kwargs):
    """
    Creates a ClaimStatusHistory record if the status has changed.
    """
    old_status = getattr(instance, '_old_status', None)
    new_status = instance.status

    if not created and old_status != new_status and old_status is not None:
        ClaimStatusHistory.objects.create(
            claim=instance,
            old_status=old_status,
            new_status=new_status,
            changed_by=None,
        )


@receiver(post_save, sender=ClaimSettlement)
def handle_settlement_financials(sender, instance, created, **kwargs):
    """
    Synchronize the exact user-owned policy after claim settlement.
    """
    claim = instance.claim
    user_policy = get_claim_subject_user_policy(claim)
    if not user_policy:
        return

    if created and user_policy.sum_insured_remaining is not None:
        user_policy.sum_insured_remaining = max(
            0,
            user_policy.sum_insured_remaining - instance.settled_amount,
        )
        user_policy.save(update_fields=['sum_insured_remaining'])

    user_policy.sync_status_with_premiums()
