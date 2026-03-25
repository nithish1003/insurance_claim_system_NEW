from django.db import connection

def check_columns():
    with connection.cursor() as cursor:
        cursor.execute("PRAGMA table_info(claims_claim)")
        cols = cursor.fetchall()
        for col in cols:
            print(f"Col: {col[1]} - Type: {col[2]}")

if __name__ == "__main__":
    import django
    import os
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'insurance_claim_system.settings')
    django.setup()
    check_columns()
