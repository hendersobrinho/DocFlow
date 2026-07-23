from __future__ import annotations

from datetime import datetime
from pathlib import Path
import tempfile
import unittest

from documentos_empresa_app.utils.auto_backup import normalize_auto_backup_settings, should_run_auto_backup
from documentos_empresa_app.utils.common import ValidationError
from documentos_empresa_app.utils.storage import (
    build_database_path,
    create_database_directory,
    is_path_within_directory,
    normalize_database_filename,
)


class StorageHelperTests(unittest.TestCase):
    def test_normalize_database_filename_appends_extension(self) -> None:
        self.assertEqual(normalize_database_filename("meu_banco", "docflow.db"), "meu_banco.db")

    def test_normalize_database_filename_uses_default_when_empty(self) -> None:
        self.assertEqual(normalize_database_filename("", "docflow.db"), "docflow.db")

    def test_build_database_path_combines_folder_and_filename(self) -> None:
        path = build_database_path("/tmp/teste", "base", "docflow.db")
        self.assertEqual(path, Path("/tmp/teste/base.db"))

    def test_normalize_database_filename_rejects_embedded_path(self) -> None:
        with self.assertRaises(ValidationError):
            normalize_database_filename("../fora.db", "docflow.db")

    def test_create_database_directory_creates_relative_folder_inside_base(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            created = create_database_directory(temp_dir, "dados/gdocs")
            self.assertTrue(created.exists())
            self.assertTrue(created.is_dir())

    def test_create_database_directory_rejects_absolute_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaises(ValidationError):
                create_database_directory(temp_dir, "/tmp/invalido")

    def test_create_database_directory_rejects_parent_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaises(ValidationError):
                create_database_directory(temp_dir, "../fora")

    def test_is_path_within_directory_detects_nested_path(self) -> None:
        self.assertTrue(is_path_within_directory("/tmp/app/dados/base.db", "/tmp/app"))
        self.assertFalse(is_path_within_directory("/tmp/dados/base.db", "/tmp/app"))

    def test_normalize_auto_backup_settings_uses_safe_defaults(self) -> None:
        settings = normalize_auto_backup_settings(None, default_directory="/tmp/docflow-backups")

        self.assertFalse(settings["enabled"])
        self.assertEqual(settings["directory"], "/tmp/docflow-backups")
        self.assertEqual(settings["interval_days"], 1)
        self.assertEqual(settings["keep_last"], 10)
        self.assertIsNone(settings["last_backup_at"])

    def test_auto_backup_runs_when_enabled_without_previous_backup(self) -> None:
        settings = normalize_auto_backup_settings(
            {
                "enabled": True,
                "directory": "/tmp/docflow-backups",
            }
        )

        self.assertTrue(should_run_auto_backup(settings, now=datetime(2026, 5, 6, 8, 0, 0)))

    def test_auto_backup_respects_interval(self) -> None:
        settings = normalize_auto_backup_settings(
            {
                "enabled": True,
                "directory": "/tmp/docflow-backups",
                "interval_days": 7,
                "last_backup_at": "2026-05-01T08:00:00",
            }
        )

        self.assertFalse(should_run_auto_backup(settings, now=datetime(2026, 5, 7, 8, 0, 0)))
        self.assertTrue(should_run_auto_backup(settings, now=datetime(2026, 5, 8, 8, 0, 0)))


if __name__ == "__main__":
    unittest.main()
