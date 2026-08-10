import re

class RuleEngine:
    """Handles high-speed keyword-based FAQ responses."""
    
    FAQ_DATA = {
        r"file|filing|submit|claim process": (
            "To file a claim: 1. Log in to your account. 2. Navigate to 'My Claims'. "
            "3. Click 'Submit New' and upload your documentation. Our team reviews all submissions within 24-48 business hours."
        ),
        r"rene?wal|expire|renew": (
            "You can renew your policy directly from your Dashboard. We'll send you a reminder "
            "30 days before your policy expires with a quick renewal link."
        ),
        r"kyc|verify|aadhaar|document": (
            "KYC verification requires a valid government ID (like Aadhaar). Please ensure the name "
            "on your account matches your ID exactly to avoid delays in processing."
        ),
        r"premium meaning|what is premium|cost|installment": (
            "A premium is the amount you pay (monthly or annually) to keep your insurance policy active. "
            "This payment ensures you are covered in the event of a claim."
        ),
        r"pay|payment|premium": (
            "You can pay your premiums via NetBanking, UPI, or Credit Card. Simply go to the 'Premiums' "
            "section in your dashboard to view your schedule and make a payment."
        ),
        r"explain policy|what is policy|coverage": (
            "An insurance policy is a legal contract between you and ClaimIQ. It outlines the specific "
            "protections, benefits, and coverage limits provided in exchange for your premium payments."
        ),
        r"contact|support|speak|talk|agent|representative|ticket": (
            "We're here to help! You can reach our support team by:\n"
            "1. Visiting our **[Support Center](/support/)**\n"
            "2. Emailing us at **support@claimiq.ai**\n"
            "3. Submitting a help ticket through your dashboard for a priority response."
        ),
        r"policy benefits|what benefits": (
            "ClaimIQ policies typically cover medical expenses, accidental damage, and third-party liabilities. "
            "Specific benefits vary by plan—you can view your full 'Benefits Schedule' in your dashboard."
        ),
        r"policy types|which plans": (
            "We offer three main tiers: **Basic** (Essential coverage), **Premium** (Standard protection), "
            "and **Elite** (Full comprehensive insurance). Contact support for a customized quote."
        ),
        r"deductible": (
            "A **deductible** is the amount you pay out-of-pocket before ClaimIQ starts covering costs. "
            "Choosing a higher deductible usually lowers your premium."
        ),
        r"waiting period": (
            "The **waiting period** is the time you must wait before certain coverages (like pre-existing conditions) "
            "become active. This is standard in most policies to ensure long-term sustainability."
        ),
        r"cashless hospital": (
            "We have a network of over **5,000+ cashless hospitals**. If you use one, ClaimIQ settles the bill "
            "directly with the hospital, so you don't have to pay anything upfront (minus your deductible)."
        ),
        r"onboarding|get started|how to buy": (
            "Getting started is easy! I can help you **explore plans**, **estimate your premium**, or "
            "**find the right coverage** based on your needs. Which would you like to do first?"
        )
    }

    @staticmethod
    def query(text):
        text = text.lower()
        for pattern, response in RuleEngine.FAQ_DATA.items():
            if re.search(pattern, text):
                return response
        return None
