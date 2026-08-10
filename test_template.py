import os
import django
from django.conf import settings
from django.template import engines

settings.configure(
    TEMPLATES=[{
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [os.path.join(os.getcwd(), 'accounts/templates'), os.path.join(os.getcwd(), 'templates')],
        'APP_DIRS': True,
    }],
    INSTALLED_APPS=[
        'django.contrib.humanize',
    ]
)
django.setup()

def check_file(filepath):
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        content = content.replace('{% load humanize file_filters %}', '{% load humanize %}')
        engines['django'].from_string(content)
        print(f"{filepath} parsed successfully!")
    except Exception as e:
        import traceback
        print(f"Error parsing {filepath}: {type(e).__name__}: {e}")

check_file('accounts/templates/accounts/dashboard_policyholder.html')
check_file('accounts/templates/accounts/dashboard_admin.html')
