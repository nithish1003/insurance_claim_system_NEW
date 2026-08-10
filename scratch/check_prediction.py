import os
import sys
import django

# Setup Django settings
sys.path.append(os.getcwd())
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'insurance_claim_system.settings')
django.setup()

from ai_features.services.ai_claim_service import AIClaimService

def main():
    desc = "Vehicle was involved in a minor road accident causing damage to the front bumper and left headlight. Requesting claim inspection and repair approval."
    service = AIClaimService()
    print("Model Loaded Info:", service.get_model_info())
    
    # 1. Prediction using predict_claim_type
    pred, conf = service.predict_claim_type(desc)
    print(f"Prediction: {pred}, Confidence: {conf}")
    
    # Let's inspect the model details if loaded
    if service._model is not None:
        cleaned_text = service.clean_text(desc)
        print(f"Cleaned Text: '{cleaned_text}'")
        vec = service._vectorizer.transform([cleaned_text])
        prediction = service._model.predict(vec)[0]
        probabilities = service._model.predict_proba(vec)[0]
        classes = service._model.classes_
        
        print("\nProbabilities per class:")
        for cls, prob in zip(classes, probabilities):
            print(f"  {cls}: {prob:.4f}")

if __name__ == '__main__':
    main()
