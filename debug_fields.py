from claims.models import Claim
print([f.name for f in Claim._meta.fields])
