from __future__ import annotations

import sqlite3

from documentos_empresa_app.database.connection import DatabaseManager

SQLITE_MAX_VARIABLE_NUMBER = 900


class BaseRepository:
    def __init__(self, db_manager: DatabaseManager) -> None:
        self.db_manager = db_manager

    def _fetchall(self, query: str, params: tuple = ()) -> list[dict]:
        with self.db_manager.connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def _fetchone(self, query: str, params: tuple = ()) -> dict | None:
        with self.db_manager.connect() as connection:
            row = connection.execute(query, params).fetchone()
        return dict(row) if row else None

    def _execute(self, query: str, params: tuple = ()) -> int:
        with self.db_manager.connect() as connection:
            cursor = connection.execute(query, params)
            return cursor.lastrowid

    def _executemany(self, query: str, params_list: list[tuple]) -> None:
        with self.db_manager.connect() as connection:
            connection.executemany(query, params_list)

    @staticmethod
    def _unique_values(values: list[int]) -> list[int]:
        unique_values: list[int] = []
        seen_values: set[int] = set()
        for value in values:
            if value in seen_values:
                continue
            seen_values.add(value)
            unique_values.append(value)
        return unique_values

    @staticmethod
    def _chunk_values(values: list[int], chunk_size: int = SQLITE_MAX_VARIABLE_NUMBER) -> list[list[int]]:
        return [values[index:index + chunk_size] for index in range(0, len(values), chunk_size)]


