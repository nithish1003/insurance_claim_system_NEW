from django.test import RequestFactory
from django.contrib.auth import get_user_model
from claims.views import claim_review
User = get_user_model()
admin = User.objects.filter(is_superuser=True).first()
from claims.models import Claim
claim = Claim.objects.first()
factory = RequestFactory()
request = factory.get(f'/claims/review/{claim.public_id}/')
request.user = admin
try:
    response = claim_review(request, str(claim.public_id))
    print("STATUS:", response.status_code)
    print("TEMPLATE RENDERING SUCCESSFUL")
except Exception as e:
    import traceback
    traceback.print_exc()
