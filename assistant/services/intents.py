class Intent:
    # CUSTOMER INTENTS
    CLAIM_STATUS = "claim_status"
    PREMIUM_DUE = "premium_due"
    ACTIVE_POLICY = "active_policy"
    RENEWAL_DATE = "renewal_date"
    FILING_GUIDANCE = "filing_guidance"
    
    # STAFF INTENTS
    PENDING_CLAIMS = "pending_claims"
    KYC_BACKLOG = "kyc_backlog"
    SUMMARIZE_CLAIM = "summarize_claim"
    REVIEW_QUEUE = "review_queue"
    STAFF_SEARCH_CUSTOMER = "staff_search_customer"
    STAFF_SEARCH_CLAIM = "staff_search_claim"
    STAFF_EXPIRING_POLICIES = "staff_expiring_policies"
    STAFF_PREMIUM_DUES = "staff_premium_dues"
    STAFF_CLAIM_NOTES = "staff_claim_notes"
    STAFF_OPERATIONAL_SUMMARY = "staff_operational_summary"
    
    # PRODUCT INFO
    HEALTH_INFO = "health_info"
    MOTOR_INFO = "motor_info"
    PROPERTY_INFO = "property_info"
    LIFE_INFO = "life_info"
    
    # ADMIN INTENTS
    FRAUD_ALERTS = "fraud_alerts"
    ANALYTICS = "system_analytics"
    OVERDUE_PREMIUMS = "admin_overdue_list"
    ADMIN_MANAGE_USER = "admin_manage_user"
    ADMIN_REVENUE_REPORT = "admin_revenue_report"
    ADMIN_STAFF_PERFORMANCE = "admin_staff_performance"
    ADMIN_EXPORT_REPORT = "admin_export_report"
    ADMIN_SYSTEM_SETTINGS = "admin_system_settings"

    # ONBOARDING
    EXPLORE_PLANS = "explore_plans"
    COMPARE_PLANS = "compare_plans"
    ESTIMATE_PREMIUM = "estimate_premium"
    BUY_POLICY = "buy_policy"
    INSURANCE_NEEDS = "insurance_needs"

    # GENERAL
    GREETING = "greeting"
    FAQ = "faq"
    DOWNLOAD_PDF = "download_pdf"
    DOWNLOAD_RECEIPT = "download_receipt"
    SUPPORT_TICKET = "support_ticket"
    PAYMENT_HISTORY = "payment_history"
    CLAIM_DOCUMENTS = "claim_documents"
    FAQ_POLICY = "faq_policy"
    URGENCY_INTENT = "urgency_intent"
    DASHBOARD_STATS = "dashboard_stats"
    FALLBACK = "fallback"

INTENT_ROLES = {
    Intent.GREETING: ['guest', 'customer', 'staff', 'admin'],
    Intent.FAQ: ['guest', 'customer', 'staff', 'admin'],
    Intent.EXPLORE_PLANS: ['guest', 'customer', 'staff', 'admin'],
    Intent.COMPARE_PLANS: ['guest', 'customer', 'staff', 'admin'],
    Intent.ESTIMATE_PREMIUM: ['guest', 'customer', 'staff', 'admin'],
    Intent.BUY_POLICY: ['guest', 'customer', 'staff', 'admin'],
    Intent.INSURANCE_NEEDS: ['guest', 'customer', 'staff', 'admin'],
    
    Intent.CLAIM_STATUS: ['customer', 'staff', 'admin'],
    Intent.PREMIUM_DUE: ['customer', 'staff', 'admin'],
    Intent.ACTIVE_POLICY: ['customer', 'staff', 'admin'],
    Intent.RENEWAL_DATE: ['customer', 'staff', 'admin'],
    Intent.FILING_GUIDANCE: ['customer', 'staff', 'admin'],
    Intent.PAYMENT_HISTORY: ['customer', 'staff', 'admin'],
    Intent.CLAIM_DOCUMENTS: ['customer', 'staff', 'admin'],
    Intent.FAQ_POLICY: ['guest', 'customer', 'staff', 'admin'],
    Intent.URGENCY_INTENT: ['guest', 'customer', 'staff', 'admin'],
    
    Intent.HEALTH_INFO: ['guest', 'customer', 'staff', 'admin'],
    Intent.MOTOR_INFO: ['guest', 'customer', 'staff', 'admin'],
    Intent.PROPERTY_INFO: ['guest', 'customer', 'staff', 'admin'],
    Intent.LIFE_INFO: ['guest', 'customer', 'staff', 'admin'],
    
    Intent.PENDING_CLAIMS: ['staff', 'admin'],
    Intent.KYC_BACKLOG: ['staff', 'admin'],
    Intent.SUMMARIZE_CLAIM: ['staff', 'admin'],
    Intent.REVIEW_QUEUE: ['staff', 'admin'],
    Intent.STAFF_SEARCH_CUSTOMER: ['staff', 'admin'],
    Intent.STAFF_SEARCH_CLAIM: ['staff', 'admin'],
    Intent.STAFF_EXPIRING_POLICIES: ['staff', 'admin'],
    Intent.STAFF_PREMIUM_DUES: ['staff', 'admin'],
    Intent.STAFF_CLAIM_NOTES: ['staff', 'admin'],
    Intent.STAFF_OPERATIONAL_SUMMARY: ['staff', 'admin'],
    Intent.DASHBOARD_STATS: ['staff', 'admin'],
    
    Intent.FRAUD_ALERTS: ['admin'],
    Intent.ANALYTICS: ['admin'],
    Intent.OVERDUE_PREMIUMS: ['admin'],
    Intent.ADMIN_MANAGE_USER: ['admin'],
    Intent.ADMIN_REVENUE_REPORT: ['admin'],
    Intent.ADMIN_STAFF_PERFORMANCE: ['admin'],
    Intent.ADMIN_EXPORT_REPORT: ['admin'],
    Intent.ADMIN_SYSTEM_SETTINGS: ['admin'],
    
    Intent.DOWNLOAD_PDF: ['customer', 'staff', 'admin'],
    Intent.DOWNLOAD_RECEIPT: ['customer', 'staff', 'admin'],
    Intent.SUPPORT_TICKET: ['customer', 'staff', 'admin'],
}
