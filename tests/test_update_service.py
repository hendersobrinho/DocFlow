from __future__ import annotations

import hashlib
import io
from pathlib import Path
import tempfile
import unittest

from documentos_empresa_app.services.update_service import (
    LATEST_RELEASE_URL,
    SILENT_INSTALL_ARGS,
    UpdateService,
    is_newer,
    parse_version,
)
from documentos_empresa_app.utils.common import ValidationError

INSTALADOR = b"MZ" + b"instalador de mentira" * 1000


class _Resposta(io.BytesIO):
    def __init__(self, conteudo: bytes) -> None:
        super().__init__(conteudo)
        self.headers = {"Content-Length": str(len(conteudo))}


def _release(versao: str = "v1.2.0", com_sha: bool = True, **extra) -> dict:
    assets = [{
        "name": f"DocFLow-Setup-{versao.lstrip('v')}.exe",
        "browser_download_url": "https://github.com/x/setup.exe",
        "size": len(INSTALADOR),
    }]
    if com_sha:
        assets.append({
            "name": f"DocFLow-Setup-{versao.lstrip('v')}.exe.sha256",
            "browser_download_url": "https://github.com/x/setup.exe.sha256",
        })
    return {"tag_name": versao, "body": "- Coisa nova", "html_url": "https://github.com/x/releases/v", "assets": assets, **extra}


class UpdateServiceTests(unittest.TestCase):
    def _service(self, release: dict, sha: str | None = None, versao_local: str = "1.1.0") -> UpdateService:
        arquivos = {
            "https://github.com/x/setup.exe": INSTALADOR,
            "https://github.com/x/setup.exe.sha256": f"{sha or hashlib.sha256(INSTALADOR).hexdigest()}  setup.exe".encode(),
        }
        self.consultas: list[str] = []
        self.executados: list[list[str]] = []

        def fetch(url: str) -> dict:
            self.consultas.append(url)
            return release

        return UpdateService(
            current_version=versao_local,
            fetch_json=fetch,
            open_url=lambda url: _Resposta(arquivos[url]),
            launcher=self.executados.append,
        )

    def test_compares_versions_by_number(self) -> None:
        self.assertEqual(parse_version("v1.10.2"), (1, 10, 2))
        self.assertTrue(is_newer("1.10.0", "1.9.9"))
        self.assertTrue(is_newer("v1.1.1", "1.1"))
        self.assertFalse(is_newer("1.1.0", "1.1"))
        self.assertFalse(is_newer("1.0.9", "1.1.0"))

    def test_finds_newer_release_with_installer(self) -> None:
        info = self._service(_release()).check()
        self.assertEqual(self.consultas, [LATEST_RELEASE_URL])
        self.assertEqual(info.versao, "1.2.0")
        self.assertEqual(info.instalador_nome, "DocFLow-Setup-1.2.0.exe")
        self.assertIn("Coisa nova", info.notas)

    def test_nothing_when_up_to_date_or_release_not_ready(self) -> None:
        self.assertIsNone(self._service(_release("v1.1.0")).check())
        self.assertIsNone(self._service(_release(prerelease=True)).check())
        sem_instalador = _release()
        sem_instalador["assets"] = []
        self.assertIsNone(self._service(sem_instalador).check())

    def test_offline_becomes_a_friendly_error(self) -> None:
        def offline(_url: str) -> dict:
            raise OSError("sem internet")

        with self.assertRaises(ValidationError):
            UpdateService(fetch_json=offline).check()

    def test_download_checks_sha256_and_installs_silently(self) -> None:
        service = self._service(_release())
        info = service.check()
        progresso: list[tuple[int, int]] = []
        with tempfile.TemporaryDirectory() as pasta:
            caminho = service.download(info, Path(pasta), on_progress=lambda f, t: progresso.append((f, t)))
            self.assertEqual(caminho.read_bytes(), INSTALADOR)
            service.install(caminho)
        self.assertEqual(progresso[-1], (len(INSTALADOR), len(INSTALADOR)))
        self.assertEqual(self.executados, [[str(caminho), *SILENT_INSTALL_ARGS]])
        self.assertIn("/RELAUNCH=1", SILENT_INSTALL_ARGS)

    def test_download_with_wrong_sha256_is_discarded(self) -> None:
        service = self._service(_release(), sha="0" * 64)
        info = service.check()
        with tempfile.TemporaryDirectory() as pasta:
            with self.assertRaises(ValidationError):
                service.download(info, Path(pasta))
            self.assertEqual(list(Path(pasta).iterdir()), [])
        self.assertEqual(self.executados, [])


if __name__ == "__main__":
    unittest.main()
