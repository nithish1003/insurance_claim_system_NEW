import os
import django
from django.urls import get_resolver

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'insurance_claim_system.settings')
django.setup()

def print_namespaces(resolver, depth=0):
    for pattern in resolver.url_patterns:
        if hasattr(pattern, 'namespace'):
            print("  " * depth + f"Namespace: {pattern.namespace} (app_name: {getattr(pattern, 'app_name', 'N/A')}) at {pattern.pattern}")
        if hasattr(pattern, 'url_patterns'):
            print_namespaces(pattern, depth + 1)

print("Listing all registered namespaces:")
resolver = get_resolver()
print_namespaces(resolver)
