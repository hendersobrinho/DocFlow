"""Atualizacao automatica pelo GitHub Releases.

O pipeline do GitHub (.github/workflows/release.yml) publica, a cada tag vX.Y.Z, o
instalador DocFLow-Setup-X.Y.Z.exe e o arquivo .sha256 dele. Aqui o sistema consulta a
ultima release, compara com a versao instalada, baixa o instalador conferindo o SHA-256
e o executa em modo silencioso: o Inno Setup fecha o DocFlow, instala por cima e abre de
novo (parametro /RELAUNCH=1). Os dados ficam em %APPDATA%\\DocFLow e no PostgreSQL, entao
a atualizacao nao mexe neles.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from typing import Callable
import urllib.request

from documentos_empresa_app import __version__
from documentos_empresa_app.utils.common import ValidationError
from documentos_empresa_app.utils.diagnostics import get_diagnostics_logger

GITHUB_REPO = "hendersobrinho/DocFlow"
LATEST_RELEASE_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
INSTALLER_NAME = re.compile(r"^DocFLow-Setup-(?P<versao>[0-9][0-9A-Za-z.\-]*)\.exe$")
TIMEOUT_SECONDS = 20
CHUNK_SIZE = 256 * 1024
# Parametros do Inno Setup: sem janelas, fecha o DocFlow aberto e reabre no fim.
SILENT_INSTALL_ARGS = ["/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS", "/RELAUNCH=1"]


def parse_version(texto: str) -> tuple[int, ...]:
    """'v1.10.2' -> (1, 10, 2). Sufixos (-beta) sao ignorados na comparacao."""
    numeros = re.findall(r"\d+", str(texto or "").split("-", 1)[0])
    if not numeros:
        raise ValidationError(f'Versão inválida: "{texto}".')
    return tuple(int(n) for n in numeros)


def is_newer(remota: str, local: str) -> bool:
    a, b = parse_version(remota), parse_version(local)
    largura = max(len(a), len(b))
    return a + (0,) * (largura - len(a)) > b + (0,) * (largura - len(b))


def can_self_update() -> bool:
    """So a versao instalada (o .exe empacotado) se atualiza sozinha; rodando pelo codigo
    fonte, quem atualiza e o git."""
    return sys.platform == "win32" and bool(getattr(sys, "frozen", False))


@dataclass(frozen=True)
class UpdateInfo:
    versao: str
    notas: str
    pagina: str
    instalador_url: str
    instalador_nome: str
    tamanho: int
    sha256_url: str | None


def _http_get(url: str, accept: str = "application/octet-stream"):
    request = urllib.request.Request(
        url, headers={"User-Agent": f"DocFlow/{__version__}", "Accept": accept}
    )
    return urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS)  # noqa: S310 - so https do GitHub


def _fetch_json(url: str) -> dict:
    with _http_get(url, accept="application/vnd.github+json") as resposta:
        return json.loads(resposta.read().decode("utf-8"))


class UpdateService:
    def __init__(
        self,
        current_version: str = __version__,
        fetch_json: Callable[[str], dict] = _fetch_json,
        open_url: Callable[[str], object] = _http_get,
        launcher: Callable[[list[str]], object] | None = None,
    ) -> None:
        self.current_version = current_version
        self._fetch_json = fetch_json
        self._open_url = open_url
        self._launcher = launcher or self._launch_detached

    def check(self) -> UpdateInfo | None:
        """A ultima release, se for mais nova que a instalada; None se ja esta em dia."""
        try:
            release = self._fetch_json(LATEST_RELEASE_URL)
        except Exception as exc:
            get_diagnostics_logger().warning("ATUALIZACAO_CONSULTA_FALHOU | erro=%s", exc)
            raise ValidationError(
                "Não foi possível consultar se há versão nova. Confira a internet e tente de novo."
            ) from exc
        versao = str(release.get("tag_name") or "").lstrip("vV")
        if not versao or release.get("draft") or release.get("prerelease"):
            return None
        if not is_newer(versao, self.current_version):
            return None
        assets = {a.get("name"): a for a in release.get("assets") or []}
        instalador = next((a for nome, a in assets.items() if nome and INSTALLER_NAME.match(nome)), None)
        if instalador is None:
            # Release ainda sem instalador (pipeline rodando): tenta de novo mais tarde.
            return None
        checksum = assets.get(f'{instalador["name"]}.sha256')
        return UpdateInfo(
            versao=versao,
            notas=str(release.get("body") or "").strip(),
            pagina=str(release.get("html_url") or ""),
            instalador_url=instalador["browser_download_url"],
            instalador_nome=instalador["name"],
            tamanho=int(instalador.get("size") or 0),
            sha256_url=checksum["browser_download_url"] if checksum else None,
        )

    def download(
        self,
        info: UpdateInfo,
        destino: Path | None = None,
        on_progress: Callable[[int, int], None] | None = None,
    ) -> Path:
        """Baixa o instalador para a pasta temporaria e confere o SHA-256 publicado junto."""
        pasta = Path(destino or Path(tempfile.gettempdir()) / "DocFLow-atualizacao")
        pasta.mkdir(parents=True, exist_ok=True)
        caminho = pasta / info.instalador_nome
        parcial = caminho.with_suffix(".part")
        esperado = self._expected_sha256(info)
        digest = hashlib.sha256()
        baixado = 0
        try:
            with self._open_url(info.instalador_url) as resposta, open(parcial, "wb") as saida:
                total = int(resposta.headers.get("Content-Length") or info.tamanho or 0)
                while True:
                    bloco = resposta.read(CHUNK_SIZE)
                    if not bloco:
                        break
                    saida.write(bloco)
                    digest.update(bloco)
                    baixado += len(bloco)
                    if on_progress:
                        on_progress(baixado, total)
        except Exception as exc:
            parcial.unlink(missing_ok=True)
            get_diagnostics_logger().warning("ATUALIZACAO_DOWNLOAD_FALHOU | erro=%s", exc)
            raise ValidationError("O download da atualização falhou. Confira a internet e tente de novo.") from exc
        if esperado and digest.hexdigest().lower() != esperado:
            parcial.unlink(missing_ok=True)
            raise ValidationError("O arquivo baixado veio diferente do publicado (SHA-256 não confere). Tente de novo.")
        parcial.replace(caminho)
        return caminho

    def install(self, instalador: Path) -> None:
        """Inicia o instalador em segundo plano. Quem chama deve fechar o DocFlow logo em
        seguida; o instalador abre o sistema de novo quando terminar."""
        get_diagnostics_logger().info("ATUALIZACAO_INICIADA | instalador=%s", instalador)
        self._launcher([str(instalador), *SILENT_INSTALL_ARGS])

    def _expected_sha256(self, info: UpdateInfo) -> str | None:
        if not info.sha256_url:
            return None
        try:
            with self._open_url(info.sha256_url) as resposta:
                texto = resposta.read().decode("utf-8", "replace")
        except Exception as exc:
            raise ValidationError("Não foi possível baixar a verificação (SHA-256) da atualização.") from exc
        match = re.search(r"\b[0-9a-fA-F]{64}\b", texto)
        if not match:
            raise ValidationError("A verificação (SHA-256) da atualização está em formato inesperado.")
        return match.group(0).lower()

    @staticmethod
    def _launch_detached(comando: list[str]) -> None:
        flags = 0
        if sys.platform == "win32":
            flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        subprocess.Popen(comando, creationflags=flags, close_fds=True)  # noqa: S603 - instalador baixado e conferido
