from claims.models import Claim, ClaimSettlement
from policy.models import Payment

output = []
output.append("--- FINANCIAL AUDIT ---")

output.append("\n[CLAIMS]")
for c in Claim.objects.all().order_by('-created_at'):
    status = c.status
    output.append(f"ID: {c.id} | CLAIM: {c.claim_number} | DESC: {c.description[:20]} | STATUS: {status} | CLAIMED: {c.claimed_amount} | APPROVED: {c.approved_amount} | SETTLED_FIELD: {c.settled_amount}")

output.append("\n[SETTLEMENTS]")
for s in ClaimSettlement.objects.all().order_by('-created_at'):
    claim_num = s.claim.claim_number if s.claim else "N/A"
    claim_id = s.claim.id if s.claim else "N/A"
    output.append(f"ID: {s.id} | CLAIM_ID: {claim_id} | CLAIM_NUM: {claim_num} | AMOUNT: {s.settled_amount} | DATE: {s.settlement_date}")

output.append("\n[PAYMENTS]")
for p in Payment.objects.all().order_by('-created_at'):
    user = p.user_policy.user.username if p.user_policy and p.user_policy.user else "Anon"
    output.append(f"ID: {p.id} | USER: {user} | AMOUNT: {p.amount} | STATUS: {p.payment_status} | REF: {p.transaction_id}")

try:
    with open(r'd:\insurance_claim_system_NEW\tmp\audit_results.txt', 'w', encoding='utf-8') as f:
        f.write('\n'.join(output))
    print("Audit report written to d:\\insurance_claim_system_NEW\\tmp\\audit_results.txt")
except Exception as e:
    print(f"Error writing audit report: {e}")
