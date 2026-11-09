from django.db import migrations


TRIGGER_NAME = "harvestjournal_quantity_guard"
FUNCTION_NAME = "harvestjournal_quantity_guard_fn"
CONSTRAINT_NAME = "harvest_journal_quantity_limit"


def install_guard(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return

    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            f"""
            CREATE OR REPLACE FUNCTION {FUNCTION_NAME}()
            RETURNS trigger
            LANGUAGE plpgsql
            AS $$
            DECLARE
                quantity_limit integer;
                existing_count bigint;
            BEGIN
                IF TG_OP = 'UPDATE' THEN
                    IF NEW.harvest_id = OLD.harvest_id THEN
                        RETURN NEW;
                    END IF;
                END IF;

                SELECT max_quantity
                INTO quantity_limit
                FROM harvesting_harvest
                WHERE id = NEW.harvest_id
                FOR UPDATE;

                IF quantity_limit IS NOT NULL THEN
                    SELECT COUNT(*)
                    INTO existing_count
                    FROM harvesting_harvestjournal
                    WHERE harvest_id = NEW.harvest_id;

                    IF existing_count >= quantity_limit THEN
                        RAISE EXCEPTION 'Harvest journal quantity limit reached'
                            USING ERRCODE = '23514',
                                  CONSTRAINT = '{CONSTRAINT_NAME}';
                    END IF;
                END IF;

                RETURN NEW;
            END;
            $$;
            """
        )
        cursor.execute(
            f"""
            CREATE TRIGGER {TRIGGER_NAME}
            BEFORE INSERT OR UPDATE OF harvest_id ON harvesting_harvestjournal
            FOR EACH ROW
            EXECUTE FUNCTION {FUNCTION_NAME}();
            """
        )


def remove_guard(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return

    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            f"DROP TRIGGER IF EXISTS {TRIGGER_NAME} "
            "ON harvesting_harvestjournal;"
        )
        cursor.execute(f"DROP FUNCTION IF EXISTS {FUNCTION_NAME}();")


class Migration(migrations.Migration):

    dependencies = [
        ("harvesting", "0007_harvest_worker_checkpoints"),
    ]

    operations = [
        migrations.RunPython(install_guard, reverse_code=remove_guard),
    ]
