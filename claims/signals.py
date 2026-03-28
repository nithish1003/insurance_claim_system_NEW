from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver
from .models import Claim, ClaimStatusHistory, ClaimSettlement
from policy.models import UserPolicy

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

    # Only track if it's an update and status has actually changed
    if not created and old_status != new_status and old_status is not None:
        ClaimStatusHistory.objects.create(
            claim=instance,
            old_status=old_status,
            new_status=new_status,
            changed_by=None # Left null as standard signals lack request context
        )

@receiver(post_save, sender=ClaimSettlement)
def handle_settlement_financials(sender, instance, created, **kwargs):
    """
    Requirement 4: Automatically trigger policy status sync upon settlement.
    The remaining_sum_insured property in UserPolicy dynamically calculates 
    balance, but this signal ensures the policy status (e.g. Expired) 
    is synchronized if coverage is exhausted.
    """
    claim = instance.claim
    # Link to the user policy that matches this claimant and policy plan
    try:
        user_policy = UserPolicy.objects.get(user=claim.created_by, policy=claim.policy)
        
        if created:
            # 💸 Financial Deduction: Reduce the persistent balance field
            if user_policy.sum_insured_remaining is not None:
                user_policy.sum_insured_remaining = max(0, user_policy.sum_insured_remaining - instance.settled_amount)
                user_policy.save(update_fields=['sum_insured_remaining'])
        
        user_policy.sync_status_with_premiums()
    except (UserPolicy.DoesNotExist, UserPolicy.MultipleObjectsReturned):
        # Heuristic failed: possibly a third party claim or multi-owner policy
        pass
