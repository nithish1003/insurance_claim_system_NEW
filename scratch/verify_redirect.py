import os
import sys
import django
from django.test import RequestFactory
from django.contrib.auth import get_user_model
from django.contrib.messages.storage.fallback import FallbackStorage

# Setup Django settings
sys.path.append(os.getcwd())
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'insurance_claim_system.settings')
django.setup()

from claims.models import Claim
from notifications.models import Notification
from notifications.views import notification_redirect
from policy.models import Policy, UserPolicy

class DummyStorage:
    def __init__(self, request):
        self.messages = []
    def add(self, level, message, extra_tags=''):
        self.messages.append(message)

def test_redirects():
    User = get_user_model()
    admin_user = User.objects.filter(role='admin').first()
    staff_user = User.objects.filter(role='staff').first()
    normal_user = User.objects.filter(role='user').first()
    
    if not admin_user or not staff_user or not normal_user:
        print("Creating missing test users...")
        if not admin_user:
            admin_user = User.objects.create_user(username='test_admin', password='password', role='admin', is_superuser=True, is_staff=True)
        if not staff_user:
            staff_user = User.objects.create_user(username='test_staff', password='password', role='staff', is_staff=True)
        if not normal_user:
            normal_user = User.objects.create_user(username='test_user', password='password', role='user')

    policy = Policy.objects.first()
    user_policy = UserPolicy.objects.first()
    
    # 1. Create a dummy claim and notification
    claim_num = "CLM-TEST-9999"
    Claim.objects.filter(claim_number=claim_num).delete()
    claim = Claim.objects.create(
        claim_number=claim_num,
        claim_type='medical',
        final_claim_type='medical',
        description="Verification claim",
        incident_date=timezone_date(),
        claimed_amount=1000.00,
        policy=policy,
        user_policy=user_policy,
        created_by=normal_user,
        status="submitted"
    )
    
    # Create notification for admin
    notif = Notification.objects.create(
        user=admin_user,
        title="New Claim Submitted",
        message=f"Claim {claim_num} pending review.",
        type='info',
        role_target='staff',
        related_claim_id=claim.public_id
    )
    
    factory = RequestFactory()
    
    # Test Admin Redirect
    print("Testing admin user redirect...")
    req = factory.get(f'/notifications/redirect/{notif.id}/')
    req.user = admin_user
    req._messages = DummyStorage(req)
    res = notification_redirect(req, notif.id)
    print(f"Admin redirect status code: {res.status_code}, location: {res.url}")
    assert f"/claim/review/{claim.public_id}/" in res.url
    
    # Test Staff Redirect
    print("Testing staff user redirect...")
    notif.user = staff_user
    notif.is_read = False
    notif.save()
    req = factory.get(f'/notifications/redirect/{notif.id}/')
    req.user = staff_user
    req._messages = DummyStorage(req)
    res = notification_redirect(req, notif.id)
    print(f"Staff redirect status code: {res.status_code}, location: {res.url}")
    assert f"/claim/staff/claim/{claim.public_id}/review/" in res.url

    # Test Normal User Redirect
    print("Testing normal user redirect...")
    notif.user = normal_user
    notif.is_read = False
    notif.save()
    req = factory.get(f'/notifications/redirect/{notif.id}/')
    req.user = normal_user
    req._messages = DummyStorage(req)
    res = notification_redirect(req, notif.id)
    print(f"Normal user redirect status code: {res.status_code}, location: {res.url}")
    assert f"/claim/{claim.public_id}/" in res.url

    # 2. Test Fallback logic for orphaned claim notification
    print("Testing fallback/orphaned notification routing...")
    import uuid
    orphaned_uuid = uuid.uuid4()
    notif.user = admin_user
    notif.is_read = False
    notif.related_claim_id = orphaned_uuid
    notif.save()
    
    req = factory.get(f'/notifications/redirect/{notif.id}/')
    req.user = admin_user
    req._messages = DummyStorage(req)
    res = notification_redirect(req, notif.id)
    print(f"Orphaned redirect resolved location: {res.url}")
    # It should still resolve to claim.public_id because of the fallback parsing the claim number from the message!
    assert f"/claim/review/{claim.public_id}/" in res.url
    print("Orphaned notification successfully mapped back via claim number!")

    # Clean up
    Claim.objects.filter(claim_number=claim_num).delete()
    notif.delete()
    print("All verification tests passed successfully!")

def timezone_date():
    from django.utils import timezone
    return timezone.now().date()

if __name__ == '__main__':
    test_redirects()
