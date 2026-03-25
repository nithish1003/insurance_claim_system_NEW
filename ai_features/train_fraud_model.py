#!/usr/bin/env python3
"""
Standardized Fraud Detection Model Training (v3)
Unified Algorithm: XGBoost Classifier
"""

import pandas as pd
import numpy as np
import os
import joblib
from sklearn.model_selection import train_test_split
from xgboost import XGBClassifier
from sklearn.metrics import classification_report, accuracy_score, precision_score, recall_score, f1_score, roc_auc_score
from sklearn.preprocessing import LabelEncoder

# Create datasets directory if it doesn't exist
os.makedirs('datasets', exist_ok=True)

def create_fraud_dataset():
    """Create synthetic dataset for fraud detection with expanded feature set"""
    np.random.seed(42)
    n_samples = 3000
    
    data = []
    for i in range(n_samples):
        claim_amount = np.random.lognormal(mean=10.5, sigma=0.8) 
        claim_amount = max(1000, min(1000000, float(claim_amount)))
        
        docs_verified = np.random.choice([True, False], p=[0.82, 0.18])
        claim_frequency = np.random.poisson(1.8)
        claim_type = np.random.choice(['theft', 'medical', 'accident', 'other'], p=[0.2, 0.4, 0.3, 0.1])
        
        policy_age = np.random.randint(0, 60)
        weekend_flag = np.random.choice([0, 1], p=[0.71, 0.29])
        
        fraud_prob = 0.05
        if claim_amount > 250000: fraud_prob += 0.40
        if not docs_verified: fraud_prob += 0.30
        if claim_frequency > 3: fraud_prob += 0.35
        if policy_age < 3: fraud_prob += 0.25
        if weekend_flag: fraud_prob += 0.15
        if claim_type == 'theft': fraud_prob += 0.10
        
        fraud_prob = max(0.0, min(1.0, fraud_prob + np.random.normal(0, 0.05)))
        is_fraud = np.random.random() < fraud_prob
        
        data.append({
            'claim_amount': float(claim_amount),
            'docs_verified': int(docs_verified),
            'claim_frequency': int(claim_frequency),
            'claim_type': str(claim_type),
            'policy_age': int(policy_age),
            'weekend_flag': int(weekend_flag),
            'fraud': int(is_fraud)
        })
    return pd.DataFrame(data)

def train_fraud_model():
    """Enterprise-Grade Fraud Model: Imbalance-Aware & Calibrated"""
    from sklearn.calibration import CalibratedClassifierCV
    
    print("🚀 Enterprise Training: Fraud Model (v3.6)...")
    df = create_fraud_dataset()
    
    le = LabelEncoder()
    df['claim_type_enc'] = le.fit_transform(df['claim_type'])
    
    feature_cols = ['claim_amount', 'docs_verified', 'claim_frequency', 'claim_type_enc', 'policy_age', 'weekend_flag']
    X = df[feature_cols]
    y = df['fraud']
    
    # Calculate scale_pos_weight for class imbalance
    # This ensures the model pays more attention to the minority (fraud) class
    negative_count = sum(y == 0)
    positive_count = sum(y == 1)
    scale_weight = negative_count / positive_count if positive_count > 0 else 1.0
    print(f"⚖️ Handling Class Imbalance: Scale Weight = {scale_weight:.2f}")

    # 80/20 Split with Stratification
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)
    
    # ── ENTERPRISE XGBOOST CONFIG ──
    xgb_base = XGBClassifier(
        n_estimators=300, # Increased for more capacity
        max_depth=6,
        learning_rate=0.05, # Slower learning for robustness
        scale_pos_weight=scale_weight, # 🎯 KEY: Handle imbalance
        subsample=0.8,
        colsample_bytree=0.8,
        random_state=42,
        use_label_encoder=False,
        eval_metric='aucpr' # Optimize for PR curve in imbalanced data
    )
    
    # ── CALIBRATION ──
    # Using 'prefit=False' as CalibratedClassifierCV will fit base on CV folds
    print("🤖 Calibrating Model (Isotonic Regression for large samples)...")
    model = CalibratedClassifierCV(xgb_base, method='isotonic', cv=3)
    model.fit(X_train, y_train)
    
    # ── EVALUATION ──
    y_proba = model.predict_proba(X_test)[:, 1]
    y_pred = (y_proba >= 0.5).astype(int)
    
    acc = accuracy_score(y_test, y_pred)
    prec = precision_score(y_test, y_pred)
    rec = recall_score(y_test, y_pred)
    f1 = f1_score(y_test, y_pred)
    
    print(f"\n📊 Enterprise Metrics (v3.6):")
    print(f"   Accuracy:  {acc:.2%}")
    print(f"   Precision: {prec:.2%}")
    print(f"   Recall (Imbalance-Fixed): {rec:.2%}")
    print(f"   F1 Score:  {f1:.2%}")
    
    # Save Artifacts
    model_dir = os.path.join('ai_features', 'models')
    os.makedirs(model_dir, exist_ok=True)
    
    joblib.dump(model, os.path.join(model_dir, 'fraud_model_v3.pkl'))
    joblib.dump(le, os.path.join(model_dir, 'fraud_label_encoder_v3.pkl'))
    joblib.dump(feature_cols, os.path.join(model_dir, 'fraud_features_v3.pkl'))
    
    print(f"✅ Enterprise Fraud model saved to {model_dir}")
    return model, le

if __name__ == "__main__":
    train_fraud_model()