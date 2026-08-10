import pandas as pd
import numpy as np
import xgboost as xgb
import shap
import pickle
import os
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_squared_error, r2_score

def train_risk_model(dataset_path="claims_dataset.csv", model_path="ai_features/models/risk_model.pkl"):
    """
    Trains an XGBoost regression model to predict claim risk score.
    Saves the model for use in the Django decision engine.
    """
    print(f"📂 Loading dataset from {dataset_path}...")
    if not os.path.exists(dataset_path):
        print(f"❌ Error: {dataset_path} not found.")
        return

    df = pd.read_csv(dataset_path)

    # 🎯 STEP 1: Feature Selection
    # These features are chosen because they directly impact insurance loss ratios
    features = [
        'non_medical', 
        'room_rent', 
        'allowed_room_rent', 
        'diagnostics', 
        'allowed_diagnostics', 
        'hospital_risk', 
        'user_risk', 
        'claim_frequency'
    ]
    target = 'risk_score'

    X = df[features]
    y = df[target]

    # ✂️ Dataset Split (80/20)
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

    print(f"🧠 Training XGBoost Regressor (n=300, depth=5)...")
    
    # ⚙️ Model Hyperparameters
    model = xgb.XGBRegressor(
        n_estimators=300,
        max_depth=5,
        learning_rate=0.05,
        objective='reg:squarederror',
        random_state=42
    )

    model.fit(X_train, y_train)

    # 📊 Evaluation
    predictions = model.predict(X_test)
    rmse = np.sqrt(mean_squared_error(y_test, predictions))
    r2 = r2_score(y_test, predictions)

    print(f"✅ Training Complete!")
    print(f"📈 Performance Metrics: RMSE = {rmse:.4f}, R2 Score = {r2:.4f}")

    # 🔍 SHAP Baseline (Required for explainability service)
    explainer = shap.TreeExplainer(model)
    expected_value = explainer.expected_value
    
    # 💾 Save Model and Metadata
    model_dir = os.path.dirname(model_path)
    if not os.path.exists(model_dir):
        os.makedirs(model_dir)
        
    model_data = {
        'model': model,
        'features': features,
        'explainer': explainer,
        'expected_value': expected_value
    }

    with open(model_path, 'wb') as f:
        pickle.dump(model_data, f)
        
    print(f"📦 Model saved to: {os.path.abspath(model_path)}")

if __name__ == "__main__":
    train_risk_model()
