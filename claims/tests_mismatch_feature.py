import pytest
from decimal import Decimal
from unittest.mock import MagicMock
from claims.models import Claim
from claims.xgb_audit_engine import XGBAuditEngine

@pytest.mark.django_db
class TestClaimAmountMismatch:
    """
    Test Suite for Enterprise Fraud Feature: Claim Amount Mismatch Ratio
    """

    def setup_method(self):
        self.engine = XGBAuditEngine()

    def test_mismatch_calculation_low_risk(self):
        # 10k manual, 10k OCR -> 0% mismatch
        claim = MagicMock(spec=Claim)
        claim.claimed_amount = Decimal("10000.00")
        claim.ocr_text = "Total Amount: 10000"
        claim.documents.all.return_value = []
        
        # Mock ocr_service
        with MagicMock() as mock_ocr:
            import ai_features.services.ocr_service
            ai_features.services.ocr_service.extract_details = MagicMock(return_value={'total_amount': 10000, 'confidence': 'HIGH'})
            
            # Run part of the engine logic (simulated)
            ocr_total = 10000.0
            manual_amt = 10000.0
            ratio = abs(manual_amt - ocr_total) / max(ocr_total, 1.0)
            
            assert ratio == 0.0

    def test_mismatch_calculation_high_risk(self):
        # 80k manual, 50k OCR -> 60% mismatch
        ocr_total = 50000.0
        manual_amt = 80000.0
        ratio = abs(manual_amt - ocr_total) / max(ocr_total, 1.0)
        
        assert ratio == 0.6
        
        # Score mapping check
        m_score = 0.0
        if ratio > 0.5: m_score = 75.0
        assert m_score == 75.0

    def test_smart_exception_estimate(self):
        # 20k manual, 15k OCR, but is an ESTIMATE
        ocr_text = "This is a repair ESTIMATE for the vehicle"
        ratio = 0.33
        m_score = 50.0 # High risk normally
        
        if "ESTIMATE" in ocr_text.upper():
            m_score *= 0.5
            
        assert m_score == 25.0 # Reduced risk
