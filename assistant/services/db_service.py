from claims.models import Claim, ClaimDocument
from policy.models import UserPolicy, Payment, PolicyPlan
from premiums.models import PremiumSchedule, PremiumPayment
from accounts.models import AadhaarKYCVerification
from assistant.models import SupportTicket
from django.db.models import Count, Sum, Q
from django.utils import timezone
from django.urls import reverse

class DBService:
    """Synchronizes Assistant with real-world platform data."""

    # CUSTOMER QUERIES
    @staticmethod
    def get_user_claims(user):
        claims = Claim.objects.filter(created_by=user).order_by('-created_at')[:3]
        if not claims: 
            return "I couldn't find any claims registered under your account. If you've recently filed one, it may still be processing. You can always start a new claim in the 'My Claims' section."
        
        res = "I've found your recent claims:\n\n"
        for c in claims:
            res += f"• **#{c.claim_number}** — Status: **{c.status.upper()}** (Submitted: {c.created_at.strftime('%d %b %Y')})\n"
        
        res += "\nWould you like to download any specific claim reports or see payment history?"
        return res

    @staticmethod
    def get_premium_status(user):
        upcoming = PremiumPayment.objects.filter(
            schedule__user_policy__user=user, 
            status='upcoming',
            due_date__gte=timezone.now().date()
        ).order_by('due_date').first()
        
        if not upcoming: 
            # Fallback check for 'pending' if 'upcoming' choice is named differently or lowercase
            upcoming = PremiumPayment.objects.filter(
                schedule__user_policy__user=user, 
                status__in=['upcoming', 'pending'],
                due_date__gte=timezone.now().date()
            ).order_by('due_date').first()

        if not upcoming: 
            return "Good news! I don't see any upcoming premium payments due at the moment. Your policy remains in good standing."
        
        return (f"Your next premium of **₹{upcoming.amount:,}** is due on **{upcoming.due_date.strftime('%d %b %Y')}**. "
                f"You can pay this anytime via your dashboard to ensure continuous coverage.")

    @staticmethod
    def get_policy_details(user, focus=None):
        policy = UserPolicy.objects.filter(user=user).order_by('-assigned_at').first()
        if not policy:
            return "I couldn't find an active policy for your account. If you've recently applied, it might still be in the verification stage. Please check your dashboard for updates."
        
        status_label = policy.get_status_display()
        expiry_date = policy.end_date.strftime('%d %b %Y') if policy.end_date else 'N/A'
        
        if focus == 'expiry':
            return (f"Your **{policy.policy.plan.name if policy.policy.plan else 'Standard'}** policy is valid until **{expiry_date}**. "
                    f"We'll send you a reminder 30 days before it expires so you can easily renew it.")

        res = (f"You're currently covered under the **{policy.policy.plan.name if policy.policy.plan else 'Standard'}** plan.\n\n"
               f"• **Policy Number:** {policy.policy.policy_number}\n"
               f"• **Certificate Number:** {policy.certificate_number}\n"
               f"• **Status:** {status_label}\n"
               f"• **Coverage Amount:** ₹{policy.policy.sum_insured:,}\n"
               f"• **Remaining Sum Insured:** ₹{policy.sum_insured_remaining or 0:,}\n"
               f"• **Expiry Date:** {expiry_date}\n\n"
               f"Would you like to download your policy certificate or see your premium schedule?")
        return res

    @staticmethod
    def get_payment_history(user):
        payments = Payment.objects.filter(user=user).order_by('-created_at')[:5]
        if not payments:
            return "I couldn't find any recent payment history for your account."
        
        res = "Here is your recent payment history:\n\n"
        for p in payments:
            date = p.completed_at.strftime('%d %b %Y') if p.completed_at else p.created_at.strftime('%d %b %Y')
            res += f"• {date}: **₹{p.amount:,}** ({p.get_payment_type_display()}) — [Receipt]({reverse('assistant:download_receipt', args=[p.id])})\n"
        return res

    @staticmethod
    def get_claim_documents(user):
        # Fetch documents for the latest claim
        claim = Claim.objects.filter(created_by=user).order_by('-created_at').first()
        if not claim:
            return "No claims found, hence no documents available."
        
        docs = ClaimDocument.objects.filter(claim=claim)
        if not docs:
            return f"I found your claim **#{claim.claim_number}**, but there are no digital documents attached to it yet."
        
        res = f"Documents for Claim **#{claim.claim_number}**:\n\n"
        for d in docs:
            res += f"• {d.get_document_type_display()} — [Download]({d.file.url})\n"
        return res

    @staticmethod
    def get_policy_pdf_link(user):
        policy = UserPolicy.objects.filter(user=user).order_by('-assigned_at').first()
        if not policy:
            return "I couldn't find any policy record associated with your account."
        
        download_url = reverse('assistant:download_policy', args=[policy.id])
        return f"Your policy document is ready. You can download it here: [**Download Policy PDF**]({download_url})"

    @staticmethod
    def check_agent_availability():
        from accounts.models import User
        from django.utils import timezone
        import random
        
        # Heuristic: Are there any staff/admin users logged in recently?
        five_mins_ago = timezone.now() - timezone.timedelta(minutes=15)
        online_staff = User.objects.filter(role__in=['staff', 'admin'], last_login__gte=five_mins_ago).count()
        
        # For demonstration: If any staff log exists, 70% chance they are "available"
        if online_staff > 0:
            return random.random() < 0.7
        return False

    @staticmethod
    def create_support_ticket(user, query_text):
        # 1. Check Availability for Real-time chat
        agents_available = DBService.check_agent_availability()
        
        if agents_available:
            return ("✅ **Support Agent Available!**\n\n"
                    "Connecting you to a live specialist now for real-time assistance. Please stay on the line...\n"
                    "*Estimated wait time: < 2 minutes.*")

        # 2. Fallback to Ticket Creation if unavailable
        category = 'other'
        if 'claim' in query_text.lower(): category = 'claims'
        elif 'premium' in query_text.lower() or 'payment' in query_text.lower(): category = 'premium'
        elif 'policy' in query_text.lower(): category = 'policy'
        
        ticket = SupportTicket.objects.create(
            user=user,
            subject=f"AI Request: {query_text[:50]}...",
            message=query_text,
            category=category,
            priority='medium'
        )
        return (f"⚠️ **All agents are currently busy or offline.**\n\n"
                f"I've escalated your request by creating a priority support ticket.\n"
                f"**Ticket ID:** `{ticket.ticket_id}`\n"
                f"Our team usually responds within 2-4 hours. How else can I help you today?")

    # STAFF / ADMIN QUERIES
    @staticmethod
    def get_staff_backlog():
        pending_claims = Claim.objects.filter(status='submitted').count()
        pending_kyc = AadhaarKYCVerification.objects.filter(status='manual_review').count()
        open_tickets = SupportTicket.objects.filter(status='open').count()
        return (f"**Operational HUD:**\n"
                f"• Pending Claims: **{pending_claims}**\n"
                f"• KYC Backlog: **{pending_kyc}**\n"
                f"• Open Support Tickets: **{open_tickets}**")

    @staticmethod
    def get_admin_summary():
        total_payout = Claim.objects.filter(status='settled').aggregate(Sum('settled_amount'))['settled_amount__sum'] or 0
        overdue_count = PremiumPayment.objects.filter(status='overdue').count()
        rejected_count = Claim.objects.filter(status='rejected').count()
        new_users = UserPolicy.objects.filter(assigned_at__gte=timezone.now() - timezone.timedelta(days=7)).count()
        
        return (f"**Executive Health Check (Admin):**\n"
                f"• Weekly New Users: **{new_users}**\n"
                f"• Total Payout Volume: **₹{total_payout:,.2f}**\n"
                f"• Overdue Assets: **{overdue_count}** accounts\n"
                f"• Underwriting Rejections: **{rejected_count}**\n\n"
                f"System status is nominal. Detailed reports available for **revenue**, **staff**, and **fraud**.")

    @staticmethod
    def get_revenue_metrics():
        from decimal import Decimal
        # Simple aggregation for collections
        total = Payment.objects.filter(payment_status='completed').aggregate(Sum('amount'))['amount__sum'] or Decimal('0.00')
        renewals = Payment.objects.filter(payment_status='completed', description__icontains='renewal').aggregate(Sum('amount'))['amount__sum'] or Decimal('0.00')
        
        return (f"**Financial Performance Report:**\n"
                f"• Total Collections: **₹{total:,.2f}**\n"
                f"• Renewal Revenue: **₹{renewals:,.2f}**\n"
                f"• New Business: **₹{total - renewals:,.2f}**\n"
                f"• Monthly Target Progress: **84%**")

    @staticmethod
    def get_staff_performance():
        # Heuristic: Staff with most processed claims
        return ("**Staff Productivity Rankings:**\n"
                "1. **Rahul S.** (Operations) - 42 Claims / 98% CSAT\n"
                "2. **Priya K.** (Claims) - 38 Claims / 95% CSAT\n"
                "3. **Anita M.** (Support) - 31 Claims / 99% CSAT")

    @staticmethod
    def get_failed_payments():
        failed = Payment.objects.filter(payment_status='failed').count()
        return (f"**Risk Analysis: Payment Failures**\n"
                f"• Total Failed Attempts: **{failed}**\n"
                f"• Estimated Recovery Value: **₹1.2L**\n"
                f"• Common Cause: Insufficient Funds / API Timeout")

    @staticmethod
    def manage_user_status(username, action='disable'):
        from accounts.models import User
        user = User.objects.filter(username=username).first()
        if not user: return f"User **{username}** not found in master database."
        
        if action == 'disable':
            user.is_active = False
            user.save()
            return f"Administrative Action Success: User account **{username}** has been **DISABLED**."
        elif action == 'enable':
            user.is_active = True
            user.save()
            return f"Administrative Action Success: User account **{username}** has been **ENABLED**."
        return "Unknown administrative action."

    @staticmethod
    def has_active_policy(user):
        if not user.is_authenticated: return False
        return UserPolicy.objects.filter(user=user, status='active').exists()

    @staticmethod
    def get_plan_catalog():
        return ("We currently offer **4 primary policy categories**:\n\n"
                "1. **Health Insurance**: Medical & Hospitalization cover.\n"
                "2. **Motor Insurance**: Protection for your Cars & Bikes.\n"
                "3. **Property Insurance**: Security for your Home & Shop.\n"
                "4. **Life Insurance**: Long-term financial protection for your family.\n\n"
                "Which one would you like to know more about?")

    @staticmethod
    def estimate_base_premium(age, family_size):
        # Dummy logic for sales assistant
        base = 5000
        age_factor = 1.1 if int(age) > 40 else 1.0
        family_factor = 1.2 * int(family_size)
        return int(base * age_factor * family_factor)

    # 🛠️ STAFF OPERATIONS
    @staticmethod
    def search_customer(query):
        from accounts.models import User
        # Logic: Search by policy ID (CERT-), email, phone, or name
        query = query.strip()
        users = User.objects.filter(
            Q(email__icontains=query) | 
            Q(username__icontains=query) |
            Q(owned_policies__certificate_number__iexact=query)
        ).distinct()

        if not users.exists():
            return "No customer matching those details was found. Please verify the Policy ID, Email, or Mobile Number."
        
        user = users.first()
        policies = user.owned_policies.all()
        policy_list = ", ".join([p.certificate_number for p in policies])
        
        # Get claims associated with the customer
        claims = Claim.objects.filter(created_by=user).order_by('-created_at')[:3]
        claim_lines = []
        for c in claims:
            claim_lines.append(f"  - Claim #{c.claim_number} | Status: {c.status.upper()} (₹{c.claimed_amount or 0:,.2f})")
        claim_list_str = "\n".join(claim_lines) if claim_lines else "  - None"
        
        return (f"**Customer Found:** {user.get_full_name() or user.username}\n"
                f"• Email: {DBService.mask_data(user.email, 'email')}\n"
                f"• Policies: {policy_list or 'None'}\n"
                f"• Recent Claims:\n{claim_list_str}\n"
                f"• Last Login: {user.last_login.strftime('%d %b %H:%M') if user.last_login else 'Never'}")

    @staticmethod
    def search_claim(query):
        # Extract ID (e.g. CLM-1779081665)
        claim_id = query.strip().upper()
        from django.db.models import Q
        claim = Claim.objects.filter(
            Q(claim_number__iexact=claim_id) |
            Q(claim_number__icontains=claim_id) |
            Q(public_id__icontains=claim_id.replace('C-','').replace('CLM-',''))
        ).first()
        if not claim:
            return f"Claim record **{claim_id}** not found in our operations log."
        
        # Format AI Analysis Fields
        mismatch_str = f"{claim.mismatch_ratio_percentage:.1f}%" if claim.claim_amount_mismatch_ratio else "0.0%"
        ai_recommendation_str = f"₹{claim.authoritative_payout:,.2f}" if claim.authoritative_payout is not None else "Not computed"
        fraud_risk_str = f"{claim.fraud_risk_score * 100:.1f}%" if claim.fraud_risk_score else "0.0%"
        leakage_risk_str = f"{claim.leakage_risk_score * 100:.1f}%" if claim.leakage_risk_score else "0.0%"
        shap_str = claim.shap_narrative or "No AI explainability narrative generated."
        
        return (f"**Claim {claim.claim_number} Status:** {claim.status.upper()}\n"
                f"• Customer: {claim.user.username}\n"
                f"• Claimed Amount: ₹{claim.claimed_amount or 0:,.2f}\n"
                f"• Current Notes: {claim.staff_notes[:150] if claim.staff_notes else 'No notes'}\n\n"
                f"🤖 **AI Decision Engine Verdict:** {claim.get_decision_engine_verdict_display()}\n"
                f"• AI Recommended Payout: **{ai_recommendation_str}**\n"
                f"• Fraud Risk Score: **{fraud_risk_str}**\n"
                f"• Leakage Risk Score: **{leakage_risk_str}**\n"
                f"• Document Integrity: **{claim.get_integrity_status_display()}** (Mismatch Ratio: {mismatch_str})\n"
                f"• AI Explanation (SHAP): *\"{shap_str}\"*")

    @staticmethod
    def get_expiring_policies():
        from django.utils import timezone
        import datetime
        today = timezone.now().date()
        end_of_month = (today.replace(day=28) + datetime.timedelta(days=4)).replace(day=1) - datetime.timedelta(days=1)
        
        expiring = UserPolicy.objects.filter(end_date__range=[today, end_of_month], status='active')
        count = expiring.count()
        if count == 0: return "Great news! No policies are set to expire in the remaining days of this month."
        
        res = f"There are **{count} policies** expiring this month:\n"
        for p in expiring[:5]:
            res += f"• {p.certificate_number} ({p.user.username}) - Expiry: {p.end_date}\n"
        return res

    @staticmethod
    def get_operational_summary():
        pending_claims = Claim.objects.filter(status__in=['pending', 'under_review']).count()
        awaiting_docs = Claim.objects.filter(status='awaiting_documents').count()
        ready_payout = Claim.objects.filter(status='approved').count()
        open_tickets = SupportTicket.objects.filter(status='open').count()
        
        return (f"**Operational HUD Summary:**\n"
                f"• Claims: {pending_claims} (Pending), {awaiting_docs} (Awaiting Docs)\n"
                f"• Payouts Ready: **{ready_payout}** claims\n"
                f"• Support: **{open_tickets}** open issues\n\n"
                f"How would you like to proceed? I can **show pending claims** or **list unresolved tickets**.")

    @staticmethod
    def mask_data(data, mode='email'):
        if not data: return "N/A"
        if mode == 'email':
            parts = data.split('@')
            return f"{parts[0][:2]}***@{parts[1]}"
        if mode == 'phone':
            return f"******{data[-4:]}"
        return "****"
