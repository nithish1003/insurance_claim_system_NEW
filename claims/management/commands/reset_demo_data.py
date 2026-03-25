from django.core.management.base import BaseCommand
from django.db import transaction
from django.contrib.auth import get_user_model

from claims.models import (
    Claim,
    ClaimDocument,
    ClaimNote,
    ClaimAssessment,
    ClaimSettlement,
    ClaimAuditLog,
    Claimant,
)
from premiums.models import PremiumSchedule, PremiumPayment
from policy.models import Policy, PolicyHolder, UserProfile


class Command(BaseCommand):
    help = "Delete demo data while preserving schema (keeps superusers)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--include-superusers",
            action="store_true",
            help="Also delete superuser accounts.",
        )

    def handle(self, *args, **options):
        include_superusers = options.get("include_superusers", False)

        deletions = [
            ("ClaimDocument", ClaimDocument.objects.all()),
            ("ClaimNote", ClaimNote.objects.all()),
            ("ClaimAssessment", ClaimAssessment.objects.all()),
            ("ClaimSettlement", ClaimSettlement.objects.all()),
            ("ClaimAuditLog", ClaimAuditLog.objects.all()),
            ("Claimant", Claimant.objects.all()),
            ("Claim", Claim.objects.all()),
            ("PremiumPayment", PremiumPayment.objects.all()),
            ("PremiumSchedule", PremiumSchedule.objects.all()),
            ("Policy", Policy.objects.all()),
            ("PolicyHolder", PolicyHolder.objects.all()),
            ("UserProfile", UserProfile.objects.all()),
        ]

        User = get_user_model()
        user_qs = User.objects.all()
        if not include_superusers:
            user_qs = user_qs.filter(is_superuser=False)
        deletions.append(("User", user_qs))

        results = []
        with transaction.atomic():
            for label, qs in deletions:
                count = qs.delete()[0]
                results.append((label, count))

        self.stdout.write(self.style.SUCCESS("Data reset complete. Deleted rows:"))
        for label, count in results:
            self.stdout.write(f"- {label}: {count}")
