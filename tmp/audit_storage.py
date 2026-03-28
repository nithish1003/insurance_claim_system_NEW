import os
import sys
import django
from django.db import models

# Add the project root to sys.path
sys.path.append(os.getcwd())

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'insurance_claim_system.settings')
django.setup()

from django.apps import apps

def audit_storage():
    all_models = apps.get_models()
    
    docs_found = []
    extracted_data_found = []
    
    sensitive_keywords = [
        'aadhaar', 'patient', 'hospital', 'bill', 'diagnosis', 
        'vehicle', 'owner', 'registration', 'garage', 'repair', 'cost', 'amount'
    ]
    
    for model in all_models:
        app_label = model._meta.app_label
        model_name = model.__name__
        
        # Check for File/Image fields
        for field in model._meta.fields:
            if isinstance(field, (models.FileField, models.ImageField)):
                docs_found.append({
                    'model': f"{app_label}.{model_name}",
                    'field': field.name,
                    'path': field.upload_to if hasattr(field, 'upload_to') else 'N/A'
                })
            
            # Check for extracted data keywords
            field_name_lower = field.name.lower()
            if any(keyword in field_name_lower for keyword in sensitive_keywords):
                # Exclude common non-sensitive fields
                if field_name_lower not in ['id', 'created_at', 'updated_at', 'amount_paid']:
                    extracted_data_found.append({
                        'model': f"{app_label}.{model_name}",
                        'field': field.name,
                        'type': type(field).__name__
                    })
                    
    print("--- DOCUMENT STORAGE ---")
    for doc in docs_found:
        print(f"Model: {doc['model']}")
        print(f"FileField: {doc['field']}")
        print(f"Path: {doc['path']}")
        print()
        
    print("--- EXTRACTED / SENSITIVE DATA ---")
    for data in extracted_data_found:
        print(f"Model: {data['model']}")
        print(f"Field: {data['field']}")
        print(f"Type: {data['type']}")
        print()

if __name__ == "__main__":
    audit_storage()
