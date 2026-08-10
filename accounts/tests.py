from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from accounts.views import _build_admin_claim_payout_metrics, _build_admin_payment_metrics
from claims.models import Claim, ClaimSettlement
from policy.models import Policy, UserPolicy, Payment


class AdminPaymentMetricsTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username="finance-user",
            password="testpass123",
            role="user",
        )
        self.policy = Policy.objects.create(
            policy_number="POL-FIN01",
            policy_type="health",
            insurer_name="Test Insurer",
            start_date=date.today(),
            end_date=date.today() + timedelta(days=365),
            sum_insured=Decimal("100000.00"),
            status="active",
        )
        self.user_policy = UserPolicy.objects.create(
            user=self.user,
            policy=self.policy,
            certificate_number="CERT-FIN01",
            status="active",
            start_date=self.policy.start_date,
            end_date=self.policy.end_date,
        )

    def test_admin_payment_metrics_only_count_successful_credit_premiums(self):
        Payment.objects.create(
            user=self.user,
            user_policy=self.user_policy,
            amount=Decimal("17700.00"),
            payment_status="completed",
            payment_type="PREMIUM_PAYMENT",
            direction="CREDIT",
            payment_method="upi",
            payment_metadata={"premium_source": "new_policy"},
            description="Activation Payment - POL-FIN01",
        )
        Payment.objects.create(
            user=self.user,
            user_policy=self.user_policy,
            amount=Decimal("1475.00"),
            payment_status="completed",
            payment_type="PREMIUM",
            direction="CREDIT",
            payment_method="upi",
            payment_metadata={"premium_source": "installment"},
            description="Premium Installment #1 - POL-FIN01",
        )
        Payment.objects.create(
            user=self.user,
            user_policy=self.user_policy,
            amount=Decimal("999.00"),
            payment_status="failed",
            payment_type="PREMIUM_PAYMENT",
            direction="CREDIT",
            payment_method="upi",
            description="Failed premium attempt - POL-FIN01",
        )
        Payment.objects.create(
            user=self.user,
            user_policy=self.user_policy,
            amount=Decimal("8000.00"),
            payment_status="completed",
            payment_type="CLAIM_SETTLEMENT",
            direction="DEBIT",
            payment_method="neft",
            description="Claim payout - CLM-0001",
        )

        metrics = _build_admin_payment_metrics()

        self.assertEqual(metrics["premium_collected"], Decimal("19175.00"))
        self.assertEqual(metrics["successful_premium_transactions"], 2)
        self.assertEqual(metrics["premium_collected_new_policies"], Decimal("17700.00"))
        self.assertEqual(metrics["premium_collected_installments"], Decimal("1475.00"))
        self.assertEqual(metrics["failed_premium_transactions"], 1)

    def test_admin_claim_payout_metrics_sum_completed_debit_settlements(self):
        claim = Claim.objects.create(
            policy=self.policy,
            user_policy=self.user_policy,
            claim_number="CLM-FIN01",
            claim_type="medical",
            status="submitted",
            incident_date=date.today(),
            claimed_amount=Decimal("12000.00"),
            deductible_amount=Decimal("1000.00"),
            created_by=self.user,
        )
        claim.status = "settled"
        claim.approved_amount = Decimal("8000.00")
        claim.settled_amount = Decimal("8000.00")
        claim.save(skip_workflow_check=True)

        ClaimSettlement.objects.create(
            claim=claim,
            payment_mode="neft",
            settled_amount=Decimal("8000.00"),
            payee_name="Finance User",
            bank_account="1234567890",
            bank_ifsc="TEST0001234",
            bank_name="Test Bank",
            processed_by=self.user,
        )

        metrics = _build_admin_claim_payout_metrics()

        self.assertEqual(metrics["total_settled_amount"], Decimal("8000.00"))


class AdminDashboardPolicyStatusTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.admin = User.objects.create_user(
            username="dashboard-admin",
            password="adminpass123",
            role="admin",
        )
        self.user = User.objects.create_user(
            username="dashboard-user",
            password="userpass123",
            role="user",
        )
        self.policy = Policy.objects.create(
            policy_number="POL-DASH01",
            policy_type="health",
            insurer_name="Dashboard Insurer",
            start_date=date.today(),
            end_date=date.today() + timedelta(days=365),
            sum_insured=Decimal("250000.00"),
            status="active",
        )
        self.user_policy = UserPolicy.objects.create(
            user=self.user,
            policy=self.policy,
            certificate_number="CERT-DASH01",
            status="approved",
            is_paid=False,
        )

    def test_admin_dashboard_uses_user_policy_status_for_system_policies(self):
        self.client.force_login(self.admin)

        response = self.client.get(reverse("accounts:admin_dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Approved (Awaiting Payment)")
        policies = response.context["policies"]
        self.assertEqual(policies[0].pk, self.user_policy.pk)
