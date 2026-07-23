from __future__ import annotations

import argparse
import hmac
import json
import sys
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from documentos_empresa_app.services.license_service import LicenseError, resolve_license_secret

OUTPUT_FILE = ROOT_DIR / "dist_license" / "license.json"
DEFAULT_NOTES = "Licenca vitalicia para uso interno/piloto."


def build_signature(payload: dict, secret_key: str) -> str:
    payload_bytes = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hmac.new(secret_key.encode("utf-8"), payload_bytes, sha256).hexdigest()


def build_payload(customer: str, email: str, notes: str) -> dict:
    issued_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return {
        "customer": customer,
        "email": email,
        "plan": "lifetime-internal",
        "license_type": "lifetime",
        "issued_at": issued_at,
        "expires_at": None,
        "max_machines": None,
        "notes": notes,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Gera license.json vitalicia para uso interno/piloto (HMAC-SHA256)."
    )
    parser.add_argument("--customer", required=True, help="Nome do cliente/empresa.")
    parser.add_argument("--email", required=True, help="Email principal.")
    parser.add_argument("--notes", default=DEFAULT_NOTES, help="Observacoes da licenca.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    customer = str(args.customer).strip()
    email = str(args.email).strip()
    notes = str(args.notes).strip()

    if not customer:
        raise SystemExit("Erro: informe --customer.")
    if not email:
        raise SystemExit("Erro: informe --email.")
    try:
        secret = resolve_license_secret().decode("utf-8")
    except LicenseError as exc:
        raise SystemExit(f"Erro: {exc}") from exc

    payload = build_payload(customer=customer, email=email, notes=notes)
    license_data = {
        "payload": payload,
        "signature": build_signature(payload, secret),
    }

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(
        json.dumps(license_data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Licenca gerada com sucesso em: {OUTPUT_FILE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
