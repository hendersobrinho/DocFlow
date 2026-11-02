"""Ligacao do DocFlow com o Claude Desktop (servidor MCP).

O Claude Desktop le os servidores MCP de um claude_desktop_config.json, mas o lugar desse
arquivo muda conforme a instalacao do Claude:
- instalador normal: %APPDATA%\\Claude\\claude_desktop_config.json
- Microsoft Store: %LOCALAPPDATA%\\Packages\\Claude_<id>\\LocalCache\\Roaming\\Claude\\...
  (a versao da loja enxerga so este; gravar no outro nao tem efeito)

Por isso a tela mostra todos os que existem, para onde cada um aponta e grava em todos.
O usuario e a senha do DocFlow que o Claude usa ficam no config.json do DocFlow,
com a senha protegida pelo DPAPI - o arquivo do Claude leva so o caminho do programa.
"""

from __future__ import annotations

from datetime import datetime
import json
import os
from pathlib import Path
import sys

from documentos_empresa_app.utils.helpers import load_config, save_config
from documentos_empresa_app.utils.secret_protection import protect_secret, unprotect_secret

SERVER_NAME = "docflow"
MCP_CREDENTIALS_KEY = "mcp_conexao"
MCP_EXE_NAME = "DocFLow-MCP.exe"
CONFIG_FILE_NAME = "claude_desktop_config.json"
PROJECT_ROOT = Path(__file__).resolve().parents[2]


# Credenciais ----------------------------------------------------------------------------


def save_mcp_credentials(usuario: str, senha: str | None) -> None:
    """Senha vazia mantem a que ja estava salva."""
    config = load_config()
    atual = config.get(MCP_CREDENTIALS_KEY) if isinstance(config.get(MCP_CREDENTIALS_KEY), dict) else {}
    config[MCP_CREDENTIALS_KEY] = {
        "usuario": usuario.strip(),
        "senha": protect_secret(senha) if senha else atual.get("senha"),
    }
    save_config(config)


def load_mcp_credentials() -> tuple[str, str] | None:
    dados = load_config().get(MCP_CREDENTIALS_KEY)
    if not isinstance(dados, dict):
        return None
    usuario = str(dados.get("usuario") or "").strip()
    senha = unprotect_secret(dados.get("senha"))
    if not usuario or not senha:
        return None
    return usuario, senha


def saved_mcp_user() -> str:
    dados = load_config().get(MCP_CREDENTIALS_KEY)
    return str(dados.get("usuario") or "") if isinstance(dados, dict) else ""


# Comando do servidor ----------------------------------------------------------------------


def server_command() -> tuple[str, list[str]]:
    """Como o Claude deve iniciar o servidor nesta instalacao: o DocFLow-MCP.exe ao lado do
    DocFLow.exe instalado ou, rodando pelo codigo-fonte, o Python atual com docflow_mcp."""
    if getattr(sys, "frozen", False):
        return str(Path(sys.executable).with_name(MCP_EXE_NAME)), []
    python = Path(sys.executable)
    if python.name.lower() == "pythonw.exe":
        python = python.with_name("python.exe")
    return str(python), [str(PROJECT_ROOT / "docflow_mcp")]


def server_entry() -> dict:
    command, args = server_command()
    return {"command": command, "args": args}


def config_snippet() -> str:
    """Trecho para colar em Claude > Configuracoes > Desenvolvedor > Editar configuracao."""
    return json.dumps({"mcpServers": {SERVER_NAME: server_entry()}}, ensure_ascii=False, indent=2)


# Arquivos do Claude Desktop ---------------------------------------------------------------


def claude_config_locations() -> list[dict]:
    """Os claude_desktop_config.json possiveis neste usuario do Windows, com o tipo da
    instalacao do Claude. Sem nenhum Claude encontrado, devolve o caminho padrao."""
    locais: list[dict] = []
    local_appdata = os.environ.get("LOCALAPPDATA")
    if local_appdata:
        for pacote in sorted(Path(local_appdata, "Packages").glob("Claude_*")):
            pasta = pacote / "LocalCache" / "Roaming" / "Claude"
            locais.append({"tipo": "Claude da Microsoft Store", "caminho": pasta / CONFIG_FILE_NAME})
    appdata = os.environ.get("APPDATA")
    if appdata:
        normal = Path(appdata) / "Claude" / CONFIG_FILE_NAME
        instalado = normal.parent.exists() or (local_appdata and Path(local_appdata, "AnthropicClaude").exists())
        if instalado or not locais:
            locais.append({"tipo": "Claude (instalador do site)", "caminho": normal})
    return locais


def inspect_config(caminho: Path) -> dict:
    """Situacao de um arquivo: se existe, se tem o DocFlow e para onde aponta."""
    caminho = Path(caminho)
    info = {"caminho": caminho, "existe": caminho.exists(), "erro": None, "tem_docflow": False,
            "comando": None, "args": [], "programa_existe": False, "desta_instalacao": False,
            "senha_no_arquivo": False}
    if not info["existe"]:
        return info
    try:
        dados = json.loads(caminho.read_text(encoding="utf-8-sig") or "{}")
    except (OSError, json.JSONDecodeError) as exc:
        info["erro"] = f"Arquivo com erro: {exc}"
        return info
    entrada = (dados.get("mcpServers") or {}).get(SERVER_NAME) if isinstance(dados, dict) else None
    if not isinstance(entrada, dict):
        return info
    comando = str(entrada.get("command") or "")
    args = [str(a) for a in entrada.get("args") or []]
    esperado = server_entry()
    info.update(
        tem_docflow=True,
        comando=comando,
        args=args,
        programa_existe=bool(comando) and Path(comando).exists() and all(Path(a).exists() for a in args),
        desta_instalacao=_same_path(comando, esperado["command"])
        and len(args) == len(esperado["args"])
        and all(_same_path(a, b) for a, b in zip(args, esperado["args"])),
        senha_no_arquivo=bool((entrada.get("env") or {}).get("DOCFLOW_MCP_SENHA")),
    )
    return info


def write_config(caminho: Path) -> Path | None:
    """Grava (ou corrige) o DocFlow no arquivo, mantendo os outros servidores do Claude.
    Faz uma copia do arquivo anterior ao lado e devolve o caminho dela."""
    caminho = Path(caminho)
    dados: dict = {}
    copia = None
    if caminho.exists():
        texto = caminho.read_text(encoding="utf-8-sig")
        dados = json.loads(texto) if texto.strip() else {}
        if not isinstance(dados, dict):
            raise ValueError(f"{caminho} nao contem um objeto JSON.")
        copia = caminho.with_name(f"{caminho.stem}.antes-docflow-{datetime.now():%Y%m%d-%H%M%S}.json")
        copia.write_text(texto, encoding="utf-8")
    servidores = dados.get("mcpServers")
    if not isinstance(servidores, dict):
        servidores = {}
    entrada = dict(servidores.get(SERVER_NAME) or {})
    entrada.update(server_entry())
    # Usuario e senha agora vem do DocFlow (protegidos); nada de senha em texto no arquivo.
    env = {k: v for k, v in (entrada.get("env") or {}).items() if k not in ("DOCFLOW_MCP_USUARIO", "DOCFLOW_MCP_SENHA")}
    if env:
        entrada["env"] = env
    else:
        entrada.pop("env", None)
    servidores[SERVER_NAME] = entrada
    dados["mcpServers"] = servidores
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")
    return copia


def _same_path(a: str, b: str) -> bool:
    try:
        return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))
    except (TypeError, ValueError):
        return False
