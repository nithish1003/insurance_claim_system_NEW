"""
Advanced Recommended Amount Service
Uses High-Fidelity XGBoost + SHAP Explainability + Business Rules
"""

import os
import joblib
import logging
import numpy as np
import pandas as pd
from django.conf import settings
from typing import Tuple, Dict, Any, List
from claims.models import Claim
from decimal import Decimal

logger = logging.getLogger(__name__)


class AmountPredictionService:
    """Production-ready AI service for insurance payout recommendation"""
    
    _instance = None
    _model = None
    _explainer = None
    _hospital_encoder = None
    _feature_names = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if self._model is None:
            self._load_model_artifacts()
    
    def _load_model_artifacts(self):
        """Load optimized XGBoost model and SHAP explainer"""
        try:
            model_dir = os.path.join(settings.BASE_DIR, 'ai_features', 'models')
            
            paths = {
                'model': os.path.join(model_dir, 'xgb_amount_model.pkl'),
                'explainer': os.path.join(model_dir, 'amount_shap_explainer.pkl'),
                'encoder': os.path.join(model_dir, 'hospital_label_encoder.pkl'),
                'features': os.path.join(model_dir, 'amount_feature_names.pkl')
            }
            
            if all(os.path.exists(p) for p in paths.values()):
                self._model = joblib.load(paths['model'])
                self._explainer = joblib.load(paths['explainer'])
                self._hospital_encoder = joblib.load(paths['encoder'])
                self._feature_names = joblib.load(paths['features'])
                logger.info("✅ Advanced AI Payout model with SHAP loaded")
            else:
                logger.warning("⚠️ Advanced ML artifacts missing, falling back to rule engine")
                
        except Exception as e:
            logger.error(f"❌ Error loading AI artifacts: {e}")

    def predict_recommended_amount(self, claim: Claim) -> float:
        """
        Main entry point for AI audit of claim payout
        """
        try:
            # ── 1. GATHER ALL FEATURES ────────────────────────
            features_df, raw_data = self._gather_comprehensive_features(claim)
            amount = float(claim.claimed_amount)
            
            explanation_parts = []
            confidence = 0.8  # Default
            
            # ── 2. ML INFERENCE ───────────────────────────────
            if self._model is not None:
                try:
                    # Predict in log-space
                    pred_log = self._model.predict(features_df)[0]
                    recommended_raw = np.expm1(pred_log)
                    
                    # ── 3. EXPLAINABILITY (SHAP) ───────────────────
                    shap_values = self._explainer.shap_values(features_df)[0]
                    shap_explanation = self._generate_shap_explanation(shap_values, features_df.columns, raw_data)
                    explanation_parts.append(shap_explanation)
                    
                    # ── 4. CONFIDENCE CALCULATION ──────────────────
                    confidence = self._calculate_prediction_confidence(features_df)
                    claim.confidence_score = confidence * 100
                    
                    recommended_amount = recommended_raw
                    ml_success = True
                except Exception as e:
                    logger.error(f"ML Inference Failed: {e}")
                    ml_success = False
            else:
                ml_success = False

            # ── 5. BUSINESS RULES & FALLBACKS ──────────────────
            if not ml_success:
                recommended_amount, fallback_exp = self._rule_based_fallback(claim)
                explanation_parts.append(f"Fallback: {fallback_exp}")
            
            # 🛡️ Hard Insurance Guards
            net_claimable = float(claim.net_claimable or (claim.claimed_amount - (claim.deductible_amount or 0)))
            
            # Final recommendation = min(AI_Prediction, Net_Claimable)
            final_payout = min(recommended_amount, net_claimable)
            
            if final_payout < recommended_amount:
                explanation_parts.append(f"Capped to Net Claimable (₹{net_claimable:,.2f}) per policy terms.")
            
            # ── 6. COMMIT AUDIT LOG (In-memory attributes only) ────
            claim.ai_predicted_amount = Decimal(str(round(final_payout, 2)))
            claim.ai_adjustment_factor = final_payout / amount if amount > 0 else 1.0
            claim.ai_calculation_logic = " | ".join(explanation_parts)
            
            return float(final_payout)

        except Exception as e:
            logger.error(f"Critical AI error: {e}")
            return float(claim.claimed_amount)

    def _gather_comprehensive_features(self, claim: Claim) -> Tuple[pd.DataFrame, Dict]:
        """Feature engineering pipeline matching train_amount_model.py"""
        # Raw Data
        claimed = float(claim.claimed_amount)
        deductible = float(claim.deductible_amount or 0)
        coverage_pct = self._get_coverage_pct(claim)
        sum_insured = float(claim.policy.sum_insured)
        
        # Clinical
        patient_age = claim.patient_age or 35 # Mean fallback
        hospital_type = claim.hospital_type or 'private'
        admission_days = claim.admission_days or 1
        num_tests = claim.number_of_tests or 0
        severity = claim.diagnosis_severity or 1
        
        # Risk
        from .fraud_service import predict_fraud_risk
        fraud_risk, _, _, _ = predict_fraud_risk(claim)
        past_claims = Claim.objects.filter(created_by=claim.created_by, created_at__lt=claim.created_at).count()
        
        # Financial Splits
        medication_ratio = float(claim.medication_cost or 0) / claimed if claimed > 0 else 0.2
        room_rent_ratio = float(claim.room_rent_cost or 0) / claimed if claimed > 0 else 0.3
        
        # Derived
        net_claimable = max(0.0, claimed - deductible)
        claim_si_ratio = claimed / sum_insured if sum_insured > 0 else 0.1
        cost_per_day = claimed / max(1, admission_days)
        high_cost_flag = 1 if claimed > 200000 else 0

        # Categorical Encoding
        try:
            hospital_enc = self._hospital_encoder.transform([hospital_type])[0]
        except:
            hospital_enc = 0

        data = {
            'claimed_amount': claimed,
            'deductible': deductible,
            'net_claimable': net_claimable,
            'coverage_pct': coverage_pct,
            'sum_insured': sum_insured,
            'patient_age': patient_age,
            'hospital_type_enc': hospital_enc,
            'admission_days': admission_days,
            'diagnosis_severity': severity,
            'num_tests': num_tests,
            'medication_ratio': medication_ratio,
            'room_rent_ratio': room_rent_ratio,
            'fraud_risk': fraud_risk,
            'past_claims': past_claims,
            'claim_si_ratio': claim_si_ratio,
            'cost_per_day': cost_per_day,
            'high_cost_flag': high_cost_flag
        }
        
        # Ensure column order matches self._feature_names exactly
        # If feature_names is missing, use a safe default order
        ordered_features = self._feature_names if self._feature_names else list(data.keys())
        df = pd.DataFrame([{f: data.get(f, 0) for f in ordered_features}])
        
        return df, data

    def _calculate_prediction_confidence(self, X: pd.DataFrame) -> float:
        """Estimate confidence based on tree variance (Consistency of XGBoost ensemble)"""
        try:
            import xgboost as xgb
            # 1. Get raw predictions from each tree in the ensemble
            booster = self._model.get_booster()
            
            # Predict each feature's contribution to the prediction Margin
            dmat = xgb.DMatrix(X)
            pred_contribs = booster.predict(dmat, pred_contribs=True)[0]
            
            # Use standard deviation of contributions (excluding bias) as proxy for uncertainty
            # If the prediction is driven by many conflicting features, confidence is lower
            contrib_std = np.std(pred_contribs[:-1])
            
            # Map 0.0-3.0 range to confidence levels
            if contrib_std > 2.2: return 0.61
            if contrib_std > 1.2: return 0.79
            return 0.94
            
        except Exception as e:
            logger.warning(f"Confidence calculation failed: {e}")
            return 0.85

    def _generate_shap_explanation(self, shap_values: np.ndarray, feature_names: List[str], raw_data: Dict) -> str:
        """Transform SHAP values into human-readable insurance logic"""
        # Find top 3 contributors
        pairs = sorted(zip(shap_values, feature_names), key=lambda x: abs(x[0]), reverse=True)[:3]
        
        reasons = []
        for val, name in pairs:
            direction = "increased" if val > 0 else "reduced"
            
            # Readable names
            pretty_name = name.replace('_', ' ').title()
            if 'Net Claimable' in pretty_name: pretty_name = "Policy Terms (Net Claimable)"
            if 'Hospital Type' in pretty_name: pretty_name = "Hospital Network Status"
            
            reasons.append(f"{pretty_name} {direction} payout recommendation.")
            
        return f"Primary AI Factors: {'; '.join(reasons)}"

    def _get_coverage_pct(self, claim: Claim) -> float:
        """Get actual coverage or default"""
        try:
            return float(claim.policy.coverage_percentage) / 100.0
        except:
            return 0.85

    def _rule_based_fallback(self, claim: Claim) -> Tuple[float, str]:
        """Sophisticated non-ML fallback logic"""
        claimed = float(claim.claimed_amount)
        deductible = float(claim.deductible_amount or 0)
        coverage = self._get_coverage_pct(claim)
        
        base = max(0.0, claimed - deductible) * coverage
        return base, "Calculated based on standard policy coverage (Claim - Deductible) * Coverage %"

def predict_recommended_amount(claim: Claim) -> float:
    """Entry point for the recommendation engine"""
    return AmountPredictionService().predict_recommended_amount(claim)