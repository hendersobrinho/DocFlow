from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from documentos_empresa_app.utils.common import CONFIG_DIR

LOG_FILE_NAME = "diagnostics.log"
MAX_BYTES = 2 * 1024 * 1024
BACKUP_COUNT = 3

_logger: logging.Logger | None = None


def get_diagnostics_log_path() -> Path:
    return CONFIG_DIR / LOG_FILE_NAME


def get_diagnostics_logger() -> logging.Logger:
    """Log tecnico do aplicativo (falhas em tarefas de segundo plano, importacao de
    planilhas etc.), gravado na pasta de configuracao do usuario com rotacao de arquivo.
    Guarda detalhes (tracebacks, linhas da planilha) que nao cabem na mensagem curta
    mostrada na tela."""
    global _logger
    if _logger is not None:
        return _logger

    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("docflow.diagnostics")
    logger.setLevel(logging.INFO)
    logger.propagate = False

    # So verifica handlers do TIPO que este modulo adiciona, nao "algum handler" - em
    # teste, o pytest costuma anexar seu proprio handler de captura de log neste mesmo
    # logger; tratando qualquer handler presente como "ja configurado" o RotatingFileHandler
    # real nunca era criado (o log ia soh pro capture do pytest, nunca pro arquivo).
    if not any(isinstance(handler, RotatingFileHandler) for handler in logger.handlers):
        handler = RotatingFileHandler(
            get_diagnostics_log_path(),
            maxBytes=MAX_BYTES,
            backupCount=BACKUP_COUNT,
            encoding="utf-8",
        )
        handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
        logger.addHandler(handler)

    _logger = logger
    return _logger


def _reset_for_tests() -> None:
    """So para uso em testes: descarta o logger cacheado (fechando so o handler que este
    modulo criou) para que a proxima chamada a get_diagnostics_logger() recrie o handler
    apontando para o CONFIG_DIR atual - necessario quando o teste faz patch de CONFIG_DIR,
    ja que o cache em nivel de modulo sobrevive entre casos de teste. So mexe no handler
    proprio (RotatingFileHandler) - remover indiscriminadamente qualquer handler tambem
    descartava o handler de captura de log que o pytest anexa neste mesmo logger."""
    global _logger
    if _logger is not None:
        for handler in list(_logger.handlers):
            if isinstance(handler, RotatingFileHandler):
                handler.close()
                _logger.removeHandler(handler)
    _logger = None
