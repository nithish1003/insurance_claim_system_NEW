import os
import django
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'insurance_claim_system.settings')
django.setup()

from notifications.models import Notification

def verify_notifications():
    notifs = Notification.objects.all().select_related('user')
    print(f"Total notifications: {notifs.count()}")
    for n in notifs:
        print(f"User: {n.user.username} | Title: {n.title} | Read: {n.is_read}")

if __name__ == "__main__":
    verify_notifications()
