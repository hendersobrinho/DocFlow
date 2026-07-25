from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from documentos_empresa_app.services.llm_types import redact_cpf
from documentos_empresa_app.utils.backup_encryption import (
    decrypt_backup_file,
    encrypt_backup_file,
    is_encrypted_backup,
)
from documentos_empresa_app.utils.common import ValidationError
from documentos_empresa_app.utils.secret_protection import protect_secret, unprotect_secret


class RedactCpfTests(unittest.TestCase):
    def test_redacts_formatted_cpf(self) -> None:
        text = "Titular CPF 123.456.789-01 residente na Rua Tal."
        self.assertNotIn("123.456.789-01", redact_cpf(text))
        self.assertIn("[CPF removido]", redact_cpf(text))

    def test_redacts_unformatted_cpf(self) -> None:
        text = "CPF: 12345678901 fim."
        self.assertNotIn("12345678901", redact_cpf(text))

    def test_does_not_touch_formatted_cnpj(self) -> None:
        text = "CNPJ 12.345.678/0001-99 emitido para a empresa."
        self.assertIn("12.345.678/0001-99", redact_cpf(text))

    def test_does_not_touch_unformatted_cnpj(self) -> None:
        text = "CNPJ 12345678000199 emitido para a empresa."
        self.assertIn("12345678000199", redact_cpf(text))

    def test_handles_empty_text(self) -> None:
        self.assertEqual(redact_cpf(""), "")
        self.assertEqual(redact_cpf(None), "")


class SecretProtectionTests(unittest.TestCase):
    def test_roundtrip_protects_and_recovers_secret(self) -> None:
        secret = "sk-ant-super-secret-value"
        protected = protect_secret(secret)

        self.assertNotEqual(protected, secret)
        self.assertEqual(unprotect_secret(protected), secret)

    def test_plaintext_legacy_values_pass_through_unchanged(self) -> None:
        self.assertEqual(unprotect_secret("valor-antigo-em-texto-plano"), "valor-antigo-em-texto-plano")

    def test_empty_values_pass_through(self) -> None:
        self.assertIsNone(protect_secret(None))
        self.assertEqual(protect_secret(""), "")
        self.assertIsNone(unprotect_secret(None))
        self.assertEqual(unprotect_secret(""), "")


class BackupEncryptionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_encrypt_then_decrypt_roundtrip(self) -> None:
        backup_file = Path(self.temp_dir.name) / "backup.db"
        original_content = b"conteudo simulado de um backup sqlite"
        backup_file.write_bytes(original_content)

        encrypt_backup_file(backup_file, "senhaForte123")
        self.assertTrue(is_encrypted_backup(backup_file))
        self.assertNotEqual(backup_file.read_bytes(), original_content)

        destination = Path(self.temp_dir.name) / "restored.db"
        decrypt_backup_file(backup_file, destination, "senhaForte123")
        self.assertEqual(destination.read_bytes(), original_content)

    def test_decrypt_with_wrong_password_raises(self) -> None:
        backup_file = Path(self.temp_dir.name) / "backup.db"
        backup_file.write_bytes(b"conteudo")
        encrypt_backup_file(backup_file, "senhaCerta")

        destination = Path(self.temp_dir.name) / "restored.db"
        with self.assertRaises(ValidationError):
            decrypt_backup_file(backup_file, destination, "senhaErrada")

    def test_plain_backup_is_not_flagged_as_encrypted(self) -> None:
        backup_file = Path(self.temp_dir.name) / "backup.db"
        backup_file.write_bytes(b"SQLite format 3\x00conteudo qualquer")
        self.assertFalse(is_encrypted_backup(backup_file))


if __name__ == "__main__":
    unittest.main()
