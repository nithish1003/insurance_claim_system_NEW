#!/usr/bin/env python3
"""
Enterprise Risk Scoring Model Training (XGBoost)
Target: risk_score [0, 1]
Explainability: SHAP
"""

import pandas as pd
import numpy as np
import xgboost as xgb
import shap
import joblib
import os
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_squared_error

# 1. 🏗️ DATASET GENERATION (High-Fidelity Synthetic)
def generate_risk_dataset(n_samples=5000):
    np.random.seed(42)
    
    # Raw Inputs
    claim_amount = np.random.lognormal(10.5, 0.8, n_samples)
    deductible = np.random.uniform(500, 15000, n_samples)
    non_medical = np.random.uniform(100, 5000, n_samples)
    room_rent = np.random.uniform(2000, 15000, n_samples)
    allowed_room_rent = np.random.uniform(2000, 6000, n_samples)
    diagnostics = np.random.uniform(1000, 10000, n_samples)
    allowed_diagnostics = np.random.uniform(1000, 4000, n_samples)
    hospital_risk = np.random.uniform(0, 0.3, n_samples)
    user_risk = np.random.uniform(0, 0.2, n_samples)
    claim_frequency = np.random.poisson(1.5, n_samples)

    # Derived Features (Engineering)
    non_medical_ratio = non_medical / claim_amount
    room_excess_ratio = np.maximum(0, (room_rent - allowed_room_rent) / allowed_room_rent)
    diagnostic_ratio = np.maximum(0, (diagnostics - allowed_diagnostics) / allowed_diagnostics)

    # 🎯 TARGET CALCULATION (Deterministic + Noise)
    # This ensures the model CAN learn the auditability rules provided in the prompt.
    risk_score = (
        (non_medical_ratio * 0.35) +
        (np.minimum(1.0, room_excess_ratio) * 0.25) +
        (np.minimum(1.0, diagnostic_ratio) * 0.20) +
        (hospital_risk * 0.15) +
        (user_risk * 0.10) +
        (np.minimum(1.0, claim_frequency / 5.0) * 0.05)
    )
    
    # Add noise but clip to [0, 1]
    risk_score = np.clip(risk_score + np.random.normal(0, 0.01, n_samples), 0, 1)

    df = pd.DataFrame({
        'claim_amount': claim_amount,
        'deductible': deductible,
        'non_medical': non_medical,
        'room_rent': room_rent,
        'allowed_room_rent': allowed_room_rent,
        'diagnostics': diagnostics,
        'allowed_diagnostics': allowed_diagnostics,
        'hospital_risk': hospital_risk,
        'user_risk': user_risk,
        'claim_frequency': claim_frequency,
        'non_medical_ratio': non_medical_ratio,
        'room_excess_ratio': room_excess_ratio,
        'diagnostic_ratio': diagnostic_ratio,
        'risk_score': risk_score
    })
    
    os.makedirs('datasets', exist_ok=True)
    df.to_csv('datasets/risk_scoring_data.csv', index=False)
    print(f"✅ Generated dataset: datasets/risk_scoring_data.csv ({n_samples} samples)")
    return df

# 2. 🦾 MODEL TRAINING (XGBRegressor)
def train_risk_model():
    print("🚀 Initializing XGBoost Risk Engine Training...")
    df = generate_risk_dataset()
    
    # Explicit Features for Training
    features = [
        'non_medical_ratio',
        'room_excess_ratio',
        'diagnostic_ratio',
        'hospital_risk',
        'user_risk',
        'claim_frequency'
    ]
    
    X = df[features]
    y = df['risk_score']
    
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
    
    # XGBRegressor specialized for continuous risk scoring
    model = xgb.XGBRegressor(
        objective='reg:logistic', # Since risk_score is in [0, 1]
        n_estimators=500,
        max_depth=5,
        learning_rate=0.03,
        subsample=0.8,
        colsample_bytree=0.8,
        random_state=42
    )
    
    model.fit(X_train, y_train)
    
    # 3. 📉 EVALUATION
    preds = model.predict(X_test)
    rmse = np.sqrt(mean_squared_error(y_test, preds))
    print(f"📊 Training RMSE: {rmse:.4f} (Max possible error: 1.0)")
    
    # 4. 🧠 SHAP INTEGRATION (Explainability Registry)
    explainer = shap.TreeExplainer(model)
    
    # 💾 SAVE ARTIFACTS
    model_dir = os.path.join('ai_features', 'models')
    os.makedirs(model_dir, exist_ok=True)
    
    joblib.dump(model, os.path.join(model_dir, 'risk_model.pkl'))
    joblib.dump(explainer, os.path.join(model_dir, 'risk_shap_explainer.pkl'))
    joblib.dump(features, os.path.join(model_dir, 'risk_features.pkl'))
    
    print(f"✅ Risk artifacts saved to {model_dir}")
    return model, explainer

if __name__ == "__main__":
    train_risk_model()
