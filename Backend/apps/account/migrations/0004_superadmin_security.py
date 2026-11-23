from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


def install_append_only_trigger(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute("""
        CREATE FUNCTION account_reject_superadmin_audit_mutation()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'superadmin audit events are append-only';
        END;
        $$;
    """)
    schema_editor.execute("""
        CREATE TRIGGER account_superadmin_audit_no_update_delete
        BEFORE UPDATE OR DELETE ON account_superadminauditevent
        FOR EACH ROW EXECUTE FUNCTION account_reject_superadmin_audit_mutation();
    """)
    schema_editor.execute("""
        CREATE TRIGGER account_superadmin_audit_no_truncate
        BEFORE TRUNCATE ON account_superadminauditevent
        FOR EACH STATEMENT EXECUTE FUNCTION account_reject_superadmin_audit_mutation();
    """)


def remove_append_only_trigger(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute("""
        DROP TRIGGER IF EXISTS account_superadmin_audit_no_update_delete
        ON account_superadminauditevent;
    """)
    schema_editor.execute("""
        DROP TRIGGER IF EXISTS account_superadmin_audit_no_truncate
        ON account_superadminauditevent;
    """)
    schema_editor.execute("""
        DROP FUNCTION IF EXISTS account_reject_superadmin_audit_mutation();
    """)


class Migration(migrations.Migration):
    dependencies = [
        ("account", "0003_account_access_and_sessions"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="mfa_secret",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="user",
            name="mfa_enabled",
            field=models.BooleanField(default=False),
        ),
        migrations.CreateModel(
            name="SuperadminAuditEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("actor_email", models.EmailField(blank=True, max_length=254)),
                ("action", models.CharField(max_length=64)),
                ("target_email", models.EmailField(blank=True, max_length=254)),
                ("details", models.JSONField(blank=True, default=dict)),
                ("timestamp", models.DateTimeField(db_index=True, default=django.utils.timezone.now)),
                ("actor", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="superadmin_events_as_actor", to=settings.AUTH_USER_MODEL)),
                ("target", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="superadmin_events_as_target", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-timestamp", "-pk"]},
        ),
        migrations.CreateModel(
            name="SuperadminBootstrapState",
            fields=[
                ("id", models.PositiveSmallIntegerField(default=1, editable=False, primary_key=True, serialize=False)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
            ],
        ),
        migrations.RunPython(install_append_only_trigger, remove_append_only_trigger),
    ]
