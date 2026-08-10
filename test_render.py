import os
import django
from django.conf import settings

settings.configure(
    TEMPLATES=[{
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [os.path.join(os.getcwd(), 'accounts/templates'), os.path.join(os.getcwd(), 'templates')],
        'APP_DIRS': True,
    }],
    INSTALLED_APPS=[
        'django.contrib.humanize',
        'accounts',
        'claims',
        'policy',
    ],
    DATABASES={'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': 'db.sqlite3'}},
)
django.setup()

from django.template.loader import render_to_string
from accounts.models import User
from policy.models import Policy

try:
    all_policies = Policy.objects.all()
    context = {'all_policies': all_policies}
    render_to_string('accounts/dashboard_staff.html', context)
    print("Rendered successfully!")
except Exception as e:
    import traceback
    traceback.print_exc()
