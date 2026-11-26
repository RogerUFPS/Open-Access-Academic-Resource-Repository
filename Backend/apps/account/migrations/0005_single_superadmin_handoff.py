from django.db import migrations, models
from django.db.models import Q


def require_single_active_superadmin(apps, schema_editor):
    User = apps.get_model("account", "User")
    count = User.objects.filter(is_superadmin=True, is_active=True).count()
    if count > 1:
        raise RuntimeError(
            "Cannot enforce the single-superadmin invariant: multiple active "
            "superadmins already exist. Resolve them explicitly before migrating."
        )


class Migration(migrations.Migration):
    dependencies = [("account", "0004_superadmin_security")]

    operations = [
        migrations.AddField(
            model_name="user",
            name="pending_superadmin",
            field=models.BooleanField(default=False),
        ),
        migrations.RunPython(require_single_active_superadmin, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="user",
            constraint=models.UniqueConstraint(
                fields=("is_superadmin",),
                condition=Q(is_superadmin=True, is_active=True),
                name="account_single_active_superadmin",
            ),
        ),
        migrations.AddConstraint(
            model_name="user",
            constraint=models.UniqueConstraint(
                fields=("pending_superadmin",),
                condition=Q(pending_superadmin=True, is_active=True),
                name="account_single_pending_superadmin",
            ),
        ),
        migrations.AddConstraint(
            model_name="user",
            constraint=models.CheckConstraint(
                condition=~Q(is_superadmin=True, pending_superadmin=True),
                name="account_pending_not_superadmin",
            ),
        ),
        migrations.AddConstraint(
            model_name="user",
            constraint=models.CheckConstraint(
                condition=Q(pending_superadmin=False) | Q(is_active=True),
                name="account_pending_superadmin_active",
            ),
        ),
    ]
