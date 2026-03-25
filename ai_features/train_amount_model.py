#!/usr/bin/env python3
"""
Standardized Amount Prediction Model Training (v3)
Unified Algorithm: XGBoost Regressor
"""

import pandas as pd
import numpy as np
import os
import joblib
import shap
from sklearn.model_selection import train_test_split
from xgboost import XGBRegressor
from sklearn.preprocessing import LabelEncoder
from sklearn.metrics import mean_absolute_error, r2_score, mean_squared_error

# Create datasets directory if it doesn't exist
os.makedirs('datasets', exist_ok=True)

def create_advanced_claim_dataset(n_samples=5000):
    """Create high-fidelity synthetic dataset for health insurance claims"""
    np.random.seed(42)
    
    data = []
    for i in range(n_samples):
        claimed_amount = np.random.lognormal(mean=10.2, sigma=1.1) 
        claimed_amount = max(3000, min(1500000, float(claimed_amount)))
        
        sum_insured = np.random.choice([100000, 200000, 300000, 500000, 1000000])
        deductible = np.random.choice([0, 2500, 5000, 7500, 10000])
        coverage_pct = np.random.uniform(0.7, 1.0) 
        
        patient_age = np.random.randint(18, 85)
        hospital_type = np.random.choice(['private', 'government', 'network'], p=[0.4, 0.2, 0.4])
        
        admission_days = np.random.poisson(lam=4) + 1  
        diagnosis_severity = np.random.randint(1, 6) 
        num_tests = np.random.randint(1, 10)
        
        medication_cost = claimed_amount * np.random.uniform(0.15, 0.4)
        room_rent = (claimed_amount * 0.2) + (admission_days * np.random.uniform(1000, 4000))
        
        fraud_risk = np.random.beta(a=2, b=6) * 100 
        past_claims = np.random.poisson(lam=0.8)
        
        net_claimable = max(0.0, claimed_amount - deductible)
        medication_ratio = medication_cost / claimed_amount
        room_rent_ratio = room_rent / claimed_amount
        claim_si_ratio = claimed_amount / sum_insured
        cost_per_day = claimed_amount / admission_days
        high_cost_flag = 1 if claimed_amount > 200000 else 0
        
        base_payout = net_claimable * coverage_pct
        severity_factor = 1.0 + (diagnosis_severity * 0.05) 
        fraud_multiplier = 1.0 - (fraud_risk / 200) 
        hospital_factor = {'private': 0.92, 'government': 1.0, 'network': 0.96}.get(hospital_type, 0.95)
        
        audit_variance = np.random.normal(0.96, 0.04) 
        recommended_amount = base_payout * severity_factor * fraud_multiplier * hospital_factor * audit_variance
        
        recommended_amount = max(0.0, min(claimed_amount, float(recommended_amount)))
        
        data.append({
            'claimed_amount': float(claimed_amount),
            'deductible': float(deductible),
            'net_claimable': float(net_claimable),
            'coverage_pct': float(coverage_pct),
            'sum_insured': float(sum_insured),
            'patient_age': int(patient_age),
            'hospital_type': str(hospital_type),
            'admission_days': int(admission_days),
            'diagnosis_severity': int(diagnosis_severity),
            'num_tests': int(num_tests),
            'medication_ratio': float(medication_ratio),
            'room_rent_ratio': float(room_rent_ratio),
            'fraud_risk': float(fraud_risk),
            'past_claims': int(past_claims),
            'claim_si_ratio': float(claim_si_ratio),
            'cost_per_day': float(cost_per_day),
            'high_cost_flag': int(high_cost_flag),
            'recommended_amount': float(recommended_amount)
        })
    return pd.DataFrame(data)

def train_amount_model():
    """Build and Save the hardened XGBoost Amount Model (v3)"""
    print("🚀 Hardening Amount Model Pipeline for Production (v3)...")
    df = create_advanced_claim_dataset(5000)
    
    le_hospital = LabelEncoder()
    df['hospital_type_enc'] = le_hospital.fit_transform(df['hospital_type'])
    
    # Target transformation (Log)
    y = np.log1p(df['recommended_amount'])
    
    features = [
        'claimed_amount', 'deductible', 'net_claimable', 'coverage_pct', 
        'patient_age', 'hospital_type_enc', 'admission_days', 'diagnosis_severity',
        'num_tests', 'medication_ratio', 'room_rent_ratio', 'fraud_risk', 
        'past_claims', 'claim_si_ratio', 'cost_per_day', 'high_cost_flag'
    ]
    X = df[features]
    
    # 80/20 Split
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
    
    # ── XGBOOST STANDARDIZATION ─────────────────────────────────────────
    print("🤖 Training XGBRegressor (Standardized)...")
    model = XGBRegressor(
        n_estimators=200,
        max_depth=6,
        learning_rate=0.1,
        subsample=0.8,
        colsample_bytree=0.8,
        random_state=42,
        n_jobs=-1
    )
    
    model.fit(X_train, y_train)
    
    # ── METRICS & BUSINESS CONSTRAINTS ───────────────────────────────────
    y_pred_log = model.predict(X_test)
    y_pred = np.expm1(y_pred_log)
    y_test_real = np.expm1(y_test)
    
    # Financial Validation: Ensure predicted payout never exceeds claimed amount
    claimed_test = X_test['claimed_amount'].values
    violation_count = np.sum(y_pred > claimed_test)
    
    mae = mean_absolute_error(y_test_real, y_pred)
    mse = mean_squared_error(y_test_real, y_pred)
    rmse = np.sqrt(mse)
    r2 = r2_score(y_test, y_pred_log)
    
    print(f"\n📊 Hardened Amount Model Performance:")
    print(f"   MAE:  ₹{mae:.2f}")
    print(f"   RMSE: ₹{rmse:.2f}")
    print(f"   R2 Score:   {r2:.4f}")
    print(f"   ⚠️ Constraint Violations: {violation_count} / {len(y_pred)}")
    
    # Save Artifacts
    model_dir = os.path.join('ai_features', 'models')
    os.makedirs(model_dir, exist_ok=True)
    
    # ── FEATURE CONSISTENCY ──────────────────────────────────────────────
    joblib.dump(model, os.path.join(model_dir, 'amount_model_v3.pkl'))
    joblib.dump(le_hospital, os.path.join(model_dir, 'hospital_label_encoder_v3.pkl'))
    joblib.dump(features, os.path.join(model_dir, 'amount_features_v3.pkl')) # Save schema
    
    # SHAP Explainer
    print("\n🔍 Fitting and Persisting SHAP Explainer...")
    explainer = shap.TreeExplainer(model)
    joblib.dump(explainer, os.path.join(model_dir, 'amount_shap_explainer_v3.pkl'))
    
    print(f"✅ Hardened Amount model artifacts saved to {model_dir}")
    return model

if __name__ == "__main__":
    train_amount_model()