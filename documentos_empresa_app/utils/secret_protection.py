from __future__ import annotations

import base64
import ctypes
import sys

DPAPI_PREFIX = "dpapi:"


def _protect_bytes(data: bytes) -> bytes:
    from ctypes import wintypes

    class _DataBlob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32

    buffer = ctypes.create_string_buffer(data, len(data))
    blob_in = _DataBlob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char)))
    blob_out = _DataBlob()
    if not crypt32.CryptProtectData(
        ctypes.byref(blob_in), None, None, None, None, 0, ctypes.byref(blob_out)
    ):
        raise OSError("Falha ao criptografar segredo via DPAPI.")
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        kernel32.LocalFree(blob_out.pbData)


def _unprotect_bytes(data: bytes) -> bytes:
    from ctypes import wintypes

    class _DataBlob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32

    buffer = ctypes.create_string_buffer(data, len(data))
    blob_in = _DataBlob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char)))
    blob_out = _DataBlob()
    if not crypt32.CryptUnprotectData(
        ctypes.byref(blob_in), None, None, None, None, 0, ctypes.byref(blob_out)
    ):
        raise OSError("Falha ao descriptografar segredo via DPAPI.")
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        kernel32.LocalFree(blob_out.pbData)


def protect_secret(plaintext: str | None) -> str | None:
    """Criptografa um segredo (API key, token de sessao lembrada) com o DPAPI do
    Windows, amarrando-o ao usuario do Windows que o configurou - assim o
    config.json sozinho (por exemplo, copiado num backup ou pendrive) nao basta
    pra extrair o segredo em outro computador ou usuario. Fora do Windows (ou se
    o DPAPI falhar), guarda em texto plano como ja acontecia antes."""
    if not plaintext:
        return plaintext
    if sys.platform != "win32":
        return plaintext
    try:
        encrypted = _protect_bytes(plaintext.encode("utf-8"))
    except OSError:
        return plaintext
    return DPAPI_PREFIX + base64.b64encode(encrypted).decode("ascii")


def unprotect_secret(stored: str | None) -> str | None:
    """Reverte protect_secret. Valores antigos gravados em texto plano (sem o
    prefixo) sao devolvidos como estao, pra manter compatibilidade com
    instalacoes existentes - eles passam a ser criptografados na proxima vez
    que forem salvos."""
    if not stored:
        return stored
    if not stored.startswith(DPAPI_PREFIX):
        return stored
    if sys.platform != "win32":
        return None
    try:
        raw = base64.b64decode(stored[len(DPAPI_PREFIX):])
        return _unprotect_bytes(raw).decode("utf-8")
    except (OSError, ValueError):
        return None
