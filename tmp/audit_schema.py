import os
import sys
import django
from django.db import connection

# Add the project root to sys.path
sys.path.append(os.getcwd())

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'insurance_claim_system.settings')
django.setup()

from django.apps import apps

def audit_models():
    models_to_check = [
        ('claims', 'ClaimStatusHistory'),
        ('notifications', 'Notification'),
        ('policy', 'UserPolicy'),
        ('policy', 'Payment'),
        ('claims', 'ClaimDocument'),
        ('claims', 'ClaimSettlement'),
        ('premiums', 'PremiumPayment'),
    ]
    
    results = {}
    
    for app_label, model_name in models_to_check:
        try:
            model = apps.get_model(app_label, model_name)
            table_name = model._meta.db_table
            
            # Get columns from database
            with connection.cursor() as cursor:
                cursor.execute(f"DESCRIBE {table_name}")
                columns = [row[0] for row in cursor.fetchall()]
            
            # Get fields from model
            model_fields = [f.name for f in model._meta.get_fields()]
            
            results[f"{app_label}.{model_name}"] = {
                'table': table_name,
                'db_columns': columns,
                'model_fields': model_fields
            }
        except Exception as e:
            results[f"{app_label}.{model_name}"] = {'error': str(e)}
            
    for key, val in results.items():
        print(f"--- {key} ---")
        if 'error' in val:
            print(f"Error: {val['error']}")
        else:
            print(f"Table: {val['table']}")
            print(f"DB columns: {', '.join(val['db_columns'])}")
            print(f"Model fields: {', '.join(val['model_fields'])}")
        print()

if __name__ == "__main__":
    audit_models()
