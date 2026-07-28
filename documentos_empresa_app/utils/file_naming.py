from __future__ import annotations

import re
from pathlib import Path

_ILLEGAL_FOLDER_CHARS = re.compile(r'[/\\:*?"<>|]')


def resolve_unique_path(directory: Path, filename: str) -> Path:
    candidate = directory / filename
    if not candidate.exists():
        return candidate

    stem, suffix = Path(filename).stem, Path(filename).suffix
    counter = 1
    while True:
        candidate = directory / f"{stem} ({counter}){suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


def sanitize_folder_name_component(text: str) -> str:
    """Remove separadores de caminho e caracteres ilegais em nomes de pasta antes de usar
    um valor vindo do banco (ex: nome_empresa) para montar um caminho novo no disco."""
    cleaned = _ILLEGAL_FOLDER_CHARS.sub("", text).strip()
    return cleaned or "Empresa"


def list_missing_ancestor_dirs(path: Path) -> list[Path]:
    """Lista, da raiz para a folha, os diretorios em `path` que ainda nao existem no disco.
    Para no primeiro ancestral ja existente - nunca sobe alem da pasta raiz/empresa, que ja
    sao garantidas existir por quem chama esta funcao."""
    missing: list[Path] = []
    current = path
    while not current.exists():
        missing.append(current)
        current = current.parent
    missing.reverse()
    return missing
