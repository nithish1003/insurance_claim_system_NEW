from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth import get_user_model
from claims.models import Claim
from accounts.models import AadhaarKYCVerification
from premiums.models import PremiumPayment
from policy.models import UserPolicy
try:
    from assistant.models import SupportTicket
except ImportError:
    SupportTicket = None
from .models import Notification
from .services import NotificationService

User = get_user_model()

@receiver(post_save, sender=Claim)
def claim_status_notification(sender, instance, created, **kwargs):
    """Triggers multi-channel alerts for Claim events."""
    if kwargs.get("raw", False):
        return
    if created:
        auditors = User.objects.filter(role__in=['admin', 'staff'])
        for auditor in auditors:
            notif = Notification.objects.create(
                user=auditor,
                title="New Claim Submitted",
                message=f"Claim {instance.claim_number} pending review from {instance.created_by.username if instance.created_by else 'Unknown'}.",
                type='info',
                role_target='staff',
                related_claim_id=instance.public_id
            )
            NotificationService.notify_user(notif)
    else:
        # PUSH to User if Approved/Rejected/Settled
        if instance.status in ['approved', 'rejected', 'settled']:
            if instance.created_by:
                titles = {'approved': 'Claim Approved 🎉', 'rejected': 'Claim Rejected ⚠️', 'settled': 'Settlement Credited 💰'}
                types = {'approved': 'success', 'rejected': 'error', 'settled': 'success'}
                
                notif = Notification.objects.create(
                    user=instance.created_by,
                    title=titles.get(instance.status, 'Claim Update'),
                    message=f"Update on claim #{instance.claim_number}: Status changed to {instance.status.upper()}.",
                    type=types.get(instance.status, 'info'),
                    role_target='policyholder',
                    related_claim_id=instance.public_id
                )
                NotificationService.notify_user(notif)

@receiver(post_save, sender=AadhaarKYCVerification)
def kyc_alert_signal(sender, instance, created, **kwargs):
    """Triggers alerts for KYC status changes."""
    if kwargs.get("raw", False):
        return
    if not created and instance.user:
        status_map = {
            'verified': ('KYC Verified ✅', 'Identity validation successful. Your profile is now elite.', 'success'),
            'rejected': ('KYC Rejected ❌', 'Verification failed. Please re-submit valid documents.', 'error'),
            'manual_review': ('KYC Pending ⏳', 'Your documents are being manually vetted by our security team.', 'warning')
        }
        
        if instance.status in status_map:
            title, msg, n_type = status_map[instance.status]
            notif = Notification.objects.create(
                user=instance.user,
                title=title,
                message=msg,
                type=n_type,
                role_target='policyholder'
            )
            NotificationService.notify_user(notif)

@receiver(post_save, sender=PremiumPayment)
def payment_alert_signal(sender, instance, created, **kwargs):
    """Triggers alerts for Premium Payment statuses."""
    if kwargs.get("raw", False):
        return
    if not created and instance.schedule.user_policy.user:
        user = instance.schedule.user_policy.user
        if instance.status == 'paid':
            # 🛡️ Deduplication: Avoid duplicate payment alerts for the same installment
            exists = Notification.objects.filter(
                user=user,
                title__icontains="Payment Received",
                message__icontains=f"installment #{instance.installment_number}",
                is_cleared=False
            ).exists()

            if not exists:
                notif = Notification.objects.create(
                    user=user,
                    title="Payment Received 💸",
                    message=f"Premium installment #{instance.installment_number} for Policy {instance.schedule.user_policy.certificate_number} was successful.",
                    type='success',
                    role_target='policyholder'
                )
                NotificationService.notify_user(notif)
        elif instance.status == 'overdue':
            # 🛡️ Deduplication: Avoid duplicate alerts for the same installment
            exists = Notification.objects.filter(
                user=user, 
                related_payment_id=instance.public_id,
                type='error',
                is_cleared=False
            ).exists()
            
            if not exists:
                due_date_str = instance.due_date.strftime('%d %b, %Y')
                notif = Notification.objects.create(
                    user=user,
                    title="Premium Overdue! 🚨",
                    message=f"Premium overdue since {due_date_str}. Pay now to avoid interruption of coverage.",
                    type='error',
                    role_target='policyholder',
                    related_payment_id=instance.public_id
                )
                NotificationService.notify_user(notif)

        elif instance.status == 'lapsed':
            # 🛡️ Deduplication: Avoid duplicate lapse alerts
            exists = Notification.objects.filter(
                user=user, 
                related_payment_id=instance.public_id,
                title__icontains="Lapsed",
                is_cleared=False
            ).exists()
            
            if not exists:
                cert = instance.schedule.user_policy.certificate_number if instance.schedule.user_policy else 'your policy'
                notif = Notification.objects.create(
                    user=user,
                    title="Policy Lapsed! ⚠️",
                    message=f"Coverage for {cert} has lapsed due to non-payment. Pay now to reinstate.",
                    type='error',
                    role_target='policyholder',
                    related_payment_id=instance.public_id
                )
                NotificationService.notify_user(notif)

@receiver(post_save, sender=UserPolicy)
def policy_activation_signal(sender, instance, created, **kwargs):
    """Triggers alert when a policy is activated."""
    if kwargs.get("raw", False):
        return
    if not created and instance.status == 'active' and instance.user:
        # 🛡️ Deduplication: Avoid duplicate activation alerts for the same certificate
        exists = Notification.objects.filter(
            user=instance.user,
            title__icontains="Policy Activated!",
            message__icontains=instance.certificate_number,
            is_cleared=False
        ).exists()

        if not exists:
            notif = Notification.objects.create(
                user=instance.user,
                title="Policy Activated! 🛡️",
                message=f"Coverage for {instance.certificate_number} is now live. Safe travels!",
                type='success',
                role_target='policyholder'
            )
            NotificationService.notify_user(notif)

if SupportTicket:
    @receiver(post_save, sender=SupportTicket)
    def support_ticket_notification(sender, instance, created, **kwargs):
        """Triggers alerts for Support Ticket lifecycles."""
        if kwargs.get("raw", False):
            return
        if created:
            # Notify Staff
            staff_users = User.objects.filter(role__in=['admin', 'staff'])
            for staff in staff_users:
                notif = Notification.objects.create(
                    user=staff,
                    title="New Support Ticket 🎟️",
                    message=f"Ticket {instance.ticket_id}: '{instance.subject}' submitted by {instance.user.username}.",
                    type='info',
                    role_target='staff'
                )
                NotificationService.notify_user(notif)
            # Notify User
            notif = Notification.objects.create(
                user=instance.user,
                title="Support Ticket Created",
                message=f"Your request '{instance.subject}' has been registered as Ticket {instance.ticket_id}. We'll get back to you shortly.",
                type='success',
                role_target='policyholder'
            )
            NotificationService.notify_user(notif)
        else:
            # Notify User if status changed
            if instance.status in ['in_progress', 'resolved', 'closed']:
                titles = {
                    'in_progress': 'Ticket In Progress ⚙️',
                    'resolved': 'Ticket Resolved ✅',
                    'closed': 'Ticket Closed 📁'
                }
                notif = Notification.objects.create(
                    user=instance.user,
                    title=titles.get(instance.status, 'Ticket Update'),
                    message=f"Your Ticket {instance.ticket_id} status has been updated to {instance.status.upper()}.",
                    type='success' if instance.status == 'resolved' else 'info',
                    role_target='policyholder'
                )
                NotificationService.notify_user(notif)
