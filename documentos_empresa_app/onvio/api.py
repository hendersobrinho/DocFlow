"""Chamadas a API interna do Onvio (a mesma que a tela usa), feitas com a sessao de quem
esta logado. Nada aqui abre navegador: quem faz as requisicoes e o 'transporte' (o
navegador do Playwright em navegador.py, ou um falso nos testes).

Caminho dos documentos de uma empresa no Onvio:
    cliente (pelo codigo) > Contabilidade > 2026 > 03-2026 > subpastas e arquivos
O download e o mesmo do botao Gerenciar > Baixar: um 'job' de exportacao que devolve um .zip.
"""

from __future__ import annotations

import json
import re
import time
from typing import Callable, Protocol

BASE_URL = "https://onvio.com.br"
PAGINA = 100


class OnvioError(Exception):
    """Falha ao falar com o Onvio (mensagem pronta para mostrar)."""


class SessaoExpirada(OnvioError):
    """O login caiu: e preciso entrar no Onvio de novo."""


class Transporte(Protocol):
    def get_json(self, caminho: str) -> dict: ...

    def post_json(self, caminho: str, corpo: dict) -> dict: ...

    def get_bytes(self, caminho: str) -> bytes: ...


def normalizar(nome: str | None) -> str:
    return re.sub(r"\s+", " ", str(nome or "")).strip().casefold()


def nome_competencia(ano: int, mes: int) -> str:
    """Como a pasta da competencia se chama no Onvio: 03-2026."""
    return f"{int(mes):02d}-{int(ano)}"


def _e_competencia(nome: str, ano: int, mes: int) -> bool:
    """Aceita 03-2026, 3-2026, 03/2026, 03.2026, 03_2026."""
    achado = re.fullmatch(r"\s*(\d{1,2})\s*[-/._ ]\s*(\d{4})\s*", str(nome or ""))
    return bool(achado) and int(achado.group(1)) == int(mes) and int(achado.group(2)) == int(ano)


class OnvioApi:
    def __init__(self, transporte: Transporte, espera: Callable[[float], None] = time.sleep) -> None:
        self.t = transporte
        self._espera = espera
        self._escritorio: str | None = None

    # Sessao / escritorio ---------------------------------------------------------------

    def escritorio_id(self) -> str:
        """Id do escritorio (a 'company' do Onvio), que entra na busca de clientes."""
        if self._escritorio is None:
            sessao = self.t.get_json("/api/security/v1/session-and-bindings")
            achado = re.search(r'"(?:companyId|firmId|CompanyId)"\s*:\s*"([0-9A-Fa-f]{32})"', json.dumps(sessao))
            if not achado:
                raise OnvioError("Nao foi possivel identificar o escritorio na sessao do Onvio.")
            self._escritorio = achado.group(1)
        return self._escritorio

    # Clientes ---------------------------------------------------------------------------

    def clientes(self) -> dict[str, dict]:
        """Todos os clientes ativos: {codigo: {"id", "codigo", "nome"}}."""
        filtro = json.dumps({"useOr": True, "items": [{"by": "clientMainExpanded.status.id", "op": "EQ", "value": "ACTIVE"}]})
        encontrados: dict[str, dict] = {}
        pagina = 1
        while True:
            corpo = {
                "filterSearchSort": {"orderBy": "name asc", "search": "", "searchBy": None, "filter": filtro},
                "pagingDataRequest": {"startIndex": None, "pageIndex": pagina, "itemsPerPage": PAGINA},
                "frp": "Onvio.StaffStorage",
                "excludeCount": True,
            }
            resposta = self.t.post_json(f"/api/core/v3/companies/{self.escritorio_id()}/clients/search", corpo)
            itens = (resposta.get("data") or resposta).get("items") or []
            for item in itens:
                codigo = str(item.get("code") or "").strip()
                if codigo:
                    encontrados[codigo] = {"id": item["id"], "codigo": codigo, "nome": str(item.get("name") or "").strip()}
            if len(itens) < PAGINA or pagina >= 200:
                return encontrados
            pagina += 1

    # Pastas -----------------------------------------------------------------------------

    def pastas_do_cliente(self, cliente_id: str) -> list[dict]:
        """As pastas de primeiro nivel (Contabilidade, Fiscal...) - no Onvio sao 'projects'."""
        resposta = self.t.get_json(
            f"/api/storage/v1/projects?primaryAssociationId={cliente_id}&primaryAssociationType=Client"
        )
        dados = resposta.get("data")
        itens = dados.get("items") if isinstance(dados, dict) else dados
        return list(itens or [])

    def filhos(self, pasta_id: str, projeto: bool = False, so_pastas: bool = False) -> list[dict]:
        """Conteudo de uma pasta (subpastas e arquivos), todas as paginas."""
        tipo = "Projects" if projeto else "Folders"
        itens: list[dict] = []
        inicio = 1
        while True:
            resposta = self.t.get_json(
                f"/api/storage/v2/{tipo}/{pasta_id}/children?from={inicio}&pageSize={PAGINA}&sort=name:asc"
                f"&containersOnly={'true' if so_pastas else 'false'}&trashed=false&countDocuments=false&calculateLocks=false"
            )
            dados = resposta.get("data") or {}
            pagina = dados.get("items") or []
            itens.extend(pagina)
            if not dados.get("hasMore") or not pagina:
                return itens
            inicio += len(pagina)

    def arquivos_da_pasta(self, pasta_id: str, profundidade: int = 8) -> list[dict]:
        """Todos os arquivos da pasta, com as subpastas: [{"id", "nome", "caminho": [subpastas...,
        nome], "topo": id da pasta de primeiro nivel (None se o arquivo esta solto na raiz)}]."""
        arquivos: list[dict] = []

        def visitar(atual: str, caminho: list[str], topo: str | None, nivel: int) -> None:
            for item in self.filhos(atual):
                nome = str(item.get("name") or "").strip()
                if str(item.get("itemType")).lower() == "folder":
                    if nivel < profundidade:
                        visitar(item["id"], caminho + [nome], topo or item["id"], nivel + 1)
                else:
                    arquivos.append({"id": item["id"], "nome": nome, "caminho": caminho + [nome], "topo": topo})

        visitar(pasta_id, [], None, 1)
        return arquivos

    def pasta_da_competencia(self, cliente_id: str, ano: int, mes: int, pasta_raiz: str = "Contabilidade") -> dict | None:
        """Contabilidade > AAAA > MM-AAAA. Sem a pasta do ano, procura a da competencia direto
        dentro de Contabilidade. None se nao existe."""
        raiz = next((p for p in self.pastas_do_cliente(cliente_id) if normalizar(p.get("name")) == normalizar(pasta_raiz)), None)
        if not raiz:
            return None
        dentro = self.filhos(raiz["id"], projeto=True, so_pastas=True)
        ano_pasta = next((p for p in dentro if str(p.get("name") or "").strip() == str(ano)), None)
        if ano_pasta:
            competencia = next(
                (p for p in self.filhos(ano_pasta["id"], so_pastas=True) if _e_competencia(p.get("name"), ano, mes)), None
            )
            if competencia:
                return competencia
        return next((p for p in dentro if _e_competencia(p.get("name"), ano, mes)), None)

    # Download ---------------------------------------------------------------------------

    def exportar_zip(self, pastas: list[str], arquivos: list[str], limite_segundos: float = 900) -> bytes:
        """Gerenciar > Baixar: pede o .zip, espera ficar pronto e devolve o conteudo."""
        if not pastas and not arquivos:
            raise OnvioError("Nada para baixar.")
        resposta = self.t.post_json("/api/storage/v1/jobs/export", {"folderIDs": pastas, "fileIDs": arquivos})
        job = resposta.get("data")
        if isinstance(job, dict):
            job = job.get("jobID") or job.get("id")
        if not job:
            raise OnvioError("O Onvio nao aceitou o pedido de download.")
        decorrido = 0.0
        intervalo = 1.0
        while True:
            dados = self.t.get_json(f"/api/storage/v1/jobs/{job}").get("data") or {}
            situacao = str(dados.get("jobStatus") or "").upper()
            if situacao == "SUCCESS":
                break
            if situacao in ("FAILED", "FAILURE", "ERROR", "CANCELLED", "CANCELED"):
                raise OnvioError(f"O Onvio nao conseguiu montar o arquivo (situacao {situacao}).")
            if decorrido >= limite_segundos:
                raise OnvioError("O Onvio demorou demais para montar o arquivo .zip.")
            self._espera(intervalo)
            decorrido += intervalo
            intervalo = min(intervalo * 1.5, 5.0)
        return self.t.get_bytes(f"/api/storage/v1/jobs/{job}/result")
