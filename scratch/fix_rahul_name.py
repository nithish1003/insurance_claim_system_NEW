import os
import sys
import django

# Setup Django settings
sys.path.append(os.getcwd())
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'insurance_claim_system.settings')
django.setup()

from accounts.models import User, UserProfile

def main():
    username = "Rahul_Sharma"
    try:
        user = User.objects.get(username=username)
        profile = user.profile
        old_name = profile.full_name
        profile.full_name = "rahul sharma"
        profile.save()
        print(f"Successfully updated profile name for {username} from '{old_name}' to '{profile.full_name}'")
    except User.DoesNotExist:
        print(f"User {username} not found.")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == '__main__':
    main()
