from premiums.models import PremiumSchedule, PremiumPayment

def cleanup_duplicates():
    print("--- 🧹 CLEANUP START ---")
    
    # Target: POL-MNNAM5 with ID 1 (Legacy/Duplicate)
    try:
        legacy_schedule = PremiumSchedule.objects.get(id=1)
        if legacy_schedule.user_policy is None:
            payment_count = PremiumPayment.objects.filter(schedule=legacy_schedule).count()
            print(f"ID 1 found. Linked Payments: {payment_count}. Deleting legacy schedule...")
            
            # Delete linked payments first if any? (on_delete=CASCADE in model)
            legacy_schedule.delete()
            print("Successfully deleted legacy schedule ID 1.")
        else:
            print("ID 1 is linked to a UserPolicy! Skipping deletion to be safe.")
    except PremiumSchedule.DoesNotExist:
        print("ID 1 not found or already deleted.")

    print("\n--- ✅ CLEANUP FINISHED ---")

if __name__ == "__main__":
    import os
    import django
    import sys
    sys.path.append(r'd:\insurance_claim_system_NEW')
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'insurance_claim_system.settings')
    django.setup()
    cleanup_duplicates()
