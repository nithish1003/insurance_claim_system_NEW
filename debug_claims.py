from claims.models import Claim
print(f'SETTLED: {Claim.objects.filter(status="settled").count()}')
print(f'APPROVED: {Claim.objects.filter(status="approved").count()}')
print(f'SUM SETTLED: {Claim.objects.filter(status="settled").values("settled_amount", "approved_amount")}')
print(f'SUM ENTIRE: {Claim.objects.all().values("status", "approved_amount")}')
