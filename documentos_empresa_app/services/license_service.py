from __future__ import annotations

import hmac
import json
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any

from documentos_empresa_app.utils.common import CONFIG_DIR

try:
    from documentos_empresa_app._private.license_secret import LICENSE_SECRET as PRIVATE_LICENSE_SECRET
except ImportError:
    PRIVATE_LICENSE_SECRET = None


PUBLIC_PORTFOLIO_LICENSE_MESSAGE = (
    "A edicao publica do DocFLow nao inclui a chave privada de licenciamento. "
    "Este repositorio foi publicado apenas para portfolio e estudo."
)


class LicenseError(Exception):
    """Erro de validacao de licenca."""


def resolve_license_secret(secret_key: str | bytes | None = None) -> bytes:
    resolved_secret = secret_key if secret_key is not None else PRIVATE_LICENSE_SECRET
    secret_value = resolved_secret.encode("utf-8") if isinstance(resolved_secret, str) else resolved_secret
    if not secret_value:
        raise LicenseError(PUBLIC_PORTFOLIO_LICENSE_MESSAGE)
    return secret_value


class LicenseService:
    def __init__(self, secret_key: str | bytes | None = None, config_dir: Path = CONFIG_DIR) -> None:
        self._secret_key = resolve_license_secret(secret_key)
        self._config_dir = Path(config_dir).expanduser()
        self._license_file = self._config_dir / "license.json"

    @property
    def license_file_path(self) -> Path:
        return self._license_file

    def load(self) -> dict[str, Any]:
        if not self._license_file.exists():
            raise LicenseError(f"Arquivo de licenca nao encontrado: {self._license_file}")

        try:
            raw_data = json.loads(self._license_file.read_text(encoding="utf-8"))
        except OSError as exc:
            raise LicenseError("Nao foi possivel ler o arquivo de licenca.") from exc
        except json.JSONDecodeError as exc:
            raise LicenseError("O arquivo de licenca esta corrompido ou invalido.") from exc

        return self.validate(raw_data)

    def validate(self, raw_license: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(raw_license, dict):
            raise LicenseError("Formato de licenca invalido: esperado objeto JSON.")

        payload = raw_license.get("payload")
        signature = raw_license.get("signature")

        if not isinstance(payload, dict):
            raise LicenseError("Licenca invalida: campo 'payload' ausente ou invalido.")
        if not isinstance(signature, str) or not signature.strip():
            raise LicenseError("Licenca invalida: campo 'signature' ausente ou invalido.")

        expected_signature = self._build_signature(payload)
        informed_signature = signature.strip().lower()
        if not hmac.compare_digest(informed_signature, expected_signature):
            raise LicenseError("Assinatura da licenca invalida.")

        self._validate_expiration(payload)
        return {"payload": payload, "signature": informed_signature}

    def save(self, raw_license: dict[str, Any]) -> dict[str, Any]:
        validated_license = self.validate(raw_license)
        self._config_dir.mkdir(parents=True, exist_ok=True)
        try:
            self._license_file.write_text(
                json.dumps(validated_license, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError as exc:
            raise LicenseError("Nao foi possivel salvar o arquivo de licenca.") from exc
        return validated_license

    def load_and_save_if_valid(self) -> dict[str, Any]:
        return self.save(self.load())

    def _build_signature(self, payload: dict[str, Any]) -> str:
        payload_bytes = json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        return hmac.new(self._secret_key, payload_bytes, sha256).hexdigest()

    def _validate_expiration(self, payload: dict[str, Any]) -> None:
        if "expires_at" not in payload:
            return

        expires_at = payload["expires_at"]
        if expires_at is None:
            return

        if not isinstance(expires_at, str) or not expires_at.strip():
            raise LicenseError("Licenca invalida: campo 'expires_at' deve ser string ISO-8601 ou null.")

        expires_at_dt = self._parse_datetime(expires_at)
        now_utc = datetime.now(timezone.utc)
        if expires_at_dt < now_utc:
            raise LicenseError(f"Licenca expirada em {expires_at_dt.isoformat()}.")

    def _parse_datetime(self, raw_value: str) -> datetime:
        normalized_value = raw_value.strip().replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(normalized_value)
        except ValueError as exc:
            raise LicenseError("Licenca invalida: campo 'expires_at' fora do formato ISO-8601.") from exc

        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
