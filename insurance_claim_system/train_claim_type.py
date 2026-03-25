import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
import joblib

# 📂 Load dataset
data = pd.read_csv("insurance_claim_system/dataset_claim_type.csv")

# 🧠 Input (X) and Output (y)
X = data["description"]
y = data["claim_type"]

# 🔄 Convert text → numbers
vectorizer = TfidfVectorizer()
X_vec = vectorizer.fit_transform(X)

# 🤖 Train model
model = LogisticRegression()
model.fit(X_vec, y)

# 💾 Save model
joblib.dump(model, "claim_model.pkl")
joblib.dump(vectorizer, "vectorizer.pkl")

print("✅ Model trained and saved successfully!")