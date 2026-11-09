"""Robo de download do Onvio: para cada empresa, baixa tudo da pasta da competencia
(Contabilidade > AAAA > MM-AAAA) e extrai numa pasta do computador, mantendo as subpastas:

    Documentos\\Onvio\\03-2026\\170 - EMPRESA TESTE LTDA\\Extrato Bancario\\...

No fim grava _resumo.json na pasta da competencia (o Claude le e classifica os arquivos).

Passadas repetidas na mesma competencia so baixam o que chegou depois: o robo guarda o id de cada
arquivo baixado (_baixados.json), entao nao baixa de novo nem o que o Claude ja moveu ou renomeou.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
import io
import json
import os
from pathlib import Path
import re
import sys
from typing import Callable
import zipfile

from documentos_empresa_app.onvio.api import OnvioApi, OnvioError, SessaoExpirada, nome_competencia

BAIXADA = "baixada"
JA_BAIXADA = "ja_baixada"
SEM_CLIENTE = "sem_cliente_no_onvio"
SEM_PASTA = "sem_pasta"
PASTA_VAZIA = "pasta_vazia"
ERRO = "erro"
ROTULOS = {
    BAIXADA: "Baixada",
    JA_BAIXADA: "Sem novidades",
    SEM_CLIENTE: "Não achou o cliente no Onvio",
    SEM_PASTA: "Sem a pasta da competência",
    PASTA_VAZIA: "Pasta vazia",
    ERRO: "Erro",
}
RESUMO = "_resumo.json"
MANIFESTO = "_baixados.json"


@dataclass
class ResultadoEmpresa:
    codigo: str
    nome: str
    situacao: str
    arquivos: int = 0
    pasta: str = ""
    detalhe: str = ""
    novos: list[str] = field(default_factory=list)  # arquivos baixados nesta passada (caminho relativo)
    no_onvio: int = 0  # quantos arquivos a pasta tem no Onvio


@dataclass
class Resumo:
    competencia: str
    pasta: str
    empresas: list[ResultadoEmpresa] = field(default_factory=list)
    interrompido: str = ""

    def contagem(self) -> dict[str, int]:
        contagem: dict[str, int] = {}
        for empresa in self.empresas:
            contagem[empresa.situacao] = contagem.get(empresa.situacao, 0) + 1
        return contagem

    def arquivos(self) -> int:
        return sum(e.arquivos for e in self.empresas if e.situacao == BAIXADA)

    def texto(self) -> str:
        partes = [f"{ROTULOS[s]}: {n}" for s, n in self.contagem().items()]
        linha = f"Competência {self.competencia}: " + (", ".join(partes) or "nenhuma empresa")
        linha += f". {self.arquivos()} arquivo(s) baixado(s)."
        if self.interrompido:
            linha += f" Parou antes do fim: {self.interrompido}"
        return linha


def pasta_documentos() -> Path:
    """A pasta Documentos do Windows (mesmo se estiver no OneDrive)."""
    if sys.platform == "win32":
        try:
            import ctypes
            from ctypes import wintypes
            import uuid

            guid = uuid.UUID("{FDD39AD0-238F-46AF-ADB4-6C85480369C7}")  # FOLDERID_Documents

            class GUID(ctypes.Structure):
                _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD), ("Data3", wintypes.WORD), ("Data4", wintypes.BYTE * 8)]

            g = GUID(guid.fields[0], guid.fields[1], guid.fields[2], (wintypes.BYTE * 8).from_buffer_copy(guid.bytes[8:]))
            caminho = ctypes.c_wchar_p()
            if ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.byref(g), 0, None, ctypes.byref(caminho)) == 0:
                resultado = Path(caminho.value)
                ctypes.windll.ole32.CoTaskMemFree(caminho)
                return resultado
        except (OSError, AttributeError, ValueError):
            pass
    return Path.home() / "Documents"


def pasta_padrao() -> Path:
    return pasta_documentos() / "Onvio"


def nome_seguro(nome: str) -> str:
    """Nome que o Windows aceita como pasta/arquivo."""
    limpo = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", str(nome or "")).strip().rstrip(". ")
    return limpo[:120] or "_"


def _nome_no_zip(info: zipfile.ZipInfo) -> str:
    """O zip do Onvio grava alguns nomes em UTF-8 sem avisar (sai 'Extrato Banc├írio')."""
    nome = info.filename
    if not info.flag_bits & 0x800:
        try:
            nome = nome.encode("cp437").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            pass
    return nome


def _caminho_livre(alvo: Path) -> Path:
    if not alvo.exists():
        return alvo
    for numero in range(2, 1000):
        candidato = alvo.with_name(f"{alvo.stem} ({numero}){alvo.suffix}")
        if not candidato.exists():
            return candidato
    return alvo


def _extrair(conteudo: bytes, destino: Path, somente: set[str] | None = None, sobrescrever: bool = True) -> list[tuple[str, str]]:
    """Extrai mantendo as pastas e devolve [(chave, caminho relativo gravado)]. A chave e o caminho
    dentro do zip (partes separadas por /). Com 'somente', extrai so essas chaves. Ignora caminhos
    que tentem sair da pasta de destino. Arquivo que ja existe: sobrescreve ou ganha ' (2)'."""
    destino.mkdir(parents=True, exist_ok=True)
    raiz = destino.resolve()
    gravados: list[tuple[str, str]] = []
    with zipfile.ZipFile(io.BytesIO(conteudo)) as pacote:
        for info in pacote.infolist():
            partes = [nome_seguro(p) for p in _nome_no_zip(info).replace("\\", "/").split("/") if p and p not in (".", "..")]
            if not partes:
                continue
            chave = "/".join(partes)
            alvo = raiz.joinpath(*partes)
            if raiz not in alvo.resolve().parents and alvo.resolve() != raiz:
                continue
            if info.is_dir():
                if somente is None:
                    alvo.mkdir(parents=True, exist_ok=True)
                continue
            if somente is not None and chave not in somente:
                continue
            alvo.parent.mkdir(parents=True, exist_ok=True)
            if not sobrescrever:
                alvo = _caminho_livre(alvo)
            with pacote.open(info) as origem, open(alvo, "wb") as saida:
                while bloco := origem.read(1024 * 1024):
                    saida.write(bloco)
            gravados.append((chave, alvo.relative_to(raiz).as_posix()))
    return gravados


def extrair_zip(conteudo: bytes, destino: Path) -> int:
    """Extrai tudo mantendo as pastas; devolve quantos arquivos."""
    return len(_extrair(conteudo, destino))


def _chave(arquivo: dict) -> str:
    return "/".join(nome_seguro(parte) for parte in arquivo["caminho"])


def _ler_json(caminho: Path) -> dict:
    try:
        dados = json.loads(caminho.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return dados if isinstance(dados, dict) else {}


def _gravar_json(caminho: Path, dados: dict) -> None:
    temporario = caminho.with_suffix(".tmp")
    temporario.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporario, caminho)


def baixar_competencia(
    api: OnvioApi,
    ano: int,
    mes: int,
    empresas: list[tuple[str, str]],
    destino: Path | None = None,
    baixar_de_novo: bool = False,
    on_progress: Callable[[int, int, ResultadoEmpresa | None, str], None] | None = None,
    cancelado: Callable[[], bool] | None = None,
) -> Resumo:
    """empresas: [(codigo, nome)]. Baixa so o que ainda nao foi baixado (ou tudo, com baixar_de_novo)."""
    competencia = nome_competencia(ano, mes)
    pasta_comp = Path(destino or pasta_padrao()) / competencia
    pasta_comp.mkdir(parents=True, exist_ok=True)
    resumo = Resumo(competencia=f"{int(mes):02d}/{int(ano)}", pasta=str(pasta_comp))
    anteriores = {str(e.get("codigo")): e for e in (_ler_json(pasta_comp / RESUMO).get("empresas") or []) if isinstance(e, dict)}
    manifesto = _ler_json(pasta_comp / MANIFESTO)

    def avisar(feitas: int, resultado: ResultadoEmpresa | None, mensagem: str) -> None:
        if on_progress:
            on_progress(feitas, len(empresas), resultado, mensagem)

    def gravar() -> None:
        _gravar_resumo(resumo, anteriores)

    avisar(0, None, "Lendo a lista de clientes do Onvio...")
    try:
        clientes = api.clientes()
    except SessaoExpirada:
        raise
    except OnvioError as exc:
        resumo.interrompido = str(exc)
        gravar()
        return resumo

    for numero, (codigo, nome) in enumerate(empresas):
        if cancelado and cancelado():
            resumo.interrompido = "cancelado"
            break
        codigo = str(codigo).strip()
        cliente = clientes.get(codigo)
        nome_pasta = nome_seguro(f"{codigo} - {nome or (cliente or {}).get('nome') or ''}")
        alvo = pasta_comp / nome_pasta
        resultado = ResultadoEmpresa(codigo=codigo, nome=nome or (cliente or {}).get("nome", ""), situacao=ERRO, pasta=str(alvo))
        avisar(numero, None, f"{codigo} - {resultado.nome}")
        try:
            if not cliente:
                resultado.situacao = SEM_CLIENTE
                resultado.pasta = ""
            else:
                pasta = api.pasta_da_competencia(cliente["id"], ano, mes)
                if not pasta:
                    resultado.situacao = SEM_PASTA
                    resultado.pasta = ""
                else:
                    _baixar_novidades(api, pasta["id"], codigo, alvo, manifesto, resultado, baixar_de_novo)
                    _gravar_json(pasta_comp / MANIFESTO, manifesto)
        except SessaoExpirada:
            resumo.empresas.append(resultado)
            resumo.interrompido = "o login do Onvio expirou"
            gravar()
            raise
        except (OnvioError, OSError, zipfile.BadZipFile) as exc:
            resultado.situacao = ERRO
            resultado.detalhe = str(exc)
        resumo.empresas.append(resultado)
        avisar(numero + 1, resultado, f"{codigo} - {resultado.nome}: {ROTULOS[resultado.situacao]}")
        gravar()  # a cada empresa: se cair no meio, o que ja foi fica registrado
    gravar()
    return resumo


def _baixar_novidades(
    api: OnvioApi, pasta_id: str, codigo: str, alvo: Path, manifesto: dict, resultado: ResultadoEmpresa, baixar_de_novo: bool
) -> None:
    """Baixa da pasta da competencia so os arquivos que ainda nao foram baixados."""
    arquivos = api.arquivos_da_pasta(pasta_id)
    resultado.no_onvio = len(arquivos)
    if not arquivos:
        resultado.situacao = PASTA_VAZIA
        resultado.pasta = ""
        return
    legado = codigo not in manifesto  # baixado por versao antiga: reconhece pelo que ja esta na pasta
    conhecidos: dict = manifesto.setdefault(codigo, {})
    novos = []
    for arquivo in arquivos:
        chave = _chave(arquivo)
        if baixar_de_novo:
            novos.append(arquivo)
        elif arquivo["id"] in conhecidos:
            continue
        elif legado and alvo.joinpath(*chave.split("/")).exists():
            conhecidos[arquivo["id"]] = chave
        else:
            novos.append(arquivo)
    if not novos:
        resultado.situacao = JA_BAIXADA
        resultado.detalhe = f"{len(arquivos)} arquivo(s) no Onvio, nenhum novo"
        return
    pastas = list(dict.fromkeys(a["topo"] for a in novos if a["topo"]))
    soltos = [a["id"] for a in novos if not a["topo"]]
    conteudo = api.exportar_zip(pastas, soltos)
    por_chave = {_chave(a): a for a in novos}
    gravados = _extrair(conteudo, alvo, set(por_chave), sobrescrever=baixar_de_novo)
    for chave, relativo in gravados:
        conhecidos[por_chave[chave]["id"]] = relativo
        resultado.novos.append(relativo)
    resultado.arquivos = len(gravados)
    if gravados:
        resultado.situacao = BAIXADA
        resultado.detalhe = f"{len(gravados)} novo(s) de {len(arquivos)} no Onvio"
    else:
        resultado.situacao = ERRO
        resultado.detalhe = "O Onvio nao devolveu os arquivos novos no .zip."
        resultado.pasta = ""


def _gravar_resumo(resumo: Resumo, anteriores: dict[str, dict] | None = None) -> None:
    """Grava o resumo. Empresas de passadas anteriores que nao foram visitadas agora ficam no arquivo."""
    desta_vez = {e.codigo for e in resumo.empresas}
    empresas = [asdict(e) | {"situacao_texto": ROTULOS[e.situacao]} for e in resumo.empresas]
    empresas += [e for codigo, e in (anteriores or {}).items() if codigo not in desta_vez]
    dados = {
        "competencia": resumo.competencia,
        "pasta": resumo.pasta,
        "gerado_em": datetime.now().isoformat(timespec="seconds"),
        "interrompido": resumo.interrompido or None,
        "empresas": empresas,
    }
    _gravar_json(Path(resumo.pasta) / RESUMO, dados)
