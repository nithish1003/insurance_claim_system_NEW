"""
AI Claim Type Service
Uses ML model to predict claim type from description text
"""

import os
import joblib
import logging
from django.conf import settings
from typing import Tuple

logger = logging.getLogger(__name__)


class AIClaimService:
    """Singleton service for AI claim type prediction"""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(AIClaimService, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        if not hasattr(self, "_initialized"):
            self._model = None
            self._vectorizer = None
            self._model_path = None
            self._vectorizer_path = None
            self._load_model()
            self._initialized = True

    def _load_model(self):
        """Load ML model and vectorizer with fallback support"""
        try:
            # Try to load database-trained models first
            model_path = os.path.join(settings.BASE_DIR, "ai_features", "models", "claim_type_model.pkl")
            vectorizer_path = os.path.join(settings.BASE_DIR, "ai_features", "models", "claim_type_vectorizer.pkl")

            if os.path.exists(model_path) and os.path.exists(vectorizer_path):
                self._model = joblib.load(model_path)
                self._vectorizer = joblib.load(vectorizer_path)
                self._model_path = model_path
                self._vectorizer_path = vectorizer_path
                logger.info("✅ Database-trained ML model and vectorizer loaded successfully")
            else:
                # Fallback to CSV-trained models
                model_path = os.path.join(settings.BASE_DIR, "claim_model.pkl")
                vectorizer_path = os.path.join(settings.BASE_DIR, "vectorizer.pkl")

                if os.path.exists(model_path) and os.path.exists(vectorizer_path):
                    self._model = joblib.load(model_path)
                    self._vectorizer = joblib.load(vectorizer_path)
                    self._model_path = model_path
                    self._vectorizer_path = vectorizer_path
                    logger.info("✅ CSV-trained ML model and vectorizer loaded as fallback")
                else:
                    logger.warning("⚠️ No model files found, using rule-based fallback only")
                    self._model = None
                    self._vectorizer = None

        except Exception as e:
            logger.error(f"❌ Error loading model: {e}")
            self._model = None
            self._vectorizer = None

    def clean_text(self, text):
        """Standardize text for consistent prediction accuracy"""
        import re
        if not text: return ""
        text = text.lower().strip()
        text = re.sub(r'[^a-z\s]', '', text)
        return re.sub(r'\s+', ' ', text)

    def predict_claim_type(self, description: str) -> Tuple[str, float]:
        """Predict claim type using ML with an intelligent rule-based hybrid fallback"""

        if not description or not description.strip():
            return "other", 0.0

        # 🧹 Sanitize input
        cleaned_text = self.clean_text(description)
        
        # ✅ ML Prediction
        if self._model is not None and self._vectorizer is not None:
            try:
                vec = self._vectorizer.transform([cleaned_text])
                prediction = self._model.predict(vec)[0]
                probabilities = self._model.predict_proba(vec)[0]
                confidence = float(max(probabilities))
                prediction = self._model.classes_[probabilities.argmax()].lower()

                # 🛡️ Confidence-based Routing
                # If confidence is below 0.6, we flag for manual review
                if confidence < 0.60:
                    logger.warning(f"⚠️ Low confidence ({confidence:.2f}) for prediction '{prediction}'. Routing to manual review.")
                    return "manual_review", confidence

                logger.info(f"ML prediction: {prediction} (Confidence: {confidence:.2f})")
                return prediction, confidence

            except Exception as e:
                logger.error(f"ML prediction failed: {e}")

        # 🔥 Traditional Fallback
        return self._rule_based_prediction(description)

    def _rule_based_prediction(self, description: str) -> Tuple[str, float]:
        """Engineered fallback logic with dynamic confidence scaling based on keyword density"""

        description_lower = description.lower().strip()

        accident_keywords = [
            'accident', 'collision', 'crash', 'injury', 'fall', 'slip',
            'broken', 'hit', 'damage', 'vehicle', 'car', 'bike'
        ]

        medical_keywords = [
            'hospital', 'surgery', 'treatment', 'doctor', 'medical',
            'health', 'fever', 'pain', 'admitted', 'consultation'
        ]

        theft_keywords = [
            'stolen', 'theft', 'robbery', 'missing', 'taken', 'snatched',
            'burglary', 'stole', 'lost'
        ]

        accident_score = sum(1 for k in accident_keywords if k in description_lower)
        medical_score = sum(1 for k in medical_keywords if k in description_lower)
        theft_score = sum(1 for k in theft_keywords if k in description_lower)

        max_score = max(accident_score, medical_score, theft_score)

        if max_score == 0:
            return "other", 0.4 # Baseline confidence if no keywords found

        # Dynamic confidence based on keyword density
        # More keywords = higher certainty in the fallback
        confidence = min(0.95, 0.5 + (max_score * 0.1))

        if accident_score == max_score:
            return "accident", confidence
        elif medical_score == max_score:
            return "medical", confidence
        else:
            return "theft", confidence

    def get_supported_claim_types(self):
        return ['accident', 'medical', 'theft', 'other']

    def reload_model(self):
        """
        Reload the model after database training
        Useful for singleton pattern when model files are updated
        """
        try:
            logger.info("🔄 Reloading AI model...")
            self._model = None
            self._vectorizer = None
            self._load_model()
            
            if self._model is not None and self._vectorizer is not None:
                logger.info("✅ Model reloaded successfully")
                return True
            else:
                logger.warning("⚠️ Model reload failed, using fallback")
                return False
                
        except Exception as e:
            logger.error(f"❌ Model reload failed: {e}")
            return False

    def get_model_info(self):
        """
        Get information about the currently loaded model
        """
        if self._model is not None and self._vectorizer is not None:
            return {
                'model_path': self._model_path,
                'vectorizer_path': self._vectorizer_path,
                'classes': list(self._model.classes_) if hasattr(self._model, 'classes_') else [],
                'status': 'loaded'
            }
        else:
            return {
                'model_path': None,
                'vectorizer_path': None,
                'classes': [],
                'status': 'fallback'
            }


# ✅ Easy access function
def predict_claim_type(description: str) -> Tuple[str, float]:
    service = AIClaimService()
    return service.predict_claim_type(description)