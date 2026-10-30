from __future__ import annotations

from functools import lru_cache

from PySide6.QtGui import QIcon

from documentos_empresa_app.utils.resources import iter_icon_candidates


@lru_cache(maxsize=1)
def app_icon() -> QIcon:
    for path in iter_icon_candidates():
        return QIcon(str(path))
    return QIcon()
