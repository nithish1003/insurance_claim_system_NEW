from django.test import RequestFactory
from django.contrib.auth import get_user_model
from claims.views import claim_detail
import re

User = get_user_model()
admin = User.objects.filter(is_superuser=True).first()
factory = RequestFactory()
request = factory.get('/claim/9044c659-4bbd-40ad-8241-eb9b33569a83/')
request.user = admin

response = claim_detail(request, '9044c659-4bbd-40ad-8241-eb9b33569a83')
if hasattr(response, 'render'):
    response.render()

html = response.content.decode('utf-8')

div_open = len(re.findall(r'<div\b', html))
div_close = len(re.findall(r'</div\b', html))
print(f"<div> opened: {div_open}, </div> closed: {div_close}")

if div_open != div_close:
    print("MISMATCH IN DIV TAGS! Difference:", div_open - div_close)

# Count other structural tags
row_open = len(re.findall(r'<div[^>]*class="[^"]*\brow\b[^"]*"', html))
print(f"row opened: {row_open}")

