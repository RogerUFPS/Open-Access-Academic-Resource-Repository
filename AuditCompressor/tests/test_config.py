import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from app.config import CONFIG_PATH, ArchiveSettings, ConfigurationError, DatabaseSettings
from tests.support import ARCHIVE


class ArchiveSettingsTests(unittest.TestCase):
    def test_repository_config_points_to_auditlog(self):
        archive = ArchiveSettings.from_yaml(CONFIG_PATH)
        self.assertEqual(archive.qualified_table, "public.auditlog_logentry")
        self.assertEqual(archive.timestamp_column, "timestamp")
        self.assertEqual(archive.primary_key, "id")

    def test_rejects_identifiers_that_could_alter_sql(self):
        for field in ("schema", "table", "timestamp_column", "primary_key"):
            with self.subTest(field=field), self.assertRaises(ConfigurationError):
                replace(ARCHIVE, **{field: 'id"; DROP TABLE x; --'})

    def test_rejects_unsafe_prefix_and_unknown_compression(self):
        for changes in ({"prefix": "../other"}, {"prefix": "/root"}, {"compression": "zip"}):
            with self.subTest(changes=changes), self.assertRaises(ConfigurationError):
                replace(ARCHIVE, **changes)

    def test_incomplete_yaml_is_reported(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.yaml"
            path.write_text("audit:\n  table: auditlog_logentry\n", encoding="utf-8")
            with self.assertRaises(ConfigurationError):
                ArchiveSettings.from_yaml(path)


class DatabaseSettingsTests(unittest.TestCase):
    def test_missing_settings_are_named_without_values(self):
        database = DatabaseSettings("", 5432, "db", "user", "")
        with self.assertRaises(ConfigurationError) as raised:
            database.ensure_complete()
        self.assertIn("DATABASE_HOST", str(raised.exception))
        self.assertIn("DATABASE_PASSWORD", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
