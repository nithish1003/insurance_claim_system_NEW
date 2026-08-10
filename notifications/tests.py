import uuid
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.messages.storage.fallback import FallbackStorage
from django.test import RequestFactory, TestCase

from claims.models import Claim
from notifications.models import Notification
from notifications.views import (
    clear_orphaned_claim_notifications,
    notification_redirect,
)
from policy.models import Policy, UserPolicy


class NotificationClaimRedirectTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.admin = User.objects.create_user(
            username="claim-admin",
            password="testpass123",
            role="admin",
            is_staff=True,
            is_superuser=True,
        )
        self.policyholder = User.objects.create_user(
            username="claim-owner",
            password="testpass123",
            role="user",
        )
        self.policy = Policy.objects.create(
            policy_number="POL-NOTIF01",
            policy_type="health",
            insurer_name="Notify Insurer",
            start_date=date.today(),
            end_date=date.today() + timedelta(days=365),
            sum_insured=Decimal("500000.00"),
            deductible=Decimal("1000.00"),
            status="active",
        )
        self.user_policy = UserPolicy.objects.create(
            user=self.policyholder,
            policy=self.policy,
            certificate_number="CERT-NOTIF01",
            status="active",
            is_paid=True,
            start_date=date.today(),
            end_date=date.today() + timedelta(days=365),
            sum_insured_remaining=Decimal("500000.00"),
        )
        self.factory = RequestFactory()

    def _request(self, notification):
        request = self.factory.get(f"/notifications/redirect/{notification.id}/")
        request.user = self.admin
        request.session = {}
        request._messages = FallbackStorage(request)
        return request

    def test_redirect_resolves_claim_from_message_when_stored_uuid_is_stale(self):
        claim = Claim.objects.create(
            policy=self.policy,
            user_policy=self.user_policy,
            claim_number="CLM-NOTIF-0001",
            claim_type="medical",
            status="submitted",
            incident_date=date.today(),
            claimed_amount=Decimal("25000.00"),
            created_by=self.policyholder,
        )
        notification = Notification.objects.create(
            user=self.admin,
            title="New Claim Submitted",
            message="Claim CLM-NOTIF-0001 pending review from claim-owner.",
            related_claim_id=uuid.uuid4(),
        )

        response = notification_redirect(self._request(notification), notification.id)

        self.assertEqual(response.status_code, 302)
        self.assertIn(f"/claim/review/{claim.public_id}/", response.url)
        notification.refresh_from_db()
        self.assertEqual(notification.related_claim_id, claim.public_id)

    def test_orphaned_claim_notifications_are_cleared_from_queryset(self):
        notification = Notification.objects.create(
            user=self.admin,
            title="New Claim Submitted",
            message="Claim CLM-MISSING-0001 pending review from claim-owner.",
            related_claim_id=uuid.uuid4(),
        )

        queryset = Notification.objects.filter(user=self.admin, is_cleared=False)
        filtered = clear_orphaned_claim_notifications(queryset)

        self.assertNotIn(notification, list(filtered))
        notification.refresh_from_db()
        self.assertTrue(notification.is_cleared)
