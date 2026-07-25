from __future__ import annotations

import os
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from documentos_empresa_app.utils.common import ValidationError

MAGIC_HEADER = b"DOCFLOWBK1"
SALT_SIZE = 16
PBKDF2_ITERATIONS = 390_000


def _derive_key(password: str, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=PBKDF2_ITERATIONS)
    import base64

    return base64.urlsafe_b64encode(kdf.derive(password.encode("utf-8")))


def is_encrypted_backup(file_path: Path) -> bool:
    try:
        with open(file_path, "rb") as handle:
            return handle.read(len(MAGIC_HEADER)) == MAGIC_HEADER
    except OSError:
        return False


def encrypt_backup_file(file_path: Path, password: str) -> None:
    """Criptografa o backup no lugar: le o .db gerado em texto claro e
    sobrescreve com a versao criptografada (cabecalho + salt + conteudo cifrado
    com Fernet/AES, chave derivada da senha via PBKDF2)."""
    salt = os.urandom(SALT_SIZE)
    key = _derive_key(password, salt)
    ciphertext = Fernet(key).encrypt(file_path.read_bytes())
    file_path.write_bytes(MAGIC_HEADER + salt + ciphertext)


def decrypt_backup_file(source_path: Path, destination_path: Path, password: str) -> None:
    """Descriptografa um backup criptografado para destination_path. Levanta
    ValidationError se a senha estiver errada ou o arquivo nao for um backup
    criptografado valido do DocFlow."""
    raw = source_path.read_bytes()
    if not raw.startswith(MAGIC_HEADER):
        raise ValidationError("O arquivo selecionado nao e um backup criptografado do DocFlow.")

    payload = raw[len(MAGIC_HEADER):]
    salt, ciphertext = payload[:SALT_SIZE], payload[SALT_SIZE:]
    key = _derive_key(password, salt)
    try:
        plaintext = Fernet(key).decrypt(ciphertext)
    except InvalidToken as exc:
        raise ValidationError("Senha incorreta para este backup criptografado.") from exc
    destination_path.write_bytes(plaintext)
