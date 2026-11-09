"""Sessao do Onvio pelo navegador (Playwright com o Edge ou o Chrome ja instalados).

Na primeira vez abre uma janela do Onvio para a pessoa entrar (usuario, senha e codigo da
Thomson Reuters). Depois a sessao fica guardada neste computador, criptografada (DPAPI),
e o robo roda sem janela. Quando o login expira, a janela abre de novo.

As chamadas a API saem de dentro de uma pagina do onvio.com.br (fetch na pagina), do mesmo
jeito que o proprio site faz - assim valem exatamente os mesmos cookies e regras do login.
"""

from __future__ import annotations

import base64
from contextlib import contextmanager
import json
import time
from typing import Callable, Iterator

from documentos_empresa_app.onvio.api import BASE_URL, OnvioApi, OnvioError, SessaoExpirada
from documentos_empresa_app.utils.helpers import load_config, save_config
from documentos_empresa_app.utils.secret_protection import protect_secret, unprotect_secret

SESSAO_CONFIG_KEY = "onvio_sessao"
URL_LOGIN = f"{BASE_URL}/staff/"
URL_SESSAO = "/api/security/v1/session-and-bindings"
CANAIS = ("msedge", "chrome", None)  # None = Chromium do Playwright (playwright install chromium)
ESPERA_LOGIN_SEGUNDOS = 900

_JS_FETCH = """async ([url, metodo, corpo]) => {
    const headers = {'Accept': 'application/json'};
    if (corpo !== null) headers['Content-Type'] = 'application/json';
    const r = await fetch(url, {method: metodo, credentials: 'include', headers, body: corpo});
    return {status: r.status, tipo: r.headers.get('content-type') || '', texto: await r.text()};
}"""

_JS_BYTES = """async (url) => {
    const r = await fetch(url, {credentials: 'include'});
    const tipo = r.headers.get('content-type') || '';
    if (!r.ok) return {status: r.status, tipo, dados: ''};
    const b = new Uint8Array(await r.arrayBuffer());
    let s = '';
    for (let i = 0; i < b.length; i += 0x8000) s += String.fromCharCode.apply(null, b.subarray(i, i + 0x8000));
    return {status: r.status, tipo, dados: btoa(s)};
}"""


def _no_onvio(url: str | None) -> bool:
    return str(url or "").startswith(BASE_URL + "/")


def _expirou() -> SessaoExpirada:
    return SessaoExpirada("O login do Onvio expirou. Entre de novo.")


class _TransportePagina:
    """Faz as chamadas com fetch dentro de uma pagina do onvio.com.br."""

    def __init__(self, pagina) -> None:
        self.pagina = pagina

    def _resposta(self, caminho: str, metodo: str, corpo: str | None) -> dict:
        if not _no_onvio(self.pagina.url):
            raise _expirou()
        return self.pagina.evaluate(_JS_FETCH, [BASE_URL + caminho, metodo, corpo])

    def _json(self, resposta: dict, caminho: str) -> dict:
        status = resposta.get("status")
        if status in (401, 403):
            raise _expirou()
        if not 200 <= int(status or 0) < 300:
            raise OnvioError(f"O Onvio respondeu {status} em {caminho.split('?')[0]}.")
        if "json" not in resposta.get("tipo", ""):
            # Sem sessao o Onvio devolve a pagina de login (HTML) em vez do JSON.
            raise _expirou()
        texto = resposta.get("texto") or ""
        return json.loads(texto) if texto.strip() else {}

    def get_json(self, caminho: str) -> dict:
        return self._json(self._resposta(caminho, "GET", None), caminho)

    def post_json(self, caminho: str, corpo: dict) -> dict:
        return self._json(self._resposta(caminho, "POST", json.dumps(corpo)), caminho)

    def get_bytes(self, caminho: str) -> bytes:
        if not _no_onvio(self.pagina.url):
            raise _expirou()
        resposta = self.pagina.evaluate(_JS_BYTES, BASE_URL + caminho)
        status = resposta.get("status")
        if status in (401, 403):
            raise _expirou()
        if not 200 <= int(status or 0) < 300:
            raise OnvioError(f"O Onvio respondeu {status} em {caminho.split('?')[0]}.")
        if "html" in resposta.get("tipo", ""):
            raise _expirou()
        return base64.b64decode(resposta.get("dados") or "")


def _estado_salvo() -> dict | None:
    bruto = unprotect_secret(load_config().get(SESSAO_CONFIG_KEY))
    try:
        return json.loads(bruto) if bruto else None
    except ValueError:
        return None


def _salvar_estado(contexto) -> None:
    config = load_config()
    config[SESSAO_CONFIG_KEY] = protect_secret(json.dumps(contexto.storage_state()))
    save_config(config)


def esquecer_sessao() -> None:
    config = load_config()
    if config.pop(SESSAO_CONFIG_KEY, None) is not None:
        save_config(config)


