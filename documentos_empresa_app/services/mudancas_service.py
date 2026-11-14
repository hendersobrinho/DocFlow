"""Percebe quando outro programa (o Claude pelo MCP, ou outro computador) gravou no banco, para a
tela avisar que ha novidades sem precisar fechar e abrir o DocFlow.

A "assinatura" e um retrato barato das tabelas que mudam no dia a dia (ultimo id, ultima
alteracao, contagens). Se ela mudou e nao foi este programa que escreveu, ha novidade."""

from __future__ import annotations

ASSINATURA_SQL = """
SELECT
    (SELECT max(id) FROM logs) AS logs,
    (SELECT max(updated_at) FROM status_documento_mensal) AS status,
    (SELECT count(*) FROM status_documento_mensal) AS status_total,
    (SELECT max(id) FROM verificacoes) AS verificacoes,
    (SELECT max(id) FROM cobrancas) AS cobrancas,
    (SELECT max(id) FROM rodadas) AS rodadas,
    (SELECT max(finalizada_em) FROM rodadas) AS rodadas_fim,
    (SELECT max(id) FROM rodada_ocorrencias) AS ocorrencias,
    (SELECT max(id) FROM situacao_eventos) AS situacoes,
    (SELECT max(id) FROM envios_registrados) AS envios,
    (SELECT count(*) FROM empresas) AS empresas,
    (SELECT count(*) FROM documentos_empresa) AS documentos,
    (SELECT max(id) FROM revisoes_socios) AS revisoes_socios,
    (SELECT max(atualizado_em) FROM alertas_socios) AS alertas_socios,
    (SELECT count(*) FROM socios) AS socios
"""


class MudancasService:
    def __init__(self, db_manager) -> None:
        self.db_manager = db_manager
        self._base: tuple | None = None
        self._geracao: int | None = None

    def assinatura(self) -> tuple | None:
        """None quando nao deu para ler (sem conexao, banco ocupado): ai nao se avisa nada."""
        if getattr(self.db_manager, "_active_connection", None) is not None:
            return None  # outra leitura/escrita em andamento: tenta na proxima
        try:
            with self.db_manager.connect() as connection:
                linha = connection.execute(ASSINATURA_SQL).fetchone()
        except Exception:  # noqa: BLE001 - verificar novidade nunca pode derrubar a tela
            return None
        return tuple(str(valor) for valor in dict(linha).values()) if linha else None

    def marcar_visto(self) -> None:
        """A tela acabou de recarregar: o que esta no banco agora ja foi visto."""
        self._base = self.assinatura()
        self._geracao = getattr(self.db_manager, "write_generation", None)

    def ha_novidades(self) -> bool:
        """True se alguem de fora gravou desde a ultima vez que a tela recarregou."""
        atual = self.assinatura()
        if atual is None:
            return False
        geracao = getattr(self.db_manager, "write_generation", None)
        if self._base is None or geracao != self._geracao:
            # Primeira olhada, ou foi este programa que escreveu (a tela ja se atualizou).
            self._base, self._geracao = atual, geracao
            return False
        return atual != self._base

    def invalidar_caches(self) -> None:
        """Faz os caches de leitura dos services (ResultCache) lerem o banco de novo."""
        if hasattr(self.db_manager, "mark_written"):
            self.db_manager.mark_written()
