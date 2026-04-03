from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from documentos_empresa_app.utils.common import ValidationError
from documentos_empresa_app.utils.storage import (
    build_database_path,
    create_database_directory,
    is_path_within_directory,
    normalize_database_filename,
)


class StorageHelperTests(unittest.TestCase):
    def test_normalize_database_filename_appends_extension(self) -> None:
        self.assertEqual(normalize_database_filename("meu_banco", "g_docs.db"), "meu_banco.db")

    def test_normalize_database_filename_uses_default_when_empty(self) -> None:
        self.assertEqual(normalize_database_filename("", "g_docs.db"), "g_docs.db")

    def test_build_database_path_combines_folder_and_filename(self) -> None:
        path = build_database_path("/tmp/teste", "base", "g_docs.db")
        self.assertEqual(path, Path("/tmp/teste/base.db"))

    def test_normalize_database_filename_rejects_embedded_path(self) -> None:
        with self.assertRaises(ValidationError):
            normalize_database_filename("../fora.db", "g_docs.db")

    def test_create_database_directory_creates_relative_folder_inside_base(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            created = create_database_directory(temp_dir, "dados/gdocs")
            self.assertTrue(created.exists())
            self.assertTrue(created.is_dir())

    def test_create_database_directory_rejects_absolute_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaises(ValidationError):
                create_database_directory(temp_dir, "/tmp/invalido")

    def test_is_path_within_directory_detects_nested_path(self) -> None:
        self.assertTrue(is_path_within_directory("/tmp/app/dados/base.db", "/tmp/app"))
        self.assertFalse(is_path_within_directory("/tmp/dados/base.db", "/tmp/app"))


if __name__ == "__main__":
    unittest.main()
