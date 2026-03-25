#!/usr/bin/env python3
"""
Standardized Claim Type Classification Model Training (v3)
Unified Algorithm: XGBoost Classifier (with TF-IDF Pipeline)
"""

import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.feature_extraction.text import TfidfVectorizer
from xgboost import XGBClassifier
from sklearn.metrics import classification_report, accuracy_score, precision_score, recall_score, f1_score
import joblib
import os
import re

# Create datasets directory if it doesn't exist
os.makedirs('datasets', exist_ok=True)

def create_claim_type_dataset():
    """Create synthetic dataset for claim type classification"""
    data = [
        ("I was involved in a car accident on the highway", "accident"),
        ("My vehicle collided with another car at the intersection", "accident"),
        ("I had a motorcycle accident while riding", "accident"),
        ("Slipped and fell at work causing injury", "accident"),
        ("Workplace accident with machinery", "accident"),
        ("Traffic accident with injuries", "accident"),
        ("Fell down stairs and hurt my back", "accident"),
        ("Sports injury during game", "accident"),
        ("Bicycle accident on road", "accident"),
        ("Hit by falling object at construction site", "accident"),
        ("Hospitalized for heart surgery", "medical"),
        ("Treatment for cancer diagnosis", "medical"),
        ("Medical expenses for diabetes management", "medical"),
        ("Hospital bill for appendectomy", "medical"),
        ("Doctor consultation and medication", "medical"),
        ("MRI scan and specialist consultation", "medical"),
        ("Dental treatment and crowns", "medical"),
        ("Eye surgery for cataract", "medical"),
        ("Physical therapy after injury", "medical"),
        ("Prescription medication costs", "medical"),
        ("My car was stolen from parking lot", "theft"),
        ("House burglary with valuable items stolen", "theft"),
        ("Laptop stolen from office desk", "theft"),
        ("Phone snatched while walking", "theft"),
        ("Bicycle stolen from apartment complex", "theft"),
        ("Wallet stolen with credit cards", "theft"),
        ("Jewelry stolen during vacation", "theft"),
        ("Property damage from fire", "other"),
        ("Natural disaster damage to home", "other"),
        ("Third party liability claim", "other"),
        ("Travel insurance claim", "other"),
    ]
    
    descriptions = [item[0] for item in data]
    labels = [item[1] for item in data]
    
    for i in range(200):
        idx = np.random.randint(0, len(data))
        base_desc, label = data[idx]
        variations = [
            f"{base_desc} last week",
            f"I need to claim for {base_desc}",
            f"Regarding {base_desc} - please process",
            f"Emergency {base_desc} situation",
            f"Submitted claim for {base_desc}",
        ]
        descriptions.append(np.random.choice(variations))
        labels.append(label)
    
    return pd.DataFrame({'description': descriptions, 'claim_type': labels})

def clean_text(text):
    if not text: return ""
    text = text.lower()
    text = re.sub(r'[^a-zA-Z\s]', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def train_claim_type_model():
    """Enterprise-Grade NLP Model: Overfitting Protection & Calibration"""
    from sklearn.calibration import CalibratedClassifierCV
    
    print("🚀 Enterprise Training: Claim Type Model (v3.6)...")
    df = create_claim_type_dataset()
    df['description'] = df['description'].apply(clean_text)
    
    X = df['description']
    y = df['claim_type']
    
    # Label Encoding
    from sklearn.preprocessing import LabelEncoder
    le = LabelEncoder()
    y_enc = le.fit_transform(y)
    
    # 80/20 Split with Stratification
    X_train, X_test, y_train, y_test = train_test_split(X, y_enc, test_size=0.2, random_state=42, stratify=y_enc)
    
    # TF-IDF with stricter parameters to prevent overfitting
    print("📝 Vectorizing text data (Low-noise config)...")
    tfidf = TfidfVectorizer(
        max_features=1000, # Reduced to top 1000 to prevent sparse overfitting
        stop_words='english',
        ngram_range=(1, 2),
        min_df=2 # Ensure keywords appear in multiple samples
    )
    X_train_vec = tfidf.fit_transform(X_train)
    X_test_vec = tfidf.transform(X_test)
    
    # ── ENTERPRISE XGBOOST CONFIG ──
    xgb_base = XGBClassifier(
        n_estimators=300,
        max_depth=5, # Shallower trees = less overfitting
        learning_rate=0.05,
        reg_alpha=0.1, # L1 Regularization
        reg_lambda=1.0, # L2 Regularization
        subsample=0.8,
        colsample_bytree=0.8,
        random_state=42,
        use_label_encoder=False,
        eval_metric='mlogloss'
    )
    
    # ── CALIBRATION ──
    print("🤖 Calibrating NLP Model (Isotonic)...")
    model = CalibratedClassifierCV(xgb_base, method='isotonic', cv=3)
    model.fit(X_train_vec, y_train)
    
    # ── EVALUATION ──
    y_proba = model.predict_proba(X_test_vec)
    y_pred = np.argmax(y_proba, axis=1)
    
    acc = accuracy_score(y_test, y_pred)
    print(f"\n📊 Enterprise NLP Performance (v3.6):")
    print(f"   Accuracy: {acc:.2%}")
    print("\n   Detailed Report:")
    print(classification_report(y_test, y_pred, target_names=le.classes_))
    
    # Save Artifacts
    model_dir = os.path.join('ai_features', 'models')
    os.makedirs(model_dir, exist_ok=True)
    
    joblib.dump(model, os.path.join(model_dir, 'claim_type_model_v3.pkl'))
    joblib.dump(tfidf, os.path.join(model_dir, 'claim_type_vectorizer_v3.pkl'))
    joblib.dump(le, os.path.join(model_dir, 'claim_type_label_encoder_v3.pkl'))
    
    print(f"✅ Enterprise Claim type model saved to {model_dir}")
    return model

if __name__ == "__main__":
    train_claim_type_model()