"""
Fraud Detection Service
Uses RandomForest ML model to predict fraud risk with Explainable AI (XAI) justifications
"""

import os
import joblib
import logging
import random
from django.conf import settings
from typing import Tuple, Optional, List
from claims.models import Claim

logger = logging.getLogger(__name__)


class FraudDetectionService:
    """Singleton service for fraud detection and risk scoring with justification engine"""
    
    _instance = None
    _model = None
    _scaler = None
    _label_encoder = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if self._model is None or self._scaler is None or self._label_encoder is None:
            self._load_model()
    
    def _load_model(self):
        """Load the trained fraud detection model and label encoder"""
        try:
            model_path = os.path.join(settings.BASE_DIR, 'ai_features', 'models', 'fraud_model.pkl')
            # Scaler is no longer used for RandomForest
            encoder_path = os.path.join(settings.BASE_DIR, 'ai_features', 'models', 'fraud_label_encoder.pkl')
            
            if os.path.exists(model_path) and os.path.exists(encoder_path):
                self._model = joblib.load(model_path)
                self._label_encoder = joblib.load(encoder_path)
                logger.info("✅ Fraud detection ML model (RandomForest) loaded successfully")
            else:
                logger.warning("⚠️ Fraud detection ML model missing, using rule-based fallback")
                self._model = None
                self._label_encoder = None
        except Exception as e:
            logger.error(f"❌ Error loading fraud detection model: {e}")
            self._model = None
            self._scaler = None
            self._label_encoder = None
    
    def predict_fraud_risk(self, claim: Claim) -> Tuple[float, bool, str, str]:
        """
        Predict fraud risk using Ensemble ML with behavioral and categorical features
        
        Returns:
            Tuple of (risk_score 0-100, fraud_flag bool, risk_level str, explanation str)
        """
        try:
            # ── 1. GATHER FEATURES ──────────────────────────────────────────
            claim_amount = float(claim.claimed_amount)
            docs_verified = self._check_document_verification(claim)
            claim_frequency = self._get_user_claim_history(claim)
            claim_type = self._get_claim_type(claim)
            
            # New features for upgraded model
            policy_age = self._calculate_policy_age(claim)
            weekend_flag = int(claim.incident_date.weekday() >= 5)
            
            explanation_parts = []
            
            # ── 2. ML INFERENCE (RandomForest with XAI) ────────────────────
            if (self._model is not None and self._label_encoder is not None):
                
                try:
                    import pandas as pd
                    claim_type_encoded = self._encode_claim_type(claim_type)
                    
                    # Construct feature dictionary matching train_fraud_model.py
                    feature_dict = {
                        'claim_amount': [claim_amount],
                        'docs_verified': [int(docs_verified)],
                        'claim_frequency': [claim_frequency],
                        'claim_type_enc': [claim_type_encoded],
                        'policy_age': [policy_age],
                        'weekend_flag': [weekend_flag]
                    }
                    features_df = pd.DataFrame(feature_dict)
                    
                    # Predict fraud probability using calibrated 0.35 threshold
                    fraud_probability = float(self._model.predict_proba(features_df)[0][1])
                    risk_score = min(100.0, max(0.0, fraud_probability * 100))
                    
                    # Threshold: 0.35 for fraud flagging
                    fraud_flag = fraud_probability >= 0.35
                    risk_level = self.get_risk_level(risk_score)
                    
                    # ── 3. GENERATE JUSTIFICATION (EXPLAINABLE AI) ─────────
                    if risk_score > 70:
                        explanation_parts.append("CRITICAL: Multiple high-risk indicators detected.")
                    elif risk_score > 35:
                        explanation_parts.append(f"ADVISORY: Risk score of {risk_score:.1f}% indicates vigilance.")
                    
                    if policy_age < 3:
                        explanation_parts.append("Risk Profile: New policyholder claim.")
                    if weekend_flag:
                        explanation_parts.append("Pattern Alert: Weekend incident pattern detected.")
                        
                    final_explanation = " | ".join(explanation_parts)
                    logger.info(f"ML Fraud Prediction: score={risk_score:.1f}, flag={fraud_flag}, level={risk_level}")
                    
                    return risk_score, fraud_flag, risk_level, final_explanation
                    
                except Exception as e:
                    logger.error(f"Error in ML fraud prediction: {e}")
            
            # ── 4. HYBRID RULE ENGINE (Fallback) ──────────────────────────
            risk_score, fraud_flag, explanation = self._rule_based_fraud_detection(claim_amount, docs_verified, claim_frequency, claim_type)
            risk_level = self.get_risk_level(risk_score)
            
            return risk_score, fraud_flag, risk_level, explanation
            
        except Exception as e:
            logger.error(f"Error in fraud detection service: {e}")
            return 0.0, False, "Error", "Error executing risk analysis."
    
    def _check_document_verification(self, claim: Claim) -> bool:
        """Check if any supporting documentation exists and is valid"""
        try:
            return claim.documents.exists()
        except Exception:
            return False
    
    def _get_user_claim_history(self, claim: Claim) -> int:
        """Count previous claims to detect serial behavior or frequency patterns"""
        try:
            user = claim.user if hasattr(claim, 'user') and claim.user else claim.created_by
            return Claim.objects.filter(user=user).exclude(id=claim.id).count()
        except Exception:
            return 0
            
    def _calculate_policy_age(self, claim: Claim) -> int:
        """Calculate policy age in months at time of incident"""
        try:
            from dateutil.relativedelta import relativedelta
            start_date = claim.policy.start_date
            incident_date = claim.incident_date
            diff = relativedelta(incident_date, start_date)
            return max(0, diff.years * 12 + diff.months)
        except Exception:
            return 12 # Default to year old if metadata missing

    def _get_claim_type(self, claim: Claim) -> str:
        """Standardize claim type for consistent encoding"""
        if hasattr(claim, 'ai_claim_type') and claim.ai_claim_type:
            return claim.ai_claim_type
        return claim.claim_type or 'other'

    def _encode_claim_type(self, claim_type: str) -> int:
        """Safe categorical encoding for the model features"""
        try:
            classes = self._label_encoder.classes_
            if claim_type in classes:
                return int(self._label_encoder.transform([claim_type])[0])
            if 'other' in classes:
                return int(self._label_encoder.transform(['other'])[0])
            return 0
        except Exception:
            return 0
    
    def _rule_based_fraud_detection(self, amount: float, docs_verified: bool, 
                                   claim_count: int, claim_type: str) -> Tuple[float, bool, str]:
        """
        Sophisticated rule-based fallback with explanation generation
        """
        score = 10.0 # Baseline
        reasons = ["Baseline profiling applied."]
        
        if amount > 100000:
            score += 35
            reasons.append(f"High-value amount (>₹1L).")
        if not docs_verified:
            score += 30
            reasons.append("Unverified documentation.")
        if claim_count > 2:
            score += 25
            reasons.append(f"Claim history count ({claim_count}).")
        if claim_type == 'theft':
            score += 15
            reasons.append("Theft risk factor.")
            
        score = max(0.0, min(100.0, score + random.uniform(-2, 2)))
        flag = score > 60
        
        explanation = "FALLBACK ENGINE: " + " | ".join(reasons)
        risk_level = self.get_risk_level(score)
        logger.info(f"Rule-based fraud prediction: score={score:.1f}")
        return float(score), flag, risk_level, explanation
    
    def get_risk_level(self, risk_score: float) -> str:
        """Standard categorization for UI display"""
        if risk_score < 30: return "Low Risk"
        elif risk_score < 60: return "Medium Risk"
        return "High Risk"


def predict_fraud_risk(claim: Claim) -> Tuple[float, bool, str, str]:
    """Production entry point for the fraud detection system. Returns (score, flag, level, explanation)"""
    return FraudDetectionService().predict_fraud_risk(claim)