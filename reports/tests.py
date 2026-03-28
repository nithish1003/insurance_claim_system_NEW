from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from claims.models import Claim
from policy.models import Payment, Policy, UserPolicy
from reports.models import ActivityLog


class ReportsActivityApiTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="admin_reports",
            password="pass12345",
            role="admin",
        )
        self.policyholder = User.objects.create_user(
            username="pay_user",
            password="pass12345",
            role="user",
            first_name="Pay",
            last_name="User",
        )

        today = timezone.now().date()
        self.policy = Policy.objects.create(
            policy_number="POL-SEARCH-001",
            policy_type="Health",
            status="active",
            start_date=today,
            end_date=today + timedelta(days=365),
            sum_insured=Decimal("500000.00"),
        )
        self.user_policy = UserPolicy.objects.create(
            user=self.policyholder,
            policy=self.policy,
            certificate_number="CERT-SEARCH-001",
            start_date=today,
            end_date=today + timedelta(days=365),
            status="active",
        )

        self.payment = Payment.objects.create(
            user=self.policyholder,
            user_policy=self.user_policy,
            amount=Decimal("12500.00"),
            payment_status="completed",
            payment_type="PREMIUM_PAYMENT",
            direction="CREDIT",
            payment_method="upi",
            gateway_reference="UPI-REF-9911",
            description="Quarterly premium collection",
        )
        self.claim = Claim.objects.create(
            policy=self.policy,
            user_policy=self.user_policy,
            claim_number="CLM-REPORT-1001",
            claim_type="medical",
            status="submitted",
            incident_date=today,
            claimed_amount=Decimal("20000.00"),
        )
        self.claim_payment = Payment.objects.create(
            user=self.policyholder,
            user_policy=self.user_policy,
            claim=self.claim,
            amount=Decimal("8000.00"),
            payment_status="completed",
            payment_type="CLAIM_SETTLEMENT",
            direction="DEBIT",
            payment_method="upi",
            gateway_reference="SETL-REF-1001",
            description="Claim payout settlement",
        )
        ActivityLog.objects.create(
            title="AI Audit Complete: CLM-REPORT-01",
            description="Claim review completed successfully.",
            log_type="claim",
            status="success",
            user=self.admin,
        )

        self.client.force_login(self.admin)

    def test_payment_filter_uses_payment_ledger_entries(self):
        response = self.client.get(reverse("reports:api_activity"), {"type": "payment"})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload["data"]), 1)
        self.assertEqual(payload["data"][0]["type"], "payment")
        self.assertIn(self.policy.policy_number, payload["data"][0]["description"])
        self.assertIn(self.payment.transaction_id, payload["data"][0]["description"])
        self.assertNotIn(self.claim_payment.transaction_id, payload["data"][0]["description"])

    def test_payment_search_matches_transaction_and_policy_details(self):
        response = self.client.get(
            reverse("reports:api_activity"),
            {"type": "payment", "q": self.payment.transaction_id[-6:]},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload["data"]), 1)
        self.assertEqual(payload["data"][0]["type"], "payment")

        response = self.client.get(
            reverse("reports:api_activity"),
            {"type": "payment", "q": self.policy.policy_number},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload["data"]), 1)
        self.assertEqual(payload["data"][0]["user"], self.policyholder.username)
