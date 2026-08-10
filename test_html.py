from django.test import Client
from django.contrib.auth import get_user_model
import re

User = get_user_model()
admin = User.objects.filter(is_superuser=True).first()
client = Client()
client.force_login(admin)

response = client.get('/claim/9044c659-4bbd-40ad-8241-eb9b33569a83/')
html = response.content.decode('utf-8')

# Try to find common HTML issues
div_open = len(re.findall(r'<div\b', html))
div_close = len(re.findall(r'</div\b', html))
print(f"<div> opened: {div_open}, </div> closed: {div_close}")

if div_open != div_close:
    print("MISMATCH IN DIV TAGS!")

# Find any unclosed tags or something obvious
