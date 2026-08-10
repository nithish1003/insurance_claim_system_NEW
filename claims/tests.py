from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile
from unittest.mock import patch

from claims.models import Claim
from policy.models import Policy, UserPolicy
from accounts.models import UserProfile
from notifications.models import Notification


class ClaimIsolationTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.old_user = User.objects.create_user(
            username="old-policyholder",
            password="testpass123",
            role="user",
        )
        self.new_user = User.objects.create_user(
            username="new-policyholder",
            password="testpass123",
            role="user",
        )
        self.policy = Policy.objects.create(
            policy_number="POL-HEALTH01",
            policy_type="health",
            insurer_name="Health Insurer",
            start_date=date.today(),
            end_date=date.today() + timedelta(days=365),
            sum_insured=Decimal("500000.00"),
            deductible=Decimal("1000.00"),
            status="active",
        )
        self.old_user_policy = UserPolicy.objects.create(
            user=self.old_user,
            policy=self.policy,
            certificate_number="CERT-OLD001",
            status="active",
            is_paid=True,
            start_date=date.today() - timedelta(days=30),
            end_date=date.today() + timedelta(days=335),
            sum_insured_remaining=Decimal("500000.00"),
        )
        self.new_user_policy = UserPolicy.objects.create(
            user=self.new_user,
            policy=self.policy,
            certificate_number="CERT-NEW001",
            status="active",
            is_paid=True,
            start_date=date.today() - timedelta(days=10),
            end_date=date.today() + timedelta(days=355),
            sum_insured_remaining=Decimal("500000.00"),
        )
        self.claim = Claim.objects.create(
            policy=self.policy,
            user_policy=self.old_user_policy,
            claim_number="CLM-HEALTH01",
            claim_type="medical",
            status="submitted",
            incident_date=date.today() - timedelta(days=5),
            claimed_amount=Decimal("25000.00"),
            deductible_amount=Decimal("1000.00"),
            created_by=self.old_user,
        )
        self.claim.status = "settled"
        self.claim.approved_amount = Decimal("20000.00")
        self.claim.settled_amount = Decimal("20000.00")
        self.claim.save(skip_workflow_check=True)

    def test_user_policy_balance_stays_isolated_per_policyholder(self):
        self.assertEqual(self.old_user_policy.total_settled_amount, Decimal("20000.00"))
        self.assertEqual(self.new_user_policy.total_settled_amount, Decimal("0.00"))
        self.assertEqual(self.new_user_policy.remaining_sum_insured, Decimal("500000.00"))

    def test_claim_list_hides_other_policyholders_claims_on_same_policy_plan(self):
        self.client.force_login(self.new_user)

        response = self.client.get(reverse("claim:list"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "CLM-HEALTH01")

    def test_policyholder_dashboard_does_not_count_other_policyholders_claims(self):
        self.client.force_login(self.new_user)

        response = self.client.get(reverse("accounts:policyholder_dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["kpi"]["total_claims"], 0)
        self.assertEqual(response.context["kpi"]["total_settled"], 0)

    def test_claim_detail_uses_public_uuid_for_owned_claim(self):
        self.client.force_login(self.old_user)

        response = self.client.get(reverse("claim:detail", args=[self.claim.public_id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.claim.claim_number)

    def test_invalid_uuid_claim_path_returns_404(self):
        self.client.force_login(self.old_user)

        response = self.client.get("/claims/00000000-0000-0000-0000-000000000000/")

        self.assertEqual(response.status_code, 404)


class ClaimSubmissionNotificationTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username="notify-user",
            password="testpass123",
            role="user",
        )
        self.staff = User.objects.create_user(
            username="notify-staff",
            password="testpass123",
            role="staff",
        )
        self.policy = Policy.objects.create(
            policy_number="POL-NOTIFY01",
            policy_type="travel",
            insurer_name="Notify Insurer",
            start_date=date.today() - timedelta(days=5),
            end_date=date.today() + timedelta(days=360),
            sum_insured=Decimal("200000.00"),
            deductible=Decimal("500.00"),
            status="active",
        )
        self.user_policy = UserPolicy.objects.create(
            user=self.user,
            policy=self.policy,
            certificate_number="CERT-NOTIFY01",
            status="active",
            is_paid=True,
            start_date=date.today() - timedelta(days=5),
            end_date=date.today() + timedelta(days=360),
            sum_insured_remaining=Decimal("200000.00"),
        )
        UserProfile.objects.create(
            user=self.user,
            full_name="Notify User",
            aadhaar_number="123456789012",
            id_proof=SimpleUploadedFile("id-proof.txt", b"proof"),
            is_verified=True,
            verification_status="VERIFIED",
        )

    @patch("claims.views.run_intelligence_pipeline", return_value=False)
    def test_claim_submission_creates_policyholder_notification(self, _mock_pipeline):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("claim:create"),
            {
                "policy": str(self.policy.public_id),
                "description": "Travel baggage was lost during transit.",
                "incident_date": (date.today() - timedelta(days=1)).isoformat(),
                "claimed_amount": "15000.00",
                "aadhaar_number": "123456789012",
            },
        )

        self.assertEqual(response.status_code, 302)
        claim = Claim.objects.get(created_by=self.user)
        notification = Notification.objects.get(user=self.user, related_entity_id=claim.public_id)

        self.assertEqual(notification.notification_type, "claim")
        self.assertEqual(notification.status, "unread")
        self.assertIn(claim.claim_number, notification.message)
