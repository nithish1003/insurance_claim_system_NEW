from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
from django.utils import timezone


def migrate_policyholder_to_userprofile_and_purchases(apps, schema_editor):
    PolicyHolder = apps.get_model("policy", "PolicyHolder")
    UserProfile = apps.get_model("policy", "UserProfile")
    Policy = apps.get_model("policy", "Policy")

    for holder in PolicyHolder.objects.all():
        if not holder.user_id:
            continue
        UserProfile.objects.update_or_create(
            user_id=holder.user_id,
            defaults={
                "phone": holder.phone,
                "address": holder.address,
                "city": holder.city,
                "state": holder.state,
                "created_at": holder.created_at,
            },
        )

    for policy in Policy.objects.exclude(holder__isnull=True):
        PolicyHolder.objects.get_or_create(
            user_id=policy.holder.user_id,
            policy_id=policy.id,
            defaults={"purchased_at": policy.created_at},
        )

    PolicyHolder.objects.filter(policy__isnull=True).delete()
    PolicyHolder.objects.filter(purchased_at__isnull=True).update(purchased_at=timezone.now())


class Migration(migrations.Migration):

    dependencies = [
        ("policy", "0010_alter_policy_holder"),
    ]

    operations = [
        migrations.CreateModel(
            name="UserProfile",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("phone", models.CharField(blank=True, default="", max_length=15)),
                ("address", models.TextField(blank=True, default="")),
                ("city", models.CharField(blank=True, default="", max_length=100)),
                ("state", models.CharField(blank=True, default="", max_length=100)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("user", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "db_table": "policy_userprofile",
                "verbose_name_plural": "User Profiles",
            },
        ),
        migrations.AlterField(
            model_name="policyholder",
            name="user",
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="policy_purchases", to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name="policyholder",
            name="policy",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="purchases", to="policy.policy"),
        ),
        migrations.AddField(
            model_name="policyholder",
            name="purchased_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.RunPython(migrate_policyholder_to_userprofile_and_purchases, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="policyholder",
            name="phone",
        ),
        migrations.RemoveField(
            model_name="policyholder",
            name="address",
        ),
        migrations.RemoveField(
            model_name="policyholder",
            name="city",
        ),
        migrations.RemoveField(
            model_name="policyholder",
            name="state",
        ),
        migrations.RemoveField(
            model_name="policyholder",
            name="created_at",
        ),
        migrations.AlterField(
            model_name="policyholder",
            name="policy",
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="purchases", to="policy.policy"),
        ),
        migrations.AlterField(
            model_name="policyholder",
            name="purchased_at",
            field=models.DateTimeField(auto_now_add=True),
        ),
        migrations.RemoveField(
            model_name="policy",
            name="holder",
        ),
        migrations.AddConstraint(
            model_name="policyholder",
            constraint=models.UniqueConstraint(fields=("user", "policy"), name="unique_user_policy_purchase"),
        ),
    ]
