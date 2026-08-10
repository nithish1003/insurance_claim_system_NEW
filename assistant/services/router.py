import re
from .intents import Intent
from .db_service import DBService

class AssistantRouter:
    """Production-Grade Hybrid NLP System for ClaimIQ AI."""

    @staticmethod
    def route(query, user, memory=None):
        memory = memory or {}
        is_authenticated = user.is_authenticated if user else False
        role = getattr(user, 'role', 'guest') if is_authenticated else 'guest'
        
        # --- PHASE 1: PREPROCESSING & TYPO CORRECTION ---
        text = AssistantRouter.preprocess(query)
        
        # --- PHASE 2: URGENCY DETECTION (Skip Rules/ML for Emergencies) ---
        urgency_score = AssistantRouter.detect_urgency(text)
        if urgency_score > 0.8:
            return AssistantRouter.handle_emergency(), Intent.URGENCY_INTENT, 1.0, False

        # --- PHASE 3: CONTEXT & PRONOUN RESOLUTION ---
        if any(w in text.split() for w in ["it", "them", "that", "this", "still", "continue"]):
            last_topic = memory.get('last_topic')
            if last_topic: 
                intent, confidence = last_topic, 1.0
            else:
                intent, confidence = AssistantRouter.detect_intent_logic(text, role)
        else:
            intent, confidence = AssistantRouter.detect_intent_logic(text, role)
        
        # --- PHASE 4: ENTITY EXTRACTION ---
        entities = AssistantRouter.extract_entities(text)
        if entities['policy_id']: memory['last_policy_id'] = entities['policy_id']
        if entities['claim_id']: memory['last_claim_id'] = entities['claim_id']

        # 👑 ADHERENCE TO ADMIN/STAFF ROLES
        if role in ['staff', 'admin']:
            if entities['policy_id'] or entities['email'] or (confidence > 0.8 and intent == Intent.STAFF_SEARCH_CUSTOMER):
                search_term = entities['policy_id'] or entities['email']
                if not search_term:
                    # Clean out standard prefix keywords to extract name/username
                    search_term = re.sub(r'\b(?:search|find|lookup|customer|user)\b', '', text, flags=re.I).strip()
                if search_term:
                    return DBService.search_customer(search_term), Intent.STAFF_SEARCH_CUSTOMER, 1.0, False
            if entities['claim_id'] or (confidence > 0.8 and intent == Intent.STAFF_SEARCH_CLAIM):
                search_term = entities['claim_id']
                if not search_term:
                    # Clean out standard prefix keywords to extract claim number/id
                    search_term = re.sub(r'\b(?:search|find|lookup|claim)\b', '', text, flags=re.I).strip()
                if search_term:
                    return DBService.search_claim(search_term), Intent.STAFF_SEARCH_CLAIM, 1.0, False

        # --- PHASE 5: RESPONSE GENERATION ---
        memory['last_topic'] = intent
        
        if confidence >= 0.85:
            # FAQ Definition
            if intent == Intent.FAQ_POLICY:
                resp = ("An **insurance policy** is essentially a promise. It's a legal contract that defines exactly how we protect you, what's covered, and how we'll support you during a claim.")
                if is_authenticated:
                    return f"I'd love to explain that! {resp}\n\nWould you like me to **summarize your personal coverage** too?", intent, confidence, False
                return resp, intent, confidence, False

            # GREETING
            if intent == Intent.GREETING: return AssistantRouter.handle_greeting(user, role), intent, confidence, False
            
            # CORE PRODUCTS (Personalized & Human Response)
            if intent == Intent.HEALTH_INFO: return AssistantRouter.handle_health_query(text, entities), intent, confidence, False
            if intent == Intent.MOTOR_INFO: return ("Car or Bike? I can help you with comprehensive cover for both including zero-dep and road-side assistance. Which vehicle are we looking to protect?", intent, confidence, False)
            if intent == Intent.PROPERTY_INFO: return ("Protecting your 'Ghar' or shop is vital. Our Property Insurance covers fire, theft, and environmental damage. Would you like to see our Home or Commercial plans?", intent, confidence, False)
            if intent == Intent.LIFE_INFO: return ("Thinking about the future is a big step. We offer Term Plans and Savings plans to ensure your family stays financially secure. Want to dive into the details?", intent, confidence, False)

            # ACCOUNT DATA
            if intent == Intent.CLAIM_STATUS: 
                if not is_authenticated: return AssistantRouter.ask_to_login(), intent, confidence, False
                return DBService.get_user_claims(user), intent, confidence, False
            if intent == Intent.PREMIUM_DUE:
                if not is_authenticated: return AssistantRouter.ask_to_login(), intent, confidence, False
                return DBService.get_premium_status(user), intent, confidence, False
            if intent == Intent.ACTIVE_POLICY:
                if not is_authenticated: return AssistantRouter.ask_to_login(), intent, confidence, False
                return DBService.get_policy_details(user), intent, confidence, False

            # SUPPORT
            if intent == Intent.SUPPORT_TICKET: return DBService.create_support_ticket(user, query), intent, confidence, False

            # ADMIN / STAFF
            if role in ['admin', 'staff']:
                if intent == Intent.PENDING_CLAIMS:
                    return DBService.get_operational_summary() + "\n\n[Open Claims Dashboard](/claim/)", intent, confidence, False
                if intent == Intent.REVIEW_QUEUE:
                    return DBService.get_staff_backlog() + "\n\n[Access KYC Verifications](/admin/)", intent, confidence, False
                if intent == Intent.FRAUD_ALERTS:
                    return DBService.get_failed_payments() + "\n\n[Open Fraud Intelligence Center](/analytics/fraud-intelligence/)", intent, confidence, False
                if intent == Intent.ANALYTICS:
                    return DBService.get_admin_summary() + "\n\n[Open System Analytics](/analytics/dashboard/)", intent, confidence, False
                if intent == Intent.ADMIN_MANAGE_USER:
                    return "User Account Management interface ready. You can use the search command `user: email@example.com` or go directly to the **[Admin User Console](/admin/accounts/user/)**.", intent, confidence, False
                if intent == Intent.ADMIN_EXPORT_REPORT:
                    return DBService.get_revenue_metrics() + "\n\n[Open Advanced Reports Hub](/reports/)", intent, confidence, False
                if intent == Intent.DASHBOARD_STATS:
                    from django.contrib.auth import get_user_model
                    User = get_user_model()
                    total_users = User.objects.count()
                    return f"There are currently **{total_users}** registered users in the platform.", intent, confidence, False
                if intent == "list_users":
                    from django.contrib.auth import get_user_model
                    User = get_user_model()
                    users_list = list(User.objects.values_list('username', flat=True)[:10])
                    return f"Here are the names of some of the users registered in the project: **{', '.join(users_list)}**.", intent, confidence, False
                if intent == Intent.ADMIN_STAFF_PERFORMANCE:
                    return DBService.get_staff_performance(), intent, confidence, False
                if intent == Intent.STAFF_EXPIRING_POLICIES:
                    return DBService.get_expiring_policies(), intent, confidence, False

        # LLM FALLBACK
        return AssistantRouter.llm_fallback(query, user, memory), Intent.FALLBACK, confidence, False

    @staticmethod
    def preprocess(text):
        text = text.lower().strip()
        # Normalization & Typo fixes
        fixes = {
            r'\bexpalin\b|\bexplian\b': 'explain',
            r'\bpolcy\b|\bplcy\b': 'policy',
            r'\binsurence\b|\bins\b': 'insurance',
            r'\bppl\b|\bmembars\b': 'people',
            r'\bcar\b|\bgaadi\b|\bvhicle\b': 'vehicle',
            r'\bhome\b|\bghar\b': 'property',
            r'\bmoney\b|\bpaisa\b': 'premium'
        }
        for p, r in fixes.items(): text = re.sub(p, r, text)
        return text

    @staticmethod
    def detect_urgency(text):
        urgency_terms = ["emergency", "accident", "hospital", "died", "death", "serious", "stolen", "ambulance"]
        return 1.0 if any(w in text for w in urgency_terms) else 0.0

    @staticmethod
    def handle_emergency():
        return ("🚨 **URGENT ASSSISTANCE DETECTED**\n\n"
                "Please stay calm. If this is a medical emergency, call **102** or **108** immediately.\n\n"
                "For **roadside assistance** or to report a **stolen vehicle**, dial our 24/7 Priority Line: **1800-CLAIM-IQ**.\n"
                "Would you like me to notify a live emergency coordinator now?")

    @staticmethod
    def detect_intent_logic(text, role):
        # 👑 ADHERENCE TO ADMIN/STAFF ROLES FOR OTHER USER LOOKUPS
        if role in ['admin', 'staff'] and not any(w in text for w in ["my", "me", "i"]):
            # If a staff member mentions user + claim/policy in their text, treat as customer search
            # Example: "ravi claim status" or "ravi policy status"
            if any(w in text for w in ["claim", "policy"]):
                return Intent.STAFF_SEARCH_CUSTOMER, 1.0

        # 🧪 DETERMINISTIC RULES FIRST
        if "my policy number" in text or "policy number" in text or "my policy id" in text or "policy id" in text or "certificate number" in text:
            if role in ['admin', 'staff'] and not any(w in text for w in ["my", "me", "i"]):
                return Intent.STAFF_SEARCH_CUSTOMER, 1.0
            return Intent.ACTIVE_POLICY, 1.0
        if "explain my policy" in text or "my policy details" in text:
            if role in ['admin', 'staff'] and not any(w in text for w in ["my", "me", "i"]):
                return Intent.STAFF_SEARCH_CUSTOMER, 1.0
            return Intent.ACTIVE_POLICY, 1.0
        if "explain policy" in text or "what is policy" in text:
            return Intent.FAQ_POLICY, 1.0
        if "my claim" in text or "claim status" in text or "check claim" in text or "claim progress" in text:
            if role in ['admin', 'staff'] and not any(w in text for w in ["my", "me", "i"]):
                return Intent.STAFF_SEARCH_CUSTOMER, 1.0
            return Intent.CLAIM_STATUS, 1.0
        
        if role in ['admin', 'staff']:
            # Search customer or claim
            if any(w in text for w in ["search customer", "find customer", "find user", "search user", "lookup customer", "lookup user"]):
                return Intent.STAFF_SEARCH_CUSTOMER, 1.0
            if any(w in text for w in ["search claim", "find claim", "lookup claim"]):
                return Intent.STAFF_SEARCH_CLAIM, 1.0
            
            # Staff & admin metrics
            if any(w in text for w in ["name of user", "list users", "show users"]): return "list_users", 1.0
            if any(w in text for w in ["how many user", "total user", "user count", "number of users"]): return Intent.DASHBOARD_STATS, 1.0
            if any(w in text for w in ["review claims", "pending claims", "claims queue", "dossiers total", "active claims"]): return Intent.PENDING_CLAIMS, 1.0
            if any(w in text for w in ["fraud alerts", "failed payments", "fraud dashboard", "payment failures", "fraud intelligence"]): return Intent.FRAUD_ALERTS, 1.0
            if any(w in text for w in ["manage users", "user console", "user management"]): return Intent.ADMIN_MANAGE_USER, 1.0
            if any(w in text for w in ["revenue report", "financial performance", "collections", "payout volume"]): return Intent.ADMIN_EXPORT_REPORT, 1.0
            if any(w in text for w in ["system analytics", "executive summary", "business health", "health check"]): return Intent.ANALYTICS, 1.0
            if any(w in text for w in ["kyc backlog", "kyc queue", "pending approvals", "kyc approvals", "aadhaar verifications"]): return Intent.REVIEW_QUEUE, 1.0
            if any(w in text for w in ["staff performance", "staff productivity", "staff rankings", "auditor performance"]): return Intent.ADMIN_STAFF_PERFORMANCE, 1.0
            if any(w in text for w in ["expiring policies", "policies expiring", "expire this month"]): return Intent.STAFF_EXPIRING_POLICIES, 1.0
            if any(w in text for w in ["support ticket", "unresolved ticket", "tickets queue"]): return Intent.SUPPORT_TICKET, 1.0
        
        # 🧪 ML CLASSIFIER (Multilingual support)
        scores = {}
        synonyms = {
            Intent.HEALTH_INFO: ["medical", "hospital", "sick", "family", "doctor", "health", "bimari"],
            Intent.MOTOR_INFO: ["car", "bike", "vehicle", "scooter", "auto", "road", "gaadi"],
            Intent.PROPERTY_INFO: ["house", "building", "shop", "office", "fire", "property", "ghar"],
            Intent.LIFE_INFO: ["future", "savings", "pension", "death", "protection", "life"],
            Intent.CLAIM_STATUS: ["update", "check", "file", "settle", "claim", "status", "my claims", "active claims"],
            Intent.ACTIVE_POLICY: ["my policy", "policy number", "policy id", "my coverage", "active policy", "certificate number", "policy details"],
            Intent.PREMIUM_DUE: ["pay", "money", "billing", "date", "premium", "paisa", "due"],
            Intent.SUPPORT_TICKET: ["problem", "issue", "help", "agent", "support", "human", "talk"]
        }
        for intent, keywords in synonyms.items():
            m = sum(1 for k in keywords if k in text)
            if m > 0: scores[intent] = 0.6 + (0.15 * m)
        
        if not scores: return Intent.FALLBACK, 0.2
        best = max(scores, key=scores.get)
        return best, min(scores[best], 0.99)

    @staticmethod
    def extract_entities(text):
        entities = {
            'policy_id': re.search(r'cert-[a-z0-9]+', text, re.I).group(0) if re.search(r'cert-[a-z0-9]+', text, re.I) else None,
            'claim_id': re.search(r'c-[a-z0-9]+', text, re.I).group(0) if re.search(r'c-[a-z0-9]+', text, re.I) else None,
            'email': re.search(r'[\w\.-]+@[\w\.-]+', text).group(0) if re.search(r'[\w\.-]+@[\w\.-]+', text) else None,
            'family_size': None
        }
        f_match = re.search(r'(\d+)\s*(?:people|members|person)|(?:family of|total)\s*(\d+)', text)
        if f_match: entities['family_size'] = f_match.group(1) or f_match.group(2)
        return entities

    @staticmethod
    def handle_health_query(text, entities):
        size = entities.get('family_size')
        if size:
            return (f"For your **family of {size}**, Health Insurance is a smart investment to cover rising medical costs. One plan can protect everyone.\n\n"
                    f"To get precise, how many adults and children would you like to include in this cover?")
        return ("Our Health Insurance ensures your family's medical bills don't drain your savings. Would you like to explore our family-floater plans?")

    @staticmethod
    def handle_greeting(user, role):
        t_name = user.username if user.is_authenticated else "there"
        if role == 'admin': return f"Welcome back Admin. Executive Dashboard online."
        if role == 'staff': return f"Good day Staff. Operational summaries updated."
        return f"Hi {t_name}! I'm ClaimIQ AI, your personal insurance assistant. How can I help you today?"

    @staticmethod
    def ask_to_login(): return "I'd resolve that for you instantly—just sign in to your secure account to access your personal records."
    
    @staticmethod
    def llm_fallback(query, user, memory):
        try:
            import google.generativeai as genai
            from django.contrib.auth import get_user_model
            User = get_user_model()
            
            # Using the Google AI Studio key provided by the user
            genai.configure(api_key="AIzaSyCWs18kopM-JhoUgb29szg6g11Ij9au3yU")
            
            is_authenticated = user.is_authenticated if user else False
            role = getattr(user, 'role', 'guest') if is_authenticated else 'guest'
            username = getattr(user, 'username', 'Guest') if is_authenticated else 'Guest'
            
            # Injecting Live System Context
            total_users = User.objects.count()
            users_list = list(User.objects.values_list('username', flat=True)[:10])
            staff_list = list(User.objects.filter(role='staff').values_list('username', flat=True))
            admin_list = list(User.objects.filter(role='admin').values_list('username', flat=True))
            
            # Fetch User Policies and Claims for logged in user context
            user_policy_context = "No active policy found."
            user_claims_context = "No recent claims found."
            if is_authenticated:
                try:
                    from policy.models import UserPolicy
                    from claims.models import Claim
                    
                    user_policies = UserPolicy.objects.filter(user=user)
                    if user_policies.exists():
                        policy_lines = []
                        for up in user_policies:
                            plan_name = up.policy.plan.name if up.policy and up.policy.plan else "Standard Plan"
                            policy_lines.append(
                                f"- Plan: {plan_name} (Policy No: {up.policy.policy_number}, Certificate No: {up.certificate_number}) | "
                                f"Status: {up.get_status_display()}, Coverage: ₹{up.policy.sum_insured:,}, "
                                f"Remaining: ₹{up.sum_insured_remaining or 0:,}, Expiry: {up.end_date.strftime('%d %b %Y') if up.end_date else 'N/A'}"
                            )
                        user_policy_context = "\n".join(policy_lines)
                    
                    claims = Claim.objects.filter(created_by=user).order_by('-created_at')[:3]
                    if claims.exists():
                        claim_lines = []
                        for c in claims:
                            claim_lines.append(
                                f"- Claim #{c.claim_number} | Status: {c.status.upper()} | Submitted: {c.created_at.strftime('%d %b %Y')}"
                            )
                        user_claims_context = "\n".join(claim_lines)
                except Exception as ex:
                    print(f"[CONTEXT ERROR] {ex}")
            
            from assistant.services.db_service import DBService
            admin_summary = DBService.get_admin_summary()
            revenue_metrics = DBService.get_revenue_metrics()
            staff_backlog = DBService.get_staff_backlog()
            staff_performance = DBService.get_staff_performance()
            
            # Dynamically fetch other user details if referenced in query
            searched_user_context = ""
            if role in ['staff', 'admin']:
                mentioned_user = None
                for uname in users_list:
                    if uname.lower() in query.lower():
                        mentioned_user = uname
                        break
                
                if mentioned_user:
                    try:
                        from accounts.models import User as UserModel
                        from policy.models import UserPolicy
                        from claims.models import Claim
                        
                        m_user = UserModel.objects.filter(username__iexact=mentioned_user).first()
                        if m_user:
                            m_policies = UserPolicy.objects.filter(user=m_user)
                            m_claims = Claim.objects.filter(created_by=m_user)
                            
                            p_lines = []
                            for up in m_policies:
                                plan_name = up.policy.plan.name if up.policy and up.policy.plan else "Standard Plan"
                                p_lines.append(
                                    f"- Certificate: {up.certificate_number} | Plan: {plan_name} | Status: {up.get_status_display()} | Coverage: ₹{up.policy.sum_insured:,}"
                                )
                            c_lines = []
                            for c in m_claims:
                                c_lines.append(
                                    f"- Claim #{c.claim_number} | Status: {c.status.upper()} | Claimed: ₹{c.claimed_amount or 0:,} | Settled: ₹{c.settled_amount or 0:,} | "
                                    f"AI Recommendation: ₹{c.authoritative_payout or 0:,} | Fraud Risk: {c.fraud_risk_score * 100:.1f}% | "
                                    f"Leakage Risk: {c.leakage_risk_score * 100:.1f}% | Integrity Status: {c.get_integrity_status_display()} | "
                                    f"SHAP Narrative: {c.shap_narrative or 'None'}"
                                )
                            
                            searched_user_context = (
                                f"\n--- DATABASE RECORDS FOR SEARCHED USER '{mentioned_user.upper()}' ---\n"
                                f"Policies:\n" + ("\n".join(p_lines) if p_lines else "None found.") + "\n"
                                f"Claims:\n" + ("\n".join(c_lines) if c_lines else "None found.") + "\n"
                                f"----------------------------------------------------\n"
                            )
                    except Exception as e_search:
                        print(f"[SEARCHED CONTEXT ERROR] {e_search}")

            # Fetch Chat History for Memory
            from assistant.models import AssistantMessage
            session_id = memory.get('session_id')
            chat_history_str = "No previous history."
            if session_id:
                past_msgs = AssistantMessage.objects.filter(session_id=session_id).order_by('-timestamp')[:7]
                history_lines = []
                for msg in reversed(past_msgs):
                    role_str = "User" if msg.sender == "user" else "ClaimIQ"
                    history_lines.append(f"{role_str}: {msg.content}")
                if history_lines:
                    chat_history_str = "\n".join(history_lines)
            
            system_prompt = f"""You are ClaimIQ, the advanced AI Assistant for an Insurance Claim System.
Your job is to be extremely helpful, professional, and explain things clearly.
Do not output raw code; use bolding, bullet points, and clean conversational text.
Current User Context: Name={username}, Role={role}.
System Context: Total Users in system: {total_users}. Sample user names: {', '.join(users_list)}.
Registered Staff Members: {', '.join(staff_list) if staff_list else 'None'}
Registered Admins: {', '.join(admin_list) if admin_list else 'None'}

{searched_user_context}
--- ACTIVE USER POLICIES ---
{user_policy_context}
---------------------------

--- ACTIVE USER CLAIMS ---
{user_claims_context}
--------------------------

--- LIVE DATABASE METRICS ---
{admin_summary}
{revenue_metrics}
{staff_backlog}
{staff_performance}
-----------------------------

--- RECENT CONVERSATION HISTORY ---
{chat_history_str}
-----------------------------------

If the user asks about the names of users, financial metrics, pending claims, backlogs, or general queries, answer them accurately and conversationally using ONLY the numbers and data provided in the System Context above.
If the user asks about their own policies (such as their Policy Number, Certificate Number, status, or sum insured) or claim statuses, retrieve the information directly from the ACTIVE USER POLICIES and ACTIVE USER CLAIMS contexts above.
If the user asks why the policy number is different from the certificate number, explain that the Policy Number (e.g., POL-XXXX) is the blueprint catalog code, while the Certificate Number (e.g., CERT-XXXX) is their personal active policy subscription certificate.
If the user asks something completely outside of insurance or your context, politely redirect them.
Respond to the final message in the Recent Conversation History.
"""
            
            model = genai.GenerativeModel(
                model_name="gemini-flash-latest",
                system_instruction=system_prompt
            )
            response = model.generate_content(query)
            return response.text
            
        except Exception as e:
            print(f"[LLM ERROR] {e}")
            return "I'm genuinely here to help, but that specific request is a bit tricky for me right now. Could you share a few more details so I can guide you correctly?"
