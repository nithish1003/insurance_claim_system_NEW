from django.test import RequestFactory
from django.contrib.auth import get_user_model
from django.template.loader import render_to_string
from claims.views import claim_review
import traceback

try:
    User = get_user_model()
    admin = User.objects.filter(is_superuser=True).first()
    from claims.models import Claim
    claim = Claim.objects.first()
    factory = RequestFactory()
    request = factory.get(f'/claims/review/{claim.public_id}/')
    request.user = admin
    
    response = claim_review(request, str(claim.public_id))
    print("STATUS:", response.status_code)
    
    # Render the content to catch template errors!
    if hasattr(response, 'render'):
        response.render()
    print("RENDER SUCCESSFUL")
    
except Exception as e:
    print("CAUGHT EXCEPTION:")
    traceback.print_exc()
