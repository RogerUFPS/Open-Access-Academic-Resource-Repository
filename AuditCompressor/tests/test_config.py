import base64
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from app.config import (
    CONFIG_PATH,
    ConfigurationError,
    DatabaseSettings,
    Settings,
    StorageSettings,
    UnknownSourceError,
    load_sources,
    load_timezone,
    parquet_encryption_key,
)
from tests.support import SOURCE, TEST_KEY


class SourceSettingsTests(unittest.TestCase):
    def test_repository_config_declares_both_audit_tables(self):
        sources = load_sources(CONFIG_PATH)
        self.assertEqual(set(sources), {"auditlog", "superadmin_events"})

        auditlog = sources["auditlog"]
        self.assertEqual(auditlog.qualified_table, "public.auditlog_logentry")
        self.assertEqual((auditlog.timestamp_column, auditlog.primary_key), ("timestamp", "id"))
        self.assertEqual(auditlog.json_columns, ("changes", "serialized_data", "additional_data"))

        events = sources["superadmin_events"]
        self.assertEqual(events.qualified_table, "public.account_superadminauditevent")
        self.assertEqual((events.timestamp_column, events.primary_key), ("timestamp", "id"))
        self.assertEqual(events.json_columns, ("details",))

    def test_superadmin_events_are_archived_without_offload(self):
        sources = load_sources(CONFIG_PATH)
        self.assertTrue(sources["auditlog"].offload)
        self.assertFalse(sources["superadmin_events"].offload)

    def test_offload_flag_must_be_boolean(self):
        with self.assertRaises(ConfigurationError):
            replace(SOURCE, offload="no")

    def test_source_name_is_its_storage_prefix(self):
        self.assertEqual(SOURCE.prefix, "auditlog")

    def test_rejects_identifiers_that_could_alter_sql(self):
        injected = 'id"; DROP TABLE x; --'
        for field in ("schema", "table", "timestamp_column", "primary_key"):
            with self.subTest(field=field), self.assertRaises(ConfigurationError):
                replace(SOURCE, **{field: injected})
        with self.assertRaises(ConfigurationError):
            replace(SOURCE, json_columns=("changes", injected))

    def test_rejects_unsafe_source_names_and_unknown_compression(self):
        for changes in (
            {"name": "../other"},
            {"name": "Auditlog"},
            {"name": "audit/log"},
            {"compression": "zip"},
        ):
            with self.subTest(changes=changes), self.assertRaises(ConfigurationError):
                replace(SOURCE, **changes)

    def test_incomplete_or_empty_yaml_is_reported(self):
        contents = (
            "sources:\n  auditlog:\n    table: auditlog_logentry\nparquet:\n  compression: zstd\n",
            "sources: {}\nparquet:\n  compression: zstd\n",
            "parquet:\n  compression: zstd\n",
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.yaml"
            for content in contents:
                with self.subTest(content=content), self.assertRaises(ConfigurationError):
                    path.write_text(content, encoding="utf-8")
                    load_sources(path)


class TimezoneTests(unittest.TestCase):
    def test_repository_config_uses_colombia(self):
        self.assertEqual(str(load_timezone(CONFIG_PATH)), "America/Bogota")

    def test_unknown_time_zone_is_reported(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.yaml"
            path.write_text("timezone: Marte/Olympus\n", encoding="utf-8")
            with self.assertRaises(ConfigurationError):
                load_timezone(path)


class SettingsSourceTests(unittest.TestCase):
    def test_unknown_source_is_reported(self):
        settings = Settings(
            api_key="",
            database=DatabaseSettings("postgres", 5432, "db", "user", "secret"),
            storage=StorageSettings("http://rustfs:9000", "auditorias", "us-east-1", "a", "b"),
            sources={"auditlog": SOURCE},
        )
        self.assertIs(settings.source("auditlog"), SOURCE)
        with self.assertRaises(UnknownSourceError):
            settings.source("users")


class EncryptionKeyTests(unittest.TestCase):
    def test_accepts_32_bytes_in_base64(self):
        self.assertEqual(parquet_encryption_key(TEST_KEY), TEST_KEY)

    def test_rejects_missing_malformed_or_short_keys(self):
        short = base64.b64encode(bytes(16)).decode()
        for value in ("", "not base64!", short):
            with self.subTest(value=value), self.assertRaises(ConfigurationError) as raised:
                parquet_encryption_key(value)
            if value:
                self.assertNotIn(value, str(raised.exception))


class DatabaseSettingsTests(unittest.TestCase):
    def test_missing_settings_are_named_without_values(self):
        database = DatabaseSettings("", 5432, "db", "user", "")
        with self.assertRaises(ConfigurationError) as raised:
            database.ensure_complete()
        self.assertIn("DATABASE_HOST", str(raised.exception))
        self.assertIn("DATABASE_PASSWORD", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
