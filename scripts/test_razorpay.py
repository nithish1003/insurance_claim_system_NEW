import os
import django
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'insurance_claim_system.settings')
django.setup()

import razorpay
from django.conf import settings

def test_razorpay_creds():
    print(f"Testing with KEY_ID: {settings.RAZORPAY_KEY_ID}")
    # Masking secret for logs, but checking length
    secret = settings.RAZORPAY_KEY_SECRET
    print(f"Secret Length: {len(secret)}")
    print(f"Secret starts with: {secret[:5]}... and ends with: ...{secret[-1]}")
    
    client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))
    try:
        # fetch_all is the correct method for recent versions
        orders = client.order.fetch_all()
        print("✅ Authentication Successful!")
        print(f"Found {len(orders['items'])} recent orders.")
    except Exception as e:
        print(f"❌ Authentication Failed: {str(e)}")

if __name__ == "__main__":
    test_razorpay_creds()
