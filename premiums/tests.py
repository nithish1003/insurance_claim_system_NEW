from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from policy.models import Payment, Policy, UserPolicy
from premiums.models import PremiumPayment, PremiumSchedule


class BillingConsoleTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username="billing-user",
            password="testpass123",
            role="user",
        )
        self.other_user = User.objects.create_user(
            username="other-user",
            password="testpass123",
            role="user",
        )

        today = timezone.now().date()

        self.policy = Policy.objects.create(
            policy_number="POL-BILL01",
            policy_type="health",
            insurer_name="Test Insurer",
            start_date=today,
            end_date=today + timedelta(days=365),
            sum_insured=Decimal("250000.00"),
            status="active",
        )
        self.user_policy = UserPolicy.objects.create(
            user=self.user,
            policy=self.policy,
            certificate_number="CERT-BILL01",
            status="active",
            start_date=today,
            end_date=today + timedelta(days=365),
        )
        self.schedule = PremiumSchedule.objects.create(
            user_policy=self.user_policy,
            policy=self.policy,
            base_premium=Decimal("6000.00"),
            gst_percentage=Decimal("18.00"),
            gst_amount=Decimal("1080.00"),
            gross_premium=Decimal("7080.00"),
            payment_frequency="monthly",
            total_installments=12,
            installment_amount=Decimal("590.00"),
            start_date=today,
            end_date=today + timedelta(days=365),
        )
        PremiumPayment.objects.create(
            schedule=self.schedule,
            installment_number=1,
            due_date=today - timedelta(days=3),
            amount=Decimal("590.00"),
            status="upcoming",
        )
        PremiumPayment.objects.create(
            schedule=self.schedule,
            installment_number=2,
            due_date=today + timedelta(days=27),
            amount=Decimal("590.00"),
            status="upcoming",
        )
        PremiumPayment.objects.create(
            schedule=self.schedule,
            installment_number=3,
            due_date=today - timedelta(days=33),
            amount=Decimal("590.00"),
            status="paid",
            paid_date=today - timedelta(days=30),
            transaction_reference="TXN-PAID-001",
        )

        other_policy = Policy.objects.create(
            policy_number="POL-OTHER01",
            policy_type="motor",
            insurer_name="Other Insurer",
            start_date=today,
            end_date=today + timedelta(days=365),
            sum_insured=Decimal("100000.00"),
            status="active",
        )
        other_user_policy = UserPolicy.objects.create(
            user=self.other_user,
            policy=other_policy,
            certificate_number="CERT-OTHER01",
            status="active",
            start_date=today,
            end_date=today + timedelta(days=365),
        )
        other_schedule = PremiumSchedule.objects.create(
            user_policy=other_user_policy,
            policy=other_policy,
            base_premium=Decimal("1200.00"),
            gst_percentage=Decimal("18.00"),
            gst_amount=Decimal("216.00"),
            gross_premium=Decimal("1416.00"),
            payment_frequency="yearly",
            total_installments=1,
            installment_amount=Decimal("1416.00"),
            start_date=today,
            end_date=today + timedelta(days=365),
        )
        PremiumPayment.objects.create(
            schedule=other_schedule,
            installment_number=1,
            due_date=today + timedelta(days=10),
            amount=Decimal("1416.00"),
            status="upcoming",
        )

    def test_dues_summary_api_returns_one_row_per_owned_policy(self):
        self.client.force_login(self.user)

        response = self.client.get("/policies/dues-summary/")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload), 1)
        self.assertEqual(payload[0]["policy_number"], "POL-BILL01")
        self.assertEqual(payload[0]["policy_id"], str(self.user_policy.public_id))
        self.assertEqual(payload[0]["pending_count"], 2)
        self.assertEqual(payload[0]["next_due_amount"], 590.0)

    def test_policy_dues_api_returns_sorted_installments_for_only_requested_users_policy(self):
        self.client.force_login(self.user)

        response = self.client.get(f"/policy/{self.user_policy.public_id}/dues/")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual([row["installment_number"] for row in payload], [3, 1, 2])
        self.assertEqual(payload[0]["status"], "PAID")
        self.assertEqual(payload[1]["status"], "OVERDUE")
        self.assertEqual(payload[2]["status"], "UPCOMING")

    def test_policy_dues_detail_shows_pay_now_only_for_unpaid_rows(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("premiums:policy_dues_detail", args=[self.user_policy.public_id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Pay Now", count=2)
        self.assertContains(response, "Paid")

    def test_first_installment_payment_activates_approved_policy(self):
        today = timezone.now().date()
        self.user_policy.status = "approved"
        self.user_policy.is_paid = False
        self.user_policy.start_date = today
        self.user_policy.end_date = today + timedelta(days=365)
        self.user_policy.save(update_fields=["status", "is_paid", "start_date", "end_date"])

        first_due = self.schedule.payments.get(installment_number=1)
        first_due.status = "upcoming"
        first_due.paid_date = None
        first_due.transaction_reference = ""
        first_due.save(update_fields=["status", "paid_date", "transaction_reference"])

        self.client.force_login(self.user)
        response = self.client.post(reverse("premiums:pay", args=[first_due.public_id]))

        self.assertEqual(response.status_code, 302)
        self.user_policy.refresh_from_db()

        self.assertTrue(self.user_policy.is_paid)
        self.assertEqual(self.user_policy.status, "active")
        self.assertTrue(
            Payment.objects.filter(
                user_policy=self.user_policy,
                payment_status="completed",
                direction="CREDIT",
                payment_type="PREMIUM_PAYMENT",
            ).exists()
        )