class EmpresaRepository(BaseRepository):
    def list_all(self, active_only: bool = False) -> list[dict]:
        query = """
            SELECT id, codigo_empresa, nome_empresa, meios_recebimento, email_contato, nome_contato,
                   observacao, diretorio_documentos, ativa, cobranca_inicio_dia, cobranca_fim_dia,
                   cobranca_alerta_dias, cnpj, nao_contatar_mala_direta
            FROM empresas
        """
        params: tuple = ()
        if active_only:
            query += " WHERE ativa = 1"
        query += " ORDER BY codigo_empresa, nome_empresa"
        return self._fetchall(query, params)

    def get_by_id(self, empresa_id: int) -> dict | None:
        return self._fetchone(
            """
            SELECT id, codigo_empresa, nome_empresa, meios_recebimento, email_contato, nome_contato,
                   observacao, diretorio_documentos, ativa, cobranca_inicio_dia, cobranca_fim_dia,
                   cobranca_alerta_dias, cnpj, nao_contatar_mala_direta
            FROM empresas
            WHERE id = ?
            """,
            (empresa_id,),
        )

    def get_by_code(self, codigo_empresa: int, active_only: bool = False) -> dict | None:
        query = """
            SELECT id, codigo_empresa, nome_empresa, meios_recebimento, email_contato, nome_contato,
                   observacao, diretorio_documentos, ativa, cobranca_inicio_dia, cobranca_fim_dia,
                   cobranca_alerta_dias, cnpj, nao_contatar_mala_direta
            FROM empresas
            WHERE codigo_empresa = ?
        """
        params: list = [codigo_empresa]
        if active_only:
            query += " AND ativa = 1"
        return self._fetchone(query, tuple(params))

    def list_by_ids(self, empresa_ids: list[int]) -> list[dict]:
        unique_ids = self._unique_values(empresa_ids)
        if not unique_ids:
            return []
        rows: list[dict] = []
        for chunk in self._chunk_values(unique_ids):
            placeholders = ", ".join("?" for _ in chunk)
            rows.extend(
                self._fetchall(
                    f"""
                    SELECT id, codigo_empresa, nome_empresa, meios_recebimento, email_contato, nome_contato,
                           observacao, diretorio_documentos, ativa, cobranca_inicio_dia, cobranca_fim_dia,
                           cobranca_alerta_dias, cnpj, nao_contatar_mala_direta
                    FROM empresas
                    WHERE id IN ({placeholders})
                    """,
                    tuple(chunk),
                )
            )
        rows.sort(key=lambda item: (item["codigo_empresa"], item["nome_empresa"].casefold()))
        return rows

    def create(
        self,
        codigo_empresa: int,
        nome_empresa: str,
        meios_recebimento: str | None = None,
        email_contato: str | None = None,
        nome_contato: str | None = None,
        observacao: str | None = None,
        cobranca_inicio_dia: int | None = None,
        cobranca_fim_dia: int | None = None,
        cobranca_alerta_dias: int | None = None,
        cnpj: str | None = None,
    ) -> int:
        return self._execute(
            """
            INSERT INTO empresas (
                codigo_empresa,
                nome_empresa,
                meios_recebimento,
                email_contato,
                nome_contato,
                observacao,
                cobranca_inicio_dia,
                cobranca_fim_dia,
                cobranca_alerta_dias,
                cnpj
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                codigo_empresa,
                nome_empresa,
                meios_recebimento,
                email_contato,
                nome_contato,
                observacao,
                cobranca_inicio_dia,
                cobranca_fim_dia,
                cobranca_alerta_dias,
                cnpj,
            ),
        )

    def update_name(self, empresa_id: int, nome_empresa: str) -> None:
        self._execute("UPDATE empresas SET nome_empresa = ? WHERE id = ?", (nome_empresa, empresa_id))

    def update_details(
        self,
        empresa_id: int,
        nome_empresa: str,
        meios_recebimento: str | None,
        email_contato: str | None,
        nome_contato: str | None,
        observacao: str | None,
        cobranca_inicio_dia: int | None,
        cobranca_fim_dia: int | None,
        cobranca_alerta_dias: int | None,
        cnpj: str | None = None,
    ) -> None:
        self._execute(
            """
            UPDATE empresas
            SET nome_empresa = ?, meios_recebimento = ?, email_contato = ?, nome_contato = ?, observacao = ?,
                cobranca_inicio_dia = ?, cobranca_fim_dia = ?, cobranca_alerta_dias = ?, cnpj = ?
            WHERE id = ?
            """,
            (
                nome_empresa,
                meios_recebimento,
                email_contato,
                nome_contato,
                observacao,
                cobranca_inicio_dia,
                cobranca_fim_dia,
                cobranca_alerta_dias,
                cnpj,
                empresa_id,
            ),
        )

    def update_directory(self, empresa_id: int, diretorio_documentos: str | None) -> None:
        self._execute(
            "UPDATE empresas SET diretorio_documentos = ? WHERE id = ?",
            (diretorio_documentos, empresa_id),
        )

    def update_cnpj(self, empresa_id: int, cnpj: str | None) -> None:
        self._execute(
            "UPDATE empresas SET cnpj = ? WHERE id = ?",
            (cnpj, empresa_id),
        )

    def get_by_cnpj(self, cnpj: str) -> dict | None:
        return self._fetchone(
            """
            SELECT id, codigo_empresa, nome_empresa, meios_recebimento, email_contato, nome_contato,
                   observacao, diretorio_documentos, ativa, cobranca_inicio_dia, cobranca_fim_dia,
                   cobranca_alerta_dias, cnpj, nao_contatar_mala_direta
            FROM empresas
            WHERE cnpj = ?
            """,
            (cnpj,),
        )

    def update_collection_settings(
        self,
        empresa_id: int,
        cobranca_inicio_dia: int | None,
        cobranca_fim_dia: int | None,
        cobranca_alerta_dias: int | None,
    ) -> None:
        self._execute(
            """
            UPDATE empresas
            SET cobranca_inicio_dia = ?, cobranca_fim_dia = ?, cobranca_alerta_dias = ?
            WHERE id = ?
            """,
            (cobranca_inicio_dia, cobranca_fim_dia, cobranca_alerta_dias, empresa_id),
        )

    def update_active(self, empresa_id: int, ativa: int) -> None:
        self._execute("UPDATE empresas SET ativa = ? WHERE id = ?", (ativa, empresa_id))

    def update_nao_contatar_mala_direta(self, empresa_id: int, nao_contatar: bool) -> None:
        self._execute(
            "UPDATE empresas SET nao_contatar_mala_direta = ? WHERE id = ?",
            (1 if nao_contatar else 0, empresa_id),
        )

    def clear_contact_info(self, empresa_id: int) -> None:
        self._execute(
            "UPDATE empresas SET email_contato = NULL, nome_contato = NULL WHERE id = ?",
            (empresa_id,),
        )

    def delete(self, empresa_id: int) -> None:
        self._execute("DELETE FROM empresas WHERE id = ?", (empresa_id,))


class DeliveryMethodRepository(BaseRepository):
    def list_all(self) -> list[dict]:
        return self._fetchall(
            """
            SELECT id, nome_meio
            FROM meios_recebimento_sistema
            ORDER BY nome_meio
            """
        )

    def get_by_id(self, method_id: int) -> dict | None:
        return self._fetchone(
            "SELECT id, nome_meio FROM meios_recebimento_sistema WHERE id = ?",
            (method_id,),
        )

    def get_by_name(self, nome_meio: str) -> dict | None:
        return self._fetchone(
            "SELECT id, nome_meio FROM meios_recebimento_sistema WHERE nome_meio = ?",
            (nome_meio,),
        )

    def create(self, nome_meio: str) -> int:
        return self._execute("INSERT INTO meios_recebimento_sistema (nome_meio) VALUES (?)", (nome_meio,))

    def update(self, method_id: int, nome_meio: str) -> None:
        self._execute("UPDATE meios_recebimento_sistema SET nome_meio = ? WHERE id = ?", (nome_meio, method_id))

    def delete(self, method_id: int) -> None:
        self._execute("DELETE FROM meios_recebimento_sistema WHERE id = ?", (method_id,))


class CollectionConfigRepository(BaseRepository):
    def get_settings(self) -> dict:
        row = self._fetchone(
            """
            SELECT
                id,
                inicio_cobranca_dia,
                encerramento_cobranca_dia,
                alerta_apos_dias
            FROM configuracoes_cobranca
            WHERE id = 1
            """
        )
        return row or {
            "id": 1,
            "inicio_cobranca_dia": 5,
            "encerramento_cobranca_dia": 12,
            "alerta_apos_dias": 4,
        }

    def upsert_settings(
        self,
        inicio_cobranca_dia: int,
        encerramento_cobranca_dia: int,
        alerta_apos_dias: int,
    ) -> None:
        self._execute(
            """
            INSERT INTO configuracoes_cobranca (
                id,
                inicio_cobranca_dia,
                encerramento_cobranca_dia,
                alerta_apos_dias
            )
            VALUES (1, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                inicio_cobranca_dia = excluded.inicio_cobranca_dia,
                encerramento_cobranca_dia = excluded.encerramento_cobranca_dia,
                alerta_apos_dias = excluded.alerta_apos_dias
            """,
            (inicio_cobranca_dia, encerramento_cobranca_dia, alerta_apos_dias),
        )


class TipoRepository(BaseRepository):
    def list_all(self) -> list[dict]:
        return self._fetchall(
            """
            SELECT id, nome_tipo, regra_ocorrencia
            FROM tipos_documento
            ORDER BY nome_tipo
            """
        )

    def get_by_id(self, tipo_id: int) -> dict | None:
        return self._fetchone(
            "SELECT id, nome_tipo, regra_ocorrencia FROM tipos_documento WHERE id = ?",
            (tipo_id,),
        )

    def get_by_name(self, nome_tipo: str) -> dict | None:
        return self._fetchone(
            "SELECT id, nome_tipo, regra_ocorrencia FROM tipos_documento WHERE nome_tipo = ?",
            (nome_tipo,),
        )

    def create(self, nome_tipo: str, regra_ocorrencia: str) -> int:
        return self._execute(
            "INSERT INTO tipos_documento (nome_tipo, regra_ocorrencia) VALUES (?, ?)",
            (nome_tipo, regra_ocorrencia),
        )

    def update(self, tipo_id: int, nome_tipo: str, regra_ocorrencia: str) -> None:
        self._execute(
            "UPDATE tipos_documento SET nome_tipo = ?, regra_ocorrencia = ? WHERE id = ?",
            (nome_tipo, regra_ocorrencia, tipo_id),
        )

    def delete(self, tipo_id: int) -> None:
        self._execute("DELETE FROM tipos_documento WHERE id = ?", (tipo_id,))

    def is_in_use(self, tipo_id: int) -> bool:
        row = self._fetchone(
            "SELECT COUNT(*) AS total FROM documentos_empresa WHERE tipo_documento_id = ?",
            (tipo_id,),
        )
        return bool(row and row["total"])


class UsuarioRepository(BaseRepository):
    def list_all(self) -> list[dict]:
        return self._fetchall(
            """
            SELECT id, username, tipo_usuario, ativa, deve_trocar_senha, criado_em
            FROM usuarios
            ORDER BY username
            """
        )

    def get_by_id(self, user_id: int, include_password: bool = False) -> dict | None:
        fields = "id, username, tipo_usuario, ativa, deve_trocar_senha, criado_em"
        if include_password:
            fields += ", senha_hash"
        return self._fetchone(f"SELECT {fields} FROM usuarios WHERE id = ?", (user_id,))

    def get_by_username(self, username: str, include_password: bool = False) -> dict | None:
        fields = "id, username, tipo_usuario, ativa, deve_trocar_senha, criado_em"
        if include_password:
            fields += ", senha_hash"
        return self._fetchone(f"SELECT {fields} FROM usuarios WHERE username = ?", (username,))

    def create(self, username: str, senha_hash: str, tipo_usuario: str, ativa: int = 1) -> int:
        return self._execute(
            """
            INSERT INTO usuarios (username, senha_hash, tipo_usuario, ativa)
            VALUES (?, ?, ?, ?)
            """,
            (username, senha_hash, tipo_usuario, ativa),
        )

    def update(self, user_id: int, username: str, tipo_usuario: str, ativa: int) -> None:
        self._execute(
            """
            UPDATE usuarios
            SET username = ?, tipo_usuario = ?, ativa = ?
            WHERE id = ?
            """,
            (username, tipo_usuario, ativa, user_id),
        )

    def update_password(self, user_id: int, senha_hash: str) -> None:
        # Trocar a senha sempre limpa a exigencia de troca obrigatoria, seja a troca
        # feita pelo proprio usuario ou por um admin resetando a senha de outro.
        self._execute(
            "UPDATE usuarios SET senha_hash = ?, deve_trocar_senha = 0 WHERE id = ?",
            (senha_hash, user_id),
        )

    def count_admins(self, active_only: bool = True) -> int:
        query = "SELECT COUNT(*) AS total FROM usuarios WHERE tipo_usuario = 'admin'"
        if active_only:
            query += " AND ativa = 1"
        row = self._fetchone(query)
        return int(row["total"]) if row else 0


class RememberedSessionRepository(BaseRepository):
    def get_by_selector(self, selector: str) -> dict | None:
        return self._fetchone(
            """
            SELECT id, usuario_id, selector, token_hash, criado_em, ultimo_uso_em
            FROM sessoes_lembradas
            WHERE selector = ?
            """,
            (selector,),
        )

    def create(self, usuario_id: int, selector: str, token_hash: str) -> int:
        return self._execute(
            """
            INSERT INTO sessoes_lembradas (usuario_id, selector, token_hash)
            VALUES (?, ?, ?)
            """,
            (usuario_id, selector, token_hash),
        )

    def touch(self, session_id: int) -> None:
        self._execute(
            """
            UPDATE sessoes_lembradas
            SET ultimo_uso_em = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (session_id,),
        )

    def delete_by_selector(self, selector: str) -> None:
        self._execute("DELETE FROM sessoes_lembradas WHERE selector = ?", (selector,))

    def delete_by_user(self, usuario_id: int) -> None:
        self._execute("DELETE FROM sessoes_lembradas WHERE usuario_id = ?", (usuario_id,))


class LogRepository(BaseRepository):
    def create(
        self,
        usuario_id: int | None,
        acao: str,
        entidade: str,
        entidade_id: int | None,
        empresa_id: int | None,
        empresa_nome: str | None,
        periodo_ano: int | None,
        periodo_mes: int | None,
        descricao: str,
        data_hora: str,
    ) -> int:
        return self._execute(
            """
            INSERT INTO logs (
                usuario_id,
                acao,
                entidade,
                entidade_id,
                empresa_id,
                empresa_nome,
                periodo_ano,
                periodo_mes,
                descricao,
                data_hora
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                usuario_id,
                acao,
                entidade,
                entidade_id,
                empresa_id,
                empresa_nome,
                periodo_ano,
                periodo_mes,
                descricao,
                data_hora,
            ),
        )

    def list_recent(
        self,
        limit: int = 500,
        empresa_id: int | None = None,
        periodo_ano: int | None = None,
        periodo_mes: int | None = None,
    ) -> list[dict]:
        filters = []
        params: list = []
        if empresa_id is not None:
            filters.append("l.empresa_id = ?")
            params.append(empresa_id)
        if periodo_ano is not None:
            filters.append("l.periodo_ano = ?")
            params.append(periodo_ano)
        if periodo_mes is not None:
            filters.append("l.periodo_mes = ?")
            params.append(periodo_mes)

        query = """
            SELECT
                l.id,
                l.usuario_id,
                l.acao,
                l.entidade,
                l.entidade_id,
                l.empresa_id,
                COALESCE(l.empresa_nome, e.nome_empresa, '') AS empresa_nome,
                l.periodo_ano,
                l.periodo_mes,
                l.descricao,
                l.data_hora,
                COALESCE(u.username, 'Sistema') AS username
            FROM logs l
            LEFT JOIN usuarios u ON u.id = l.usuario_id
            LEFT JOIN empresas e ON e.id = l.empresa_id
        """
        if filters:
            query += " WHERE " + " AND ".join(filters)
        query += " ORDER BY l.data_hora DESC, l.id DESC LIMIT ?"
        params.append(limit)
        return self._fetchall(query, tuple(params))

    def list_logged_companies(self) -> list[dict]:
        return self._fetchall(
            """
            SELECT
                l.empresa_id AS id,
                COALESCE(MAX(l.empresa_nome), MAX(e.nome_empresa), 'Empresa removida') AS nome_empresa
            FROM logs l
            LEFT JOIN empresas e ON e.id = l.empresa_id
            WHERE l.empresa_id IS NOT NULL
            GROUP BY l.empresa_id
            ORDER BY nome_empresa
            """
        )

    def list_log_years(self) -> list[int]:
        rows = self._fetchall(
            """
            SELECT DISTINCT periodo_ano
            FROM logs
            WHERE periodo_ano IS NOT NULL
            ORDER BY periodo_ano
            """
        )
        return [row["periodo_ano"] for row in rows]

    def list_log_months_by_year(self, ano: int) -> list[int]:
        rows = self._fetchall(
            """
            SELECT DISTINCT periodo_mes
            FROM logs
            WHERE periodo_ano = ?
              AND periodo_mes IS NOT NULL
            ORDER BY periodo_mes
            """,
            (ano,),
        )
        return [row["periodo_mes"] for row in rows]

    def count_older_than(self, cutoff_iso: str) -> int:
        row = self._fetchone("SELECT COUNT(*) AS total FROM logs WHERE data_hora < ?", (cutoff_iso,))
        return int(row["total"]) if row else 0

    def delete_older_than(self, cutoff_iso: str) -> int:
        count = self.count_older_than(cutoff_iso)
        self._execute("DELETE FROM logs WHERE data_hora < ?", (cutoff_iso,))
        return count


class DocumentoRepository(BaseRepository):
    def list_all(self) -> list[dict]:
        return self._fetchall(
            """
            SELECT id, empresa_id, tipo_documento_id, meios_recebimento, nome_documento
            FROM documentos_empresa
            ORDER BY empresa_id, nome_documento
            """
        )

    def list_by_company(self, empresa_id: int) -> list[dict]:
        return self._fetchall(
            """
            SELECT
                d.id,
                d.empresa_id,
                d.tipo_documento_id,
                d.meios_recebimento,
                d.nome_documento,
                t.nome_tipo,
                t.regra_ocorrencia
            FROM documentos_empresa d
            INNER JOIN tipos_documento t ON t.id = d.tipo_documento_id
            WHERE d.empresa_id = ?
            ORDER BY t.nome_tipo, d.nome_documento
            """,
            (empresa_id,),
        )

    def list_by_company_ids(self, empresa_ids: list[int]) -> list[dict]:
        unique_ids = self._unique_values(empresa_ids)
        if not unique_ids:
            return []
        rows: list[dict] = []
        for chunk in self._chunk_values(unique_ids):
            placeholders = ", ".join("?" for _ in chunk)
            rows.extend(
                self._fetchall(
                    f"""
                    SELECT
                        d.id,
                        d.empresa_id,
                        d.tipo_documento_id,
                        d.meios_recebimento,
                        d.nome_documento,
                        t.nome_tipo,
                        t.regra_ocorrencia
                    FROM documentos_empresa d
                    INNER JOIN tipos_documento t ON t.id = d.tipo_documento_id
                    WHERE d.empresa_id IN ({placeholders})
                    """,
                    tuple(chunk),
                )
            )
        rows.sort(key=lambda item: (item["empresa_id"], item["nome_tipo"].casefold(), item["nome_documento"].casefold()))
        return rows

    def get_by_id(self, documento_id: int) -> dict | None:
        return self._fetchone(
            """
            SELECT
                d.id,
                d.empresa_id,
                d.tipo_documento_id,
                d.meios_recebimento,
                d.nome_documento,
                t.nome_tipo,
                t.regra_ocorrencia
            FROM documentos_empresa d
            INNER JOIN tipos_documento t ON t.id = d.tipo_documento_id
            WHERE d.id = ?
            """,
            (documento_id,),
        )

    def list_by_ids(self, documento_ids: list[int]) -> list[dict]:
        unique_ids = self._unique_values(documento_ids)
        if not unique_ids:
            return []
        rows: list[dict] = []
        for chunk in self._chunk_values(unique_ids):
            placeholders = ", ".join("?" for _ in chunk)
            rows.extend(
                self._fetchall(
                    f"""
                    SELECT
                        d.id,
                        d.empresa_id,
                        d.tipo_documento_id,
                        d.meios_recebimento,
                        d.nome_documento,
                        t.nome_tipo,
                        t.regra_ocorrencia
                    FROM documentos_empresa d
                    INNER JOIN tipos_documento t ON t.id = d.tipo_documento_id
                    WHERE d.id IN ({placeholders})
                    """,
                    tuple(chunk),
                )
            )
        position_by_id = {documento_id: index for index, documento_id in enumerate(unique_ids)}
        rows.sort(key=lambda item: position_by_id.get(item["id"], len(unique_ids)))
        return rows

    def list_system_names(self, tipo_documento_id: int | None = None, search: str | None = None) -> list[dict]:
        filters: list[str] = []
        params: list = []

        if tipo_documento_id is not None:
            filters.append("n.tipo_documento_id = ?")
            params.append(tipo_documento_id)

        normalized_search = str(search or "").strip()
        if normalized_search:
            filters.append("n.nome_documento LIKE ? COLLATE NOCASE")
            params.append(f"%{normalized_search}%")

        query = """
            SELECT
                n.id,
                n.tipo_documento_id,
                n.nome_documento,
                t.nome_tipo
            FROM nomes_documento_padrao_sistema n
            INNER JOIN tipos_documento t ON t.id = n.tipo_documento_id
        """
        if filters:
            query += " WHERE " + " AND ".join(filters)
        query += " ORDER BY t.nome_tipo, n.nome_documento"
        return self._fetchall(query, tuple(params))

    def list_distinct_system_names(self, tipo_documento_id: int | None = None, search: str | None = None) -> list[str]:
        filters: list[str] = []
        params: list = []

        if tipo_documento_id is not None:
            filters.append("tipo_documento_id = ?")
            params.append(tipo_documento_id)

        normalized_search = str(search or "").strip()
        if normalized_search:
            filters.append("nome_documento LIKE ? COLLATE NOCASE")
            params.append(f"%{normalized_search}%")

        query = """
            SELECT DISTINCT nome_documento
            FROM nomes_documento_padrao_sistema
        """
        if filters:
            query += " WHERE " + " AND ".join(filters)
        query += " ORDER BY nome_documento"

        rows = self._fetchall(query, tuple(params))
        return [row["nome_documento"] for row in rows]

    def get_system_name_by_id(self, name_id: int) -> dict | None:
        return self._fetchone(
            """
            SELECT
                n.id,
                n.tipo_documento_id,
                n.nome_documento,
                t.nome_tipo
            FROM nomes_documento_padrao_sistema n
            INNER JOIN tipos_documento t ON t.id = n.tipo_documento_id
            WHERE n.id = ?
            """,
            (name_id,),
        )

    def find_duplicate_system_name(
        self,
        tipo_documento_id: int,
        nome_documento: str,
        ignore_id: int | None = None,
    ) -> dict | None:
        query = """
            SELECT id
            FROM nomes_documento_padrao_sistema
            WHERE tipo_documento_id = ?
              AND nome_documento = ?
        """
        params: list = [tipo_documento_id, nome_documento]
        if ignore_id is not None:
            query += " AND id <> ?"
            params.append(ignore_id)
        return self._fetchone(query, tuple(params))

    def create_system_name(self, tipo_documento_id: int, nome_documento: str) -> int:
        return self._execute(
            """
            INSERT INTO nomes_documento_padrao_sistema (tipo_documento_id, nome_documento)
            VALUES (?, ?)
            """,
            (tipo_documento_id, nome_documento),
        )

    def update_system_name(self, name_id: int, tipo_documento_id: int, nome_documento: str) -> None:
        self._execute(
            """
            UPDATE nomes_documento_padrao_sistema
            SET tipo_documento_id = ?, nome_documento = ?
            WHERE id = ?
            """,
            (tipo_documento_id, nome_documento, name_id),
        )

    def delete_system_name(self, name_id: int) -> None:
        self._execute("DELETE FROM nomes_documento_padrao_sistema WHERE id = ?", (name_id,))

    def list_distinct_names(self, tipo_documento_id: int | None = None, search: str | None = None) -> list[str]:
        filters: list[str] = []
        params: list = []

        if tipo_documento_id is not None:
            filters.append("tipo_documento_id = ?")
            params.append(tipo_documento_id)

        normalized_search = str(search or "").strip()
        if normalized_search:
            filters.append("nome_documento LIKE ? COLLATE NOCASE")
            params.append(f"%{normalized_search}%")

        query = """
            SELECT DISTINCT nome_documento
            FROM documentos_empresa
        """
        if filters:
            query += " WHERE " + " AND ".join(filters)
        query += " ORDER BY nome_documento"

        rows = self._fetchall(query, tuple(params))
        return [row["nome_documento"] for row in rows]

    def find_duplicate(
        self,
        empresa_id: int,
        tipo_documento_id: int,
        nome_documento: str,
        ignore_id: int | None = None,
    ) -> dict | None:
        query = """
            SELECT id
            FROM documentos_empresa
            WHERE empresa_id = ?
              AND tipo_documento_id = ?
              AND nome_documento = ?
        """
        params: list = [empresa_id, tipo_documento_id, nome_documento]
        if ignore_id is not None:
            query += " AND id <> ?"
            params.append(ignore_id)
        return self._fetchone(query, tuple(params))

    def create(
        self,
        empresa_id: int,
        tipo_documento_id: int,
        meios_recebimento: str | None,
        nome_documento: str,
    ) -> int:
        return self._execute(
            """
            INSERT INTO documentos_empresa (empresa_id, tipo_documento_id, meios_recebimento, nome_documento)
            VALUES (?, ?, ?, ?)
            """,
            (empresa_id, tipo_documento_id, meios_recebimento, nome_documento),
        )

    def update(
        self,
        documento_id: int,
        tipo_documento_id: int,
        meios_recebimento: str | None,
        nome_documento: str,
    ) -> None:
        self._execute(
            """
            UPDATE documentos_empresa
            SET tipo_documento_id = ?, meios_recebimento = ?, nome_documento = ?
            WHERE id = ?
            """,
            (tipo_documento_id, meios_recebimento, nome_documento, documento_id),
        )

    def update_delivery_methods(self, documento_id: int, meios_recebimento: str | None) -> None:
        self._execute(
            "UPDATE documentos_empresa SET meios_recebimento = ? WHERE id = ?",
            (meios_recebimento, documento_id),
        )

    def delete(self, documento_id: int) -> None:
        self._execute("DELETE FROM documentos_empresa WHERE id = ?", (documento_id,))

    def delete_many(self, documento_ids: list[int]) -> None:
        unique_ids = self._unique_values(documento_ids)
        if not unique_ids:
            return
        for chunk in self._chunk_values(unique_ids):
            placeholders = ", ".join("?" for _ in chunk)
            self._execute(f"DELETE FROM documentos_empresa WHERE id IN ({placeholders})", tuple(chunk))


class PeriodoRepository(BaseRepository):
    def list_all(self) -> list[dict]:
        return self._fetchall(
            """
            SELECT id, ano, mes
            FROM periodos
            ORDER BY ano, mes
            """
        )

    def get_by_id(self, periodo_id: int) -> dict | None:
        return self._fetchone("SELECT id, ano, mes FROM periodos WHERE id = ?", (periodo_id,))

    def get_by_year_month(self, ano: int, mes: int) -> dict | None:
        return self._fetchone("SELECT id, ano, mes FROM periodos WHERE ano = ? AND mes = ?", (ano, mes))

    def create(self, ano: int, mes: int) -> int:
        return self._execute("INSERT INTO periodos (ano, mes) VALUES (?, ?)", (ano, mes))

    def exists(self, ano: int, mes: int) -> bool:
        row = self._fetchone("SELECT id FROM periodos WHERE ano = ? AND mes = ?", (ano, mes))
        return row is not None

    def list_years(self) -> list[int]:
        rows = self._fetchall("SELECT DISTINCT ano FROM periodos ORDER BY ano")
        return [row["ano"] for row in rows]

    def list_by_year(self, ano: int) -> list[dict]:
        return self._fetchall(
            "SELECT id, ano, mes FROM periodos WHERE ano = ? ORDER BY mes",
            (ano,),
        )

    def list_between(self, start_ano: int, start_mes: int, end_ano: int, end_mes: int) -> list[dict]:
        return self._fetchall(
            """
            SELECT id, ano, mes
            FROM periodos
            WHERE (ano > ? OR (ano = ? AND mes >= ?))
              AND (ano < ? OR (ano = ? AND mes <= ?))
            ORDER BY ano, mes
            """,
            (start_ano, start_ano, start_mes, end_ano, end_ano, end_mes),
        )

    def delete_year(self, ano: int) -> int:
        with self.db_manager.connect() as connection:
            cursor = connection.execute("DELETE FROM periodos WHERE ano = ?", (ano,))
            return cursor.rowcount


class StatusRepository(BaseRepository):
    def get_by_document_and_period(self, documento_empresa_id: int, periodo_id: int) -> dict | None:
        return self._fetchone(
            """
            SELECT
                s.id,
                s.documento_empresa_id,
                s.periodo_id,
                s.status,
                s.updated_by_user_id,
                s.updated_at,
                COALESCE(u.username, 'Sistema') AS updated_by_username
            FROM status_documento_mensal s
            LEFT JOIN usuarios u ON u.id = s.updated_by_user_id
            WHERE s.documento_empresa_id = ? AND s.periodo_id = ?
            """,
            (documento_empresa_id, periodo_id),
        )

    def upsert(
        self,
        documento_empresa_id: int,
        periodo_id: int,
        status: str | None,
        updated_by_user_id: int | None,
    ) -> None:
        self._execute(
            """
            INSERT INTO status_documento_mensal (
                documento_empresa_id,
                periodo_id,
                status,
                updated_by_user_id,
                updated_at
            )
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(documento_empresa_id, periodo_id)
            DO UPDATE SET
                status = excluded.status,
                updated_by_user_id = excluded.updated_by_user_id,
                updated_at = CURRENT_TIMESTAMP
            """,
            (documento_empresa_id, periodo_id, status, updated_by_user_id),
        )

    def list_for_documents_and_periods(self, documento_ids: list[int], periodo_ids: list[int]) -> list[dict]:
        unique_document_ids = self._unique_values(documento_ids)
        unique_period_ids = self._unique_values(periodo_ids)
        if not unique_document_ids or not unique_period_ids:
            return []
        max_document_chunk = max(SQLITE_MAX_VARIABLE_NUMBER - len(unique_period_ids), 1)
        period_placeholders = ", ".join("?" for _ in unique_period_ids)
        rows: list[dict] = []
        for doc_chunk in self._chunk_values(unique_document_ids, max_document_chunk):
            doc_placeholders = ", ".join("?" for _ in doc_chunk)
            params = tuple(doc_chunk + unique_period_ids)
            rows.extend(
                self._fetchall(
                    f"""
                    SELECT
                        s.id,
                        s.documento_empresa_id,
                        s.periodo_id,
                        s.status,
                        s.updated_by_user_id,
                        s.updated_at,
                        COALESCE(u.username, 'Sistema') AS updated_by_username
                    FROM status_documento_mensal s
                    LEFT JOIN usuarios u ON u.id = s.updated_by_user_id
                    WHERE s.documento_empresa_id IN ({doc_placeholders})
                      AND s.periodo_id IN ({period_placeholders})
                    """,
                    params,
                )
            )
        rows.sort(key=lambda item: (item["documento_empresa_id"], item["periodo_id"]))
        return rows

    def list_future_statuses(self, documento_empresa_id: int, ano: int, mes: int) -> list[dict]:
        return self._fetchall(
            """
            SELECT
                s.id,
                s.documento_empresa_id,
                s.periodo_id,
                s.status,
                p.ano,
                p.mes
            FROM status_documento_mensal s
            INNER JOIN periodos p ON p.id = s.periodo_id
            WHERE s.documento_empresa_id = ?
              AND (p.ano * 100 + p.mes) > (? * 100 + ?)
            ORDER BY p.ano, p.mes
            """,
            (documento_empresa_id, ano, mes),
        )

    def get_earliest_closure(self, documento_empresa_id: int) -> dict | None:
        return self._fetchone(
            """
            SELECT
                s.id,
                s.documento_empresa_id,
                s.periodo_id,
                p.ano,
                p.mes
            FROM status_documento_mensal s
            INNER JOIN periodos p ON p.id = s.periodo_id
            WHERE s.documento_empresa_id = ?
              AND s.status = 'Encerrado'
            ORDER BY p.ano, p.mes
            LIMIT 1
            """,
            (documento_empresa_id,),
        )

    def list_earliest_closures(self, documento_ids: list[int]) -> list[dict]:
        unique_ids = self._unique_values(documento_ids)
        if not unique_ids:
            return []
        rows: list[dict] = []
        for chunk in self._chunk_values(unique_ids):
            placeholders = ", ".join("?" for _ in chunk)
            rows.extend(
                self._fetchall(
                    f"""
                    SELECT
                        s.documento_empresa_id,
                        MIN(p.ano * 100 + p.mes) AS fechamento
                    FROM status_documento_mensal s
                    INNER JOIN periodos p ON p.id = s.periodo_id
                    WHERE s.documento_empresa_id IN ({placeholders})
                      AND s.status = 'Encerrado'
                    GROUP BY s.documento_empresa_id
                    """,
                    tuple(chunk),
                )
            )
        rows.sort(key=lambda item: item["documento_empresa_id"])
        return rows

    def list_closures_for_documents(self, documento_ids: list[int]) -> list[dict]:
        unique_ids = self._unique_values(documento_ids)
        if not unique_ids:
            return []
        rows: list[dict] = []
        for chunk in self._chunk_values(unique_ids):
            placeholders = ", ".join("?" for _ in chunk)
            rows.extend(
                self._fetchall(
                    f"""
                    SELECT
                        s.documento_empresa_id,
                        p.ano,
                        p.mes
                    FROM status_documento_mensal s
                    INNER JOIN periodos p ON p.id = s.periodo_id
                    WHERE s.documento_empresa_id IN ({placeholders})
                      AND s.status = 'Encerrado'
                    """,
                    tuple(chunk),
                )
            )
        rows.sort(key=lambda item: (item["documento_empresa_id"], item["ano"], item["mes"]))
        return rows

    def delete_future_statuses(self, documento_empresa_id: int, ano: int, mes: int) -> None:
        self._execute(
            """
            DELETE FROM status_documento_mensal
            WHERE documento_empresa_id = ?
              AND periodo_id IN (
                  SELECT id FROM periodos
                  WHERE (ano * 100 + mes) > (? * 100 + ?)
              )
            """,
            (documento_empresa_id, ano, mes),
        )


class DocumentoPendenteRevisaoRepository(BaseRepository):
    def create(
        self,
        caminho_arquivo_original: str,
        nome_arquivo: str,
        cnpj_extraido: str | None,
        empresa_sugerida_id: int | None,
        empresa_sugerida_nome: str | None,
        tipo_documento_sugerido: str | None,
        confianca_sugestao: float | None,
        origem_sugestao: str,
        motivo: str | None,
    ) -> int:
        return self._execute(
            """
            INSERT INTO documentos_pendentes_revisao (
                caminho_arquivo_original,
                nome_arquivo,
                cnpj_extraido,
                empresa_sugerida_id,
                empresa_sugerida_nome,
                tipo_documento_sugerido,
                confianca_sugestao,
                origem_sugestao,
                motivo
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                caminho_arquivo_original,
                nome_arquivo,
                cnpj_extraido,
                empresa_sugerida_id,
                empresa_sugerida_nome,
                tipo_documento_sugerido,
                confianca_sugestao,
                origem_sugestao,
                motivo,
            ),
        )

    def get_by_original_path(self, caminho_arquivo_original: str) -> dict | None:
        return self._fetchone(
            """
            SELECT id, caminho_arquivo_original, nome_arquivo, cnpj_extraido, empresa_sugerida_id,
                   empresa_sugerida_nome, tipo_documento_sugerido, confianca_sugestao, origem_sugestao,
                   status, motivo, criado_em, resolvido_em, resolvido_por_usuario_id, empresa_confirmada_id
            FROM documentos_pendentes_revisao
            WHERE caminho_arquivo_original = ? AND status = 'pendente'
            """,
            (caminho_arquivo_original,),
        )

    def get_by_id(self, pendente_id: int) -> dict | None:
        return self._fetchone(
            """
            SELECT id, caminho_arquivo_original, nome_arquivo, cnpj_extraido, empresa_sugerida_id,
                   empresa_sugerida_nome, tipo_documento_sugerido, confianca_sugestao, origem_sugestao,
                   status, motivo, criado_em, resolvido_em, resolvido_por_usuario_id, empresa_confirmada_id
            FROM documentos_pendentes_revisao
            WHERE id = ?
            """,
            (pendente_id,),
        )

    def list_pendentes(self) -> list[dict]:
        return self._fetchall(
            """
            SELECT id, caminho_arquivo_original, nome_arquivo, cnpj_extraido, empresa_sugerida_id,
                   empresa_sugerida_nome, tipo_documento_sugerido, confianca_sugestao, origem_sugestao,
                   status, motivo, criado_em, resolvido_em, resolvido_por_usuario_id, empresa_confirmada_id
            FROM documentos_pendentes_revisao
            WHERE status = 'pendente'
            ORDER BY criado_em DESC
            """
        )

    def mark_resolved(self, pendente_id: int, empresa_confirmada_id: int, resolvido_por_usuario_id: int | None) -> None:
        self._execute(
            """
            UPDATE documentos_pendentes_revisao
            SET status = 'resolvido',
                empresa_confirmada_id = ?,
                resolvido_por_usuario_id = ?,
                resolvido_em = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (empresa_confirmada_id, resolvido_por_usuario_id, pendente_id),
        )

    def mark_ignored(self, pendente_id: int) -> None:
        self._execute(
            """
            UPDATE documentos_pendentes_revisao
            SET status = 'ignorado', resolvido_em = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (pendente_id,),
        )


class UserPreferenceRepository(BaseRepository):
    def get_pasta_entrada(self, usuario_id: int) -> str | None:
        row = self._fetchone(
            "SELECT pasta_entrada FROM usuario_preferencias WHERE usuario_id = ?",
            (usuario_id,),
        )
        return row["pasta_entrada"] if row else None

    def set_pasta_entrada(self, usuario_id: int, pasta_entrada: str | None) -> None:
        self._execute(
            """
            INSERT INTO usuario_preferencias (usuario_id, pasta_entrada)
            VALUES (?, ?)
            ON CONFLICT(usuario_id) DO UPDATE SET pasta_entrada = excluded.pasta_entrada
            """,
            (usuario_id, pasta_entrada),
        )

    def count_all(self) -> int:
        row = self._fetchone("SELECT COUNT(*) AS total FROM usuario_preferencias")
        return int(row["total"]) if row else 0
