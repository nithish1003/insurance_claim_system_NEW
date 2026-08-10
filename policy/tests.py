from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.urls import reverse
from django.test import TestCase

from claims.models import Claim
from notifications.models import Notification
from policy.models import Payment, Policy, PolicyApplication, UserPolicy
from policy.views import _approve_policy_application


class UserPolicyCoverageTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="coverage-user",
            password="testpass123",
        )
        self.policy = Policy.objects.create(
            policy_number="POL-TEST01",
            policy_type="health",
            insurer_name="Test Insurer",
            start_date=date.today(),
            end_date=date.today() + timedelta(days=365),
            sum_insured=Decimal("500000.00"),
            status="active",
        )
        self.user_policy = UserPolicy.objects.create(
            user=self.user,
            policy=self.policy,
            certificate_number="CERT-TEST01",
            status="active",
            start_date=self.policy.start_date,
            end_date=self.policy.end_date,
            sum_insured_remaining=Decimal("500000.00"),
        )

    def test_sync_status_recalculates_remaining_from_approved_claims(self):
        claim = Claim.objects.create(
            policy=self.policy,
            claim_number="CLM-TEST01",
            claim_type="medical",
            status="submitted",
            incident_date=date.today(),
            claimed_amount=Decimal("50000.00"),
            created_by=self.user,
        )
        claim.status = "approved"
        claim.approved_amount = Decimal("30000.00")
        claim.save(skip_workflow_check=True)

        self.user_policy.sync_status_with_premiums()
        self.user_policy.refresh_from_db()

        self.assertEqual(self.user_policy.total_settled_amount, Decimal("30000.00"))
        self.assertEqual(self.user_policy.sum_insured_remaining, Decimal("470000.00"))
        self.assertEqual(self.user_policy.remaining_sum_insured, Decimal("470000.00"))

    def test_coverage_usage_percentage_uses_approved_amount(self):
        claim = Claim.objects.create(
            policy=self.policy,
            claim_number="CLM-TEST02",
            claim_type="medical",
            status="submitted",
            incident_date=date.today(),
            claimed_amount=Decimal("50000.00"),
            created_by=self.user,
        )
        claim.status = "approved"
        claim.approved_amount = Decimal("30000.00")
        claim.save(skip_workflow_check=True)

        self.assertAlmostEqual(self.user_policy.coverage_usage_percentage, 6.0, places=2)

    def test_core_policy_records_generate_public_uuids(self):
        self.assertIsNotNone(self.policy.public_id)
        self.assertIsNotNone(self.user_policy.public_id)


class PolicyApplicationSubmissionTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.admin = User.objects.create_user(
            username="admin-user",
            password="adminpass123",
            role="admin",
        )
        self.user = User.objects.create_user(
            username="applicant-user",
            password="userpass123",
            role="user",
        )
        self.policy = Policy.objects.create(
            policy_number="POL-TEST02",
            policy_type="health",
            insurer_name="Test Insurer",
            start_date=date.today(),
            end_date=date.today() + timedelta(days=365),
            sum_insured=Decimal("200000.00"),
            base_premium=Decimal("6000.00"),
            admin_premium_percent=Decimal("6.00"),
            status="active",
        )

    def test_buy_policy_creates_pending_application_with_locked_premium_and_admin_notification(self):
        self.client.force_login(self.user)

        response = self.client.post(reverse("policy:buy_policy", args=[self.policy.public_id]))

        self.assertEqual(response.status_code, 201)
        self.assertEqual(PolicyApplication.objects.filter(user=self.user, policy=self.policy, status="pending").count(), 1)
        user_policy = UserPolicy.objects.get(user=self.user, policy=self.policy)
        self.assertEqual(user_policy.status, "pending")
        self.assertFalse(user_policy.is_paid)
        self.assertEqual(user_policy.final_premium, Decimal("6360.00"))
        self.assertTrue(
            Notification.objects.filter(
                user=self.admin,
                title="New Policy Application",
                message__icontains=self.policy.policy_number,
            ).exists()
        )

    def test_admin_approval_preserves_locked_premium_from_application_time(self):
        self.client.force_login(self.user)
        self.client.post(reverse("policy:buy_policy", args=[self.policy.public_id]))

        user_policy = UserPolicy.objects.get(user=self.user, policy=self.policy)
        application = PolicyApplication.objects.get(user=self.user, policy=self.policy)

        self.policy.base_premium = Decimal("9000.00")
        self.policy.admin_premium_percent = Decimal("10.00")
        self.policy.save(update_fields=["base_premium", "admin_premium_percent"])

        _approve_policy_application(application, self.admin, "Approved for payment")
        user_policy.refresh_from_db()
        application.refresh_from_db()

        self.assertEqual(application.status, "approved")
        self.assertEqual(user_policy.status, "approved")
        self.assertEqual(user_policy.final_premium, Decimal("6360.00"))

    def test_admin_approval_keeps_policy_awaiting_payment_until_paid(self):
        self.client.force_login(self.user)
        self.client.post(reverse("policy:buy_policy", args=[self.policy.public_id]))

        application = PolicyApplication.objects.get(user=self.user, policy=self.policy)
        user_policy = UserPolicy.objects.get(user=self.user, policy=self.policy)

        _approve_policy_application(application, self.admin, "Approved for payment")
        user_policy.refresh_from_db()

        self.assertEqual(user_policy.status, "approved")
        self.assertFalse(user_policy.is_paid)
        self.assertEqual(user_policy.payment_status, "Pending")
        self.assertEqual(user_policy.admin_status_label, "Approved (Awaiting Payment)")
        self.assertEqual(user_policy.admin_status_tone, "status-awaiting-payment")

    def test_make_payment_uses_locked_user_policy_premium_and_activates_policy(self):
        self.client.force_login(self.user)
        self.client.post(reverse("policy:buy_policy", args=[self.policy.public_id]))

        application = PolicyApplication.objects.get(user=self.user, policy=self.policy)
        user_policy = UserPolicy.objects.get(user=self.user, policy=self.policy)
        _approve_policy_application(application, self.admin, "Approved for payment")

        self.policy.base_premium = Decimal("12000.00")
        self.policy.admin_premium_percent = Decimal("20.00")
        self.policy.save(update_fields=["base_premium", "admin_premium_percent"])

        response = self.client.post(reverse("policy:make_payment", args=[user_policy.public_id]))

        self.assertEqual(response.status_code, 200)
        user_policy.refresh_from_db()
        payment = Payment.objects.get(user_policy=user_policy)

        self.assertTrue(user_policy.is_paid)
        self.assertEqual(user_policy.status, "active")
        self.assertEqual(payment.amount, Decimal("6360.00"))
        self.assertEqual(payment.direction, "CREDIT")
        self.assertEqual(payment.payment_status, "completed")
        self.assertIsNotNone(payment.public_id)

    def test_sync_status_with_completed_premium_activates_stale_approved_policy(self):
        user_policy = UserPolicy.objects.create(
            user=self.user,
            policy=self.policy,
            certificate_number="CERT-STUCK01",
            status="approved",
            is_paid=False,
            start_date=date.today(),
            end_date=date.today() + timedelta(days=365),
            final_premium=Decimal("6360.00"),
        )
        Payment.objects.create(
            user=self.user,
            user_policy=user_policy,
            amount=Decimal("590.00"),
            payment_status="completed",
            payment_type="PREMIUM_PAYMENT",
            direction="CREDIT",
            payment_method="upi",
            payment_metadata={"premium_source": "installment"},
            description=f"Premium Installment #1 - {self.policy.policy_number}",
        )

        user_policy.sync_status_with_premiums()
        user_policy.refresh_from_db()

        self.assertTrue(user_policy.is_paid)
        self.assertEqual(user_policy.status, "active")

    def test_admin_policy_list_shows_awaiting_payment_for_unpaid_approved_policy(self):
        self.client.force_login(self.user)
        self.client.post(reverse("policy:buy_policy", args=[self.policy.public_id]))

        application = PolicyApplication.objects.get(user=self.user, policy=self.policy)
        _approve_policy_application(application, self.admin, "Approved for payment")

        active_policy = Policy.objects.create(
            policy_number="POL-ACTIVE01",
            policy_type="health",
            insurer_name="Legacy Insurer",
            start_date=date.today(),
            end_date=date.today() + timedelta(days=365),
            sum_insured=Decimal("150000.00"),
            base_premium=Decimal("5000.00"),
            admin_premium_percent=Decimal("5.00"),
            status="active",
        )
        UserPolicy.objects.create(
            user=self.user,
            policy=active_policy,
            certificate_number="CERT-ACTIVE01",
            status="active",
            is_paid=True,
            start_date=date.today(),
            end_date=date.today() + timedelta(days=365),
        )

        self.client.force_login(self.admin)
        response = self.client.get(reverse("policy:admin_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Approved (Awaiting Payment)")
        self.assertNotContains(response, "POL-ACTIVE01")
