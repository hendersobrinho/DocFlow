from __future__ import annotations

import threading
import time
from typing import Any, Callable, Hashable


class ResultCache:
    """Guarda o resultado de leituras pesadas (fila de cobranca, plano de acoes) enquanto o
    banco nao muda.

    Vale ate a proxima escrita feita por este programa (DatabaseManager.write_generation) ou
    ate 'ttl' segundos - o que vier primeiro. O ttl cobre o que outro computador ou o
    Claude (MCP) gravar no mesmo banco. Devolve sempre uma copia, porque quem chama pode
    alterar o resultado (ex: o MCP tira campos antes de responder)."""

    def __init__(self, db_manager, ttl: float = 20.0, max_entries: int = 16) -> None:
        self.db_manager = db_manager
        self.ttl = ttl
        self.max_entries = max_entries
        self._entries: dict[Hashable, tuple[int, float, Any]] = {}
        self._lock = threading.Lock()

    def get(self, key: Hashable, compute: Callable[[], Any], *, copy: bool = True) -> Any:
        """copy=False devolve o proprio objeto guardado: so para quem le sem alterar."""
        generation = getattr(self.db_manager, "write_generation", None)
        now = time.monotonic()
        with self._lock:
            entry = self._entries.get(key)
            if entry and generation is not None and entry[0] == generation and now - entry[1] < self.ttl:
                return fast_copy(entry[2]) if copy else entry[2]
        value = compute()
        if generation is not None:
            with self._lock:
                if len(self._entries) >= self.max_entries:
                    self._entries.pop(next(iter(self._entries)))
                self._entries[key] = (generation, now, value)
        return fast_copy(value) if copy else value

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()


def fast_copy(value: Any) -> Any:
    """Copia dicts/listas/tuplas aninhados; o resto (texto, numero, data) e imutavel e e
    reaproveitado. Bem mais rapido que copy.deepcopy para os resultados dos services."""
    kind = type(value)
    if kind is dict:
        return {k: fast_copy(v) for k, v in value.items()}
    if kind is list:
        return [fast_copy(v) for v in value]
    if kind is tuple:
        return tuple(fast_copy(v) for v in value)
    return value
