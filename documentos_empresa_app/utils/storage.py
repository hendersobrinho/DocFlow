from __future__ import annotations

from pathlib import Path

from documentos_empresa_app.utils.common import ValidationError


def normalize_database_filename(filename: str, default_name: str) -> str:
    normalized = str(filename).strip()
    if not normalized:
        normalized = default_name
    candidate = Path(normalized)
    if candidate.is_absolute() or candidate.name != normalized:
        raise ValidationError("Informe apenas o nome do arquivo do banco, sem caminho.")
    if not Path(normalized).suffix:
        normalized = f"{normalized}.db"
    return normalized


def build_database_path(folder: str | Path, filename: str, default_name: str) -> Path:
    folder_path = Path(folder).expanduser()
    if not str(folder_path).strip():
        raise ValidationError("Selecione uma pasta para armazenar o banco de dados.")
    return folder_path / normalize_database_filename(filename, default_name)


def is_path_within_directory(candidate_path: str | Path, directory: str | Path) -> bool:
    candidate = Path(candidate_path).expanduser().resolve()
    base_directory = Path(directory).expanduser().resolve()
    return candidate.is_relative_to(base_directory)


def create_database_directory(base_folder: str | Path, new_folder_name: str) -> Path:
    normalized_name = str(new_folder_name).strip()
    if not normalized_name:
        raise ValidationError("Informe um nome para a nova pasta.")

    new_folder = Path(normalized_name)
    if new_folder.is_absolute() or any(part in {".", ".."} for part in new_folder.parts):
        raise ValidationError("Informe apenas o nome da pasta a ser criada.")

    target_folder = Path(base_folder).expanduser() / new_folder
    target_folder.mkdir(parents=True, exist_ok=True)
    return target_folder
