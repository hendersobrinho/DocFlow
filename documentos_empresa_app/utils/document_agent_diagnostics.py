from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from documentos_empresa_app.utils.common import CONFIG_DIR, redact_cpf

LOG_FILE_NAME = "document_agent_diagnostics.log"
MAX_BYTES = 2 * 1024 * 1024
BACKUP_COUNT = 3
TEXT_SNIPPET_CHARS = 400

_logger: logging.Logger | None = None


def get_document_agent_log_path() -> Path:
    return CONFIG_DIR / LOG_FILE_NAME


def get_document_agent_logger() -> logging.Logger:
    """Logger tecnico das camadas do agente organizador de documentos que rodam
    sem IA (extracao de texto do PDF/planilha e casamento por CNPJ via regex).

    Separado de proposito do 'motivo' de negocio salvo por documento na fila de
    revisao: aqui entram detalhes tecnicos (candidatos de CNPJ encontrados, trecho
    do texto extraido, excecoes) para depurar e ajustar essas camadas depois,
    olhando padroes de falha reais em vez de casos isolados."""
    global _logger
    if _logger is not None:
        return _logger

    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("docflow.document_agent")
    logger.setLevel(logging.INFO)
    logger.propagate = False

    if not logger.handlers:
        handler = RotatingFileHandler(
            get_document_agent_log_path(),
            maxBytes=MAX_BYTES,
            backupCount=BACKUP_COUNT,
            encoding="utf-8",
        )
        handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
        logger.addHandler(handler)

    _logger = logger
    return _logger


def _reset_for_tests() -> None:
    """So para uso em testes: descarta o logger cacheado (fechando seus handlers)
    para que a proxima chamada a get_document_agent_logger() recrie o handler
    apontando para o CONFIG_DIR atual - necessario quando o teste faz patch de
    CONFIG_DIR, ja que o cache em nivel de modulo sobrevive entre casos de teste."""
    global _logger
    if _logger is not None:
        for handler in list(_logger.handlers):
            handler.close()
            _logger.removeHandler(handler)
    _logger = None


def _snippet(text: str) -> str:
    normalized = " ".join(redact_cpf(str(text or "")).split())
    if len(normalized) > TEXT_SNIPPET_CHARS:
        return normalized[:TEXT_SNIPPET_CHARS] + "..."
    return normalized


def log_extraction_failure(file_path: str, error: str) -> None:
    get_document_agent_logger().error("EXTRACAO_FALHOU | arquivo=%s | erro=%s", file_path, error)


def log_unmatched_cnpj(file_path: str, cnpj_candidates: list[str], text: str) -> None:
    logger = get_document_agent_logger()
    if cnpj_candidates:
        logger.warning(
            "CNPJ_NAO_CADASTRADO | arquivo=%s | candidatos=%s | trecho=%r",
            file_path,
            cnpj_candidates,
            _snippet(text),
        )
    else:
        logger.warning(
            "CNPJ_NAO_ENCONTRADO | arquivo=%s | trecho=%r",
            file_path,
            _snippet(text),
        )


def log_move_failure(file_path: str, destino: str, error: str) -> None:
    get_document_agent_logger().error(
        "MOVER_ARQUIVO_FALHOU | arquivo=%s | destino=%s | erro=%s", file_path, destino, error
    )
