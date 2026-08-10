from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from django.contrib.auth import get_user_model
from claims.models import Claim
from policy.models import UserPolicy
from notifications.models import Notification
from notifications.utils import create_notification
from notifications.services import NotificationService

User = get_user_model()

class Command(BaseCommand):
    help = 'Processes periodic notifications: Expiry alerts, Overdue claims, and Cleanup.'

    def handle(self, *args, **options):
        self.stdout.write("🚀 Starting notification processing job...")
        
        # 1. CLEANUP: Delete expired notifications
        expired = Notification.objects.filter(expires_at__lt=timezone.now())
        count, _ = expired.delete()
        self.stdout.write(self.style.SUCCESS(f"🧹 Cleaned up {count} expired notifications."))

        # 2. OVERDUE CLAIMS: Daily alerts for Admin/Staff
        # Target: Claims in queue for > 7 days
        overdue_threshold = timezone.now() - timedelta(days=7)
        overdue_claims = Claim.objects.filter(
            status__in=['submitted', 'under_review', 'investigation', 'staff_reviewed'],
            reported_date__lt=overdue_threshold
        )
        
        if overdue_claims.exists():
            auditors = User.objects.filter(role__in=['admin', 'staff'])
            for auditor in auditors:
                for claim in overdue_claims:
                    # Avoid duplicate notifications for the same claim on the same day if possible
                    # Simple check: No unread 'SLA' notification for this claim
                    if not Notification.objects.filter(user=auditor, is_read=False, title__contains=claim.claim_number).exists():
                        notif = create_notification(
                            user=auditor,
                            title=f"SLA BREACH: Claim {claim.claim_number}",
                            message=f"Dossier {claim.claim_number} has been pending for over 7 days. Escalation required.",
                            type='error',
                            role_target='staff',
                            related_claim_id=claim.public_id
                        )
                        NotificationService.notify_user(notif)
            self.stdout.write(self.style.SUCCESS(f"⚠️ Processed SLA alerts for {overdue_claims.count()} claims."))

        # 3. POLICY EXPIRY: 7 days before alert
        expiry_date = (timezone.now() + timedelta(days=7)).date()
        expiring_policies = UserPolicy.objects.filter(end_date=expiry_date, status='active')
        
        for up in expiring_policies:
            if not Notification.objects.filter(user=up.user, title__contains="Policy Expiry").exists():
                create_notification(
                    user=up.user,
                    title="Action Required: Policy Expiry Notice",
                    message=f"Your policy {up.certificate_number} will expire in 7 days on {up.end_date}. Renew now to maintain coverage.",
                    type='warning',
                    role_target='policyholder'
                )
        self.stdout.write(self.style.SUCCESS(f"🔔 Dispatched {expiring_policies.count()} expiry warnings."))

        self.stdout.write(self.style.SUCCESS("✅ Periodic processing complete."))
