from django.test import Client
from django.contrib.auth import get_user_model
User = get_user_model()
admin = User.objects.filter(is_superuser=True).first()
client = Client()
client.force_login(admin)
from claims.models import Claim
claim = Claim.objects.first()
response = client.get(f'/claims/review/{claim.public_id}/')
print("STATUS:", response.status_code)
if response.status_code == 500:
    import re
    match = re.search(r'<div class="exception_value">(.*?)</div>', response.content.decode('utf-8'))
    print("ERROR:", match.group(1) if match else "No error found")
    match_trace = re.search(r'<pre class="exception_value">(.*?)</pre>', response.content.decode('utf-8'), re.DOTALL)
    if match_trace:
        print("TRACE:", match_trace.group(1))
    
    # Also grab the traceback frames
    match_tb = re.search(r'<table class="meta">(.*?)</table>', response.content.decode('utf-8'), re.DOTALL)
    if match_tb:
        print("META:", match_tb.group(1)[:500])