def _verificar(pagina) -> str:
    """'' se a pagina esta logada no Onvio; senao o motivo (para a mensagem de erro)."""
    try:
        if pagina.is_closed():
            return "janela fechada"
        if not _no_onvio(pagina.url):
            return "fora do onvio.com.br"
        resposta = pagina.evaluate(_JS_FETCH, [BASE_URL + URL_SESSAO, "GET", None])
    except Exception as exc:  # noqa: BLE001 - pagina navegando, fechada...
        return f"pagina ocupada ({str(exc).splitlines()[0][:80]})"
    status, tipo = resposta.get("status"), resposta.get("tipo", "")
    if status == 200 and "json" in tipo:
        try:
            sessao = json.loads(resposta.get("texto") or "{}")
        except ValueError:
            return "resposta invalida"
        if sessao:
            return ""
    return f"sessao respondeu {status} ({tipo.split(';')[0] or 'sem tipo'})"


def _pagina_logada(contexto):
    """Alguma aba do contexto que ja esta logada no Onvio (ou None) e o ultimo motivo."""
    motivo = "nenhuma aba do Onvio"
    for pagina in list(contexto.pages):
        motivo = _verificar(pagina)
        if not motivo:
            return pagina, ""
    return None, motivo


def _abrir_navegador(playwright, headless: bool):
    erros = []
    for canal in CANAIS:
        try:
            return playwright.chromium.launch(channel=canal, headless=headless) if canal else playwright.chromium.launch(headless=headless)
        except Exception as exc:  # noqa: BLE001
            erros.append(f"{canal or 'chromium'}: {str(exc).splitlines()[0]}")
    raise OnvioError("Não encontrei o Edge nem o Chrome neste computador.\n" + "\n".join(erros))


def _sessao_sem_janela(playwright):
    """Tenta a sessao guardada, sem janela. Devolve (navegador, contexto, pagina) ou None."""
    estado = _estado_salvo()
    if not estado:
        return None
    navegador = _abrir_navegador(playwright, headless=True)
    try:
        contexto = navegador.new_context(storage_state=estado, accept_downloads=True)
        pagina = contexto.new_page()
        pagina.goto(BASE_URL + URL_SESSAO, wait_until="commit", timeout=60_000)
        pagina.wait_for_load_state("domcontentloaded", timeout=60_000)
        if not _verificar(pagina):
            return navegador, contexto, pagina
    except Exception:  # noqa: BLE001 - qualquer falha aqui e "precisa entrar de novo"
        pass
    navegador.close()
    return None


@contextmanager
def sessao_onvio(
    avisar: Callable[[str], None] | None = None,
    pode_abrir_janela: bool = True,
    cancelado: Callable[[], bool] | None = None,
) -> Iterator[OnvioApi]:
    """Entrega a OnvioApi com a sessao pronta. Sem login valido abre a janela do Onvio e
    espera a pessoa entrar (ate 15 minutos); com pode_abrir_janela=False so avisa."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:  # pragma: no cover - so sem o pacote instalado
        raise OnvioError("Falta o pacote playwright: pip install playwright") from exc

    avisar = avisar or (lambda _m: None)
    with sync_playwright() as playwright:
        aberta = _sessao_sem_janela(playwright)
        if aberta:
            navegador, contexto, pagina = aberta
        else:
            if not pode_abrir_janela:
                raise SessaoExpirada("Entre no Onvio pelo DocFlow (Panorama > Ferramentas > Baixar do Onvio) uma vez.")
            avisar("Entre no Onvio na janela que abriu (usuário, senha e código). O robô continua sozinho depois.")
            navegador = _abrir_navegador(playwright, headless=False)
            contexto = navegador.new_context(accept_downloads=True)
            primeira = contexto.new_page()
            try:
                # O site e pesado: nao espera carregar tudo, so comecar.
                primeira.goto(URL_LOGIN, wait_until="commit", timeout=120_000)
            except Exception:  # noqa: BLE001 - a pessoa ve a pagina e pode recarregar
                pass
            inicio = time.monotonic()
            while True:
                pagina, motivo = _pagina_logada(contexto)
                if pagina:
                    break
                if cancelado and cancelado():
                    navegador.close()
                    raise OnvioError("Cancelado.")
                if not contexto.pages:
                    navegador.close()
                    raise OnvioError("A janela do Onvio foi fechada antes do login.")
                if time.monotonic() - inicio > ESPERA_LOGIN_SEGUNDOS:
                    navegador.close()
                    raise OnvioError(f"O login do Onvio não foi reconhecido em 15 minutos ({motivo}). Tente de novo.")
                contexto.pages[0].wait_for_timeout(2000)
            # Aba propria e parada (a do site continua navegando sozinha).
            try:
                trabalho = contexto.new_page()
                trabalho.goto(BASE_URL + URL_SESSAO, wait_until="commit", timeout=60_000)
                trabalho.wait_for_load_state("domcontentloaded", timeout=60_000)
                if not _verificar(trabalho):
                    pagina = trabalho
            except Exception:  # noqa: BLE001 - fica com a aba do login
                pass
            avisar("Login feito. Baixando... (pode minimizar a janela do Onvio, não feche)")
        _salvar_estado(contexto)
        try:
            yield OnvioApi(_TransportePagina(pagina))
            _salvar_estado(contexto)  # a sessao pode ter sido renovada no caminho
        finally:
            contexto.close()
            navegador.close()
