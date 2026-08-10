import os
import sys
import django

# Setup Django settings
sys.path.append(os.getcwd())
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'insurance_claim_system.settings')
django.setup()

from ai_features.services.ocr_service import verify_identity

def main():
    image_path = "media/id_proofs/rahul_sharma.png"
    if not os.path.exists(image_path):
        print(f"File not found: {image_path}")
        return
        
    print("Running verify_identity on rahul_sharma.png...")
    results = verify_identity(image_path, "RAHUL SHARMA", "123456789012")
    
    print("\n--- RESULTS ---")
    import pprint
    pprint.pprint(results)
    print("---------------\n")

if __name__ == '__main__':
    main()
