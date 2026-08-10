import uuid
from django.db import migrations, models

def migrate_pending_to_manual_review(apps, schema_editor):
    AadhaarKYCVerification = apps.get_model('accounts', 'AadhaarKYCVerification')
    # Convert 'pending' to 'manual_review'
    AadhaarKYCVerification.objects.filter(status='pending').update(status='manual_review')
    # Convert 'failed' to 'rejected'
    AadhaarKYCVerification.objects.filter(status='failed').update(status='rejected')

def reverse_migration(apps, schema_editor):
    AadhaarKYCVerification = apps.get_model('accounts', 'AadhaarKYCVerification')
    AadhaarKYCVerification.objects.filter(status='manual_review').update(status='pending')
    AadhaarKYCVerification.objects.filter(status='rejected').update(status='failed')

class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0010_add_public_ids_and_kyc'),
    ]

    operations = [
        migrations.AlterField(
            model_name='aadhaarkycverification',
            name='status',
            field=models.CharField(choices=[('verified', 'Verified'), ('manual_review', 'Manual Review'), ('rejected', 'Rejected'), ('approved_override', 'Approved by Admin'), ('rejected_override', 'Rejected by Admin')], default='manual_review', max_length=20),
        ),
        migrations.RunPython(migrate_pending_to_manual_review, reverse_migration),
    ]
