import os
import joblib
import pandas as pd
import numpy as np
import xgboost as xgb
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score

def train_modern_risk_model():
    print("🚀 Starting Modern Risk Model Training (Ratio-Based)...")
    
    # 1. 📊 GENERATE SYNTHETIC DATA (Aligning with new requirements)
    # Features: non_medical_ratio, room_excess_ratio, diagnostic_ratio, hospital_risk, user_risk, claim_frequency
    np.random.seed(42)
    n_samples = 2000
    
    data = {
        'non_medical_ratio': np.random.uniform(0, 0.5, n_samples),
        'room_excess_ratio': np.random.uniform(0, 0.4, n_samples),
        'diagnostic_ratio': np.random.uniform(0, 0.3, n_samples),
        'hospital_risk': np.random.uniform(0, 0.8, n_samples),
        'user_risk': np.random.uniform(0, 0.6, n_samples),
        'claim_frequency': np.random.randint(1, 10, n_samples)
    }
    
    # Simple logic for target 'fraud'
    # Fraud probability increases with high ratios and risks
    prob = (
        data['non_medical_ratio'] * 2.0 + 
        data['room_excess_ratio'] * 1.5 + 
        data['hospital_risk'] * 1.2 + 
        data['user_risk'] * 1.0 +
        (data['claim_frequency'] > 5).astype(int) * 0.3
    )
    # Scale to 0-1 and add noise
    prob = (prob - prob.min()) / (prob.max() - prob.min())
    noise = np.random.normal(0, 0.05, n_samples)
    target = (prob + noise > 0.65).astype(int)
    
    df = pd.DataFrame(data)
    df['fraud'] = target
    
    features = ['non_medical_ratio', 'room_excess_ratio', 'diagnostic_ratio', 'hospital_risk', 'user_risk', 'claim_frequency']
    X = df[features]
    y = df['fraud']
    
    # 2. ✂️ SPLIT DATA
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
    
    # 3. 🦾 TRAIN XGBOOST
    model = xgb.XGBClassifier(
        n_estimators=100,
        max_depth=4,
        learning_rate=0.1,
        use_label_encoder=False,
        eval_metric='logloss'
    )
    
    model.fit(X_train, y_train)
    
    # 4. 📈 EVALUATE
    preds = model.predict(X_test)
    acc = accuracy_score(y_test, preds)
    print(f"📊 Model Training Complete. Accuracy: {acc:.4f}")
    
    # 5. 💾 SAVE MODEL WITH SCHEMA (Requirement: joblib.dump with keys 'model' and 'features')
    model_dir = "ai_features/models"
    if not os.path.exists(model_dir):
        os.makedirs(model_dir)
        
    model_path = os.path.join(model_dir, 'risk_model.pkl')
    # Save in requested format
    joblib.dump({
        "model": model,
        "features": features
    }, model_path)
    
    # Also save features separately for backward compatibility if needed by other components
    joblib.dump(features, os.path.join(model_dir, 'risk_features.pkl'))
    
    # Save a SHAP explainer as well to prevent runtime recomputation
    import shap
    explainer = shap.TreeExplainer(model)
    joblib.dump(explainer, os.path.join(model_dir, 'risk_shap_explainer.pkl'))
    
    print(f"✅ Model and Schema saved to {model_path}")

if __name__ == "__main__":
    train_modern_risk_model()
