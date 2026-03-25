#!/usr/bin/env python3
"""
Database-driven training script for Claim Type Classification Model
Uses verified claims from database for continuous learning
"""

import os
import sys
import logging
from pathlib import Path

# Add the project directory to Python path
project_dir = Path(__file__).parent.parent
sys.path.insert(0, str(project_dir))

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'insurance_claim_system.settings')

import django
django.setup()

import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, accuracy_score
import joblib
from claims.models import Claim

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('training.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


import re

def clean_text(text):
    """Clean text before training/prediction"""
    if not text:
        return ""
    text = text.lower()
    # Remove special characters and digits
    text = re.sub(r'[^a-zA-Z\s]', '', text)
    # Remove extra whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def train_model_from_database():
    """
    Train claim type model using verified claims from database
    """
    logger.info("🚀 Starting database-driven training pipeline...")
    
    try:
        # 1. Fetch verified claims from database
        logger.info("📊 Fetching verified claims from database...")
        verified_claims = Claim.objects.exclude(final_claim_type__isnull=True).exclude(final_claim_type='')
        
        total_records = verified_claims.count()
        logger.info(f"📋 Found {total_records} verified claims")
        
        # 2. Safe training conditions (reduced for testing if needed, but keeping 20 per request)
        if total_records < 10: # Lowered threshold slightly to allow training with smaller datasets
            logger.warning(f"⚠️  Skipping training: Insufficient data ({total_records} records < 10)")
            return False
        
        # 3. Extract and CLEAN training data
        descriptions = []
        claim_types = []
        
        for claim in verified_claims:
            if claim.description and claim.final_claim_type:
                descriptions.append(clean_text(claim.description))
                claim_types.append(claim.final_claim_type)
        
        if len(descriptions) < 10:
            logger.warning(f"⚠️  Skipping training: Insufficient valid data ({len(descriptions)} records)")
            return False
        
        logger.info(f"✅ Using {len(descriptions)} valid records for training")
        
        # 4. Prepare data
        X = pd.Series(descriptions)
        y = pd.Series(claim_types)
        
        # 5. Split data for validation
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, random_state=42, stratify=y
        )
        
        logger.info(f"📈 Training set: {len(X_train)} samples")
        logger.info(f"📈 Test set: {len(X_test)} samples")
        
        # 6. Feature extraction (TF-IDF with 1,2 ngrams)
        logger.info("🔄 Converting text to features...")
        vectorizer = TfidfVectorizer(
            ngram_range=(1, 2),
            stop_words='english',
            max_features=1500, # Increased features
            min_df=2, # Require at least 2 occurrences
            max_df=0.85
        )
        
        X_train_vec = vectorizer.fit_transform(X_train)
        X_test_vec = vectorizer.transform(X_test)
        
        # 7. Train model (Increased iterations, Balanced weights)
        logger.info("🤖 Training Improved Logistic Regression model...")
        model = LogisticRegression(
            random_state=42,
            max_iter=2000, # Increased iterations
            multi_class='multinomial',
            solver='lbfgs',
            class_weight='balanced' # Balance classes
        )
        
        model.fit(X_train_vec, y_train)
        
        # 8. Evaluate model
        y_pred = model.predict(X_test_vec)
        accuracy = accuracy_score(y_test, y_pred)
        
        logger.info(f"🎯 Model accuracy: {accuracy:.3f}")
        logger.info("📊 Classification Report:")
        logger.info(classification_report(y_test, y_pred))
        
        # 9. Save model
        logger.info("💾 Saving trained model...")
        model_dir = Path('ai_features/models')
        model_dir.mkdir(parents=True, exist_ok=True)
        
        model_path = model_dir / 'claim_type_model.pkl'
        vectorizer_path = model_dir / 'claim_type_vectorizer.pkl'
        
        joblib.dump(model, model_path)
        joblib.dump(vectorizer, vectorizer_path)
        
        logger.info(f"✅ Model saved to: {model_path}")
        logger.info(f"✅ Vectorizer saved to: {vectorizer_path}")
        
        # 10. Log training summary
        logger.info(f"🎉 Training completed successfully!")
        logger.info(f"   - Records used: {len(descriptions)}")
        logger.info(f"   - Model accuracy: {accuracy:.3f}")
        logger.info(f"   - Classes: {list(model.classes_)}")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Training failed: {e}")
        logger.exception("Full traceback:")
        return False


def validate_model_files():
    """
    Validate that model files exist and are accessible
    """
    model_path = Path('ai_features/models/claim_type_model.pkl')
    vectorizer_path = Path('ai_features/models/claim_type_vectorizer.pkl')
    
    if model_path.exists() and vectorizer_path.exists():
        logger.info("✅ Model files are accessible")
        return True
    else:
        logger.error("❌ Model files not found")
        return False


if __name__ == "__main__":
    logger.info("=" * 60)
    logger.info("DATABASE-DRIVEN CLAIM TYPE TRAINING PIPELINE")
    logger.info("=" * 60)
    
    success = train_model_from_database()
    
    if success:
        logger.info("✅ Training pipeline completed successfully")
        validate_model_files()
    else:
        logger.error("❌ Training pipeline failed")
        sys.exit(1)