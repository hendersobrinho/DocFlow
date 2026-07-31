from __future__ import annotations

from functools import lru_cache

from PySide6.QtGui import QIcon

from documentos_empresa_app.utils.resources import get_icons_directory, iter_icon_candidates

STATUS_ICON_FILENAMES = {
    "attention": "status_attention.svg",
    "completed": "status_completed.svg",
    "closed": "status_closed.svg",
    "in_progress": "status_in_progress.svg",
    "neutral": "status_neutral.svg",
    "not_started": "status_not_started.svg",
    "overdue": "status_overdue.svg",
    "save": "status_save.svg",
}

SITUATION_ICON_KEYS = {
    "nao_iniciada": "not_started",
    "em_andamento": "in_progress",
    "com_pendencia": "attention",
    "mes_em_atraso": "overdue",
    "concluida": "completed",
    "sem_documentos": "neutral",
    "sem_cobranca": "neutral",
}

STATUS_ICON_KEYS = {
    "": "not_started",
    "Recebido": "completed",
    "Pendente": "attention",
    "Encerrado": "closed",
    "Nao cobrar": "neutral",
}


@lru_cache(maxsize=32)
def get_status_icon(icon_name: str) -> QIcon:
    filename = STATUS_ICON_FILENAMES.get(icon_name)
    if not filename:
        return QIcon()
    path = get_icons_directory() / filename
    if not path.exists():
        return QIcon()
    return QIcon(str(path))


def situation_icon(situacao_key: str) -> QIcon:
    return get_status_icon(SITUATION_ICON_KEYS.get(situacao_key, "neutral"))


def document_status_icon(status: str) -> QIcon:
    return get_status_icon(STATUS_ICON_KEYS.get(status, "neutral"))


@lru_cache(maxsize=1)
def app_icon() -> QIcon:
    for path in iter_icon_candidates():
        return QIcon(str(path))
    return QIcon()


@lru_cache(maxsize=1)
def agent_chat_icon() -> QIcon:
    path = get_icons_directory() / "agent_chat.svg"
    if not path.exists():
        return QIcon()
    return QIcon(str(path))
