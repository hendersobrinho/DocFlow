from __future__ import annotations

from documentos_empresa_app.database.connection import DatabaseManager
from documentos_empresa_app.database.schema import UTC_NOW_FUNCTION

# Limite de parametros por consulta nas buscas "IN (...)" - o PostgreSQL aceita bem mais,
# mas lotes menores mantem as queries curtas.
MAX_QUERY_PARAMETERS = 900


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
        """Executa um comando de escrita e devolve a quantidade de linhas afetadas."""
        with self.db_manager.connect() as connection:
            cursor = connection.execute(query, params)
            return cursor.rowcount

    def _insert(self, query: str, params: tuple = ()) -> int:
        """Executa um INSERT e devolve o id gerado para a nova linha."""
        with self.db_manager.connect() as connection:
            row = connection.execute(f"{query.rstrip()} RETURNING id", params).fetchone()
            return int(row["id"])

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
    def _chunk_values(values: list[int], chunk_size: int = MAX_QUERY_PARAMETERS) -> list[list[int]]:
        return [values[index:index + chunk_size] for index in range(0, len(values), chunk_size)]


class EmpresaRepository(BaseRepository):
    def ids_com_pendencia_no_meio(self, meio: str, ano: int, mes: int) -> set[int] | None:
        """Empresas com documento ainda Pendente nessa competencia, entre os que chegam pelo meio.
        None se a competencia nao existe no DocFlow (nao ha como saber o que esta pendente)."""
        if not self._fetchall("SELECT 1 FROM periodos WHERE ano = ? AND mes = ?", (ano, mes)):
            return None
        rows = self._fetchall(
            """
            SELECT DISTINCT d.empresa_id
            FROM documentos_empresa d
            INNER JOIN status_documento_mensal s ON s.documento_empresa_id = d.id
            INNER JOIN periodos p ON p.id = s.periodo_id
            WHERE p.ano = ? AND p.mes = ? AND s.status = 'Pendente' AND d.meios_recebimento ILIKE ?
            """,
            (ano, mes, f"%{meio}%"),
        )
        return {int(row["empresa_id"]) for row in rows}

    def ids_com_meio_recebimento(self, meio: str) -> set[int]:
        """Empresas com o meio marcado em algum documento (o meio de recebimento fica nos documentos)."""
        rows = self._fetchall(
            "SELECT DISTINCT d.empresa_id AS id FROM documentos_empresa d WHERE d.meios_recebimento ILIKE ?",
            (f"%{meio}%",),
        )
        return {int(row["id"]) for row in rows}

    def list_all(self, active_only: bool = False) -> list[dict]:
        query = """
            SELECT id, codigo_empresa, nome_empresa, meios_recebimento, email_contato, nome_contato,
                   observacao, diretorio_documentos, ativa, cobranca_inicio_dia, cobranca_fim_dia,
                   cobranca_alerta_dias, cnpj, nao_contatar_mala_direta,
                   canais_recebimento, emails_origem_documentos, instrucoes_busca, whatsapp,
                   whatsapp_envios, whatsapp_grupo
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
                   cobranca_alerta_dias, cnpj, nao_contatar_mala_direta,
                   canais_recebimento, emails_origem_documentos, instrucoes_busca, whatsapp,
                   whatsapp_envios, whatsapp_grupo
            FROM empresas
            WHERE id = ?
            """,
            (empresa_id,),
        )

    def get_by_code(self, codigo_empresa: int, active_only: bool = False) -> dict | None:
        query = """
            SELECT id, codigo_empresa, nome_empresa, meios_recebimento, email_contato, nome_contato,
                   observacao, diretorio_documentos, ativa, cobranca_inicio_dia, cobranca_fim_dia,
                   cobranca_alerta_dias, cnpj, nao_contatar_mala_direta,
                   canais_recebimento, emails_origem_documentos, instrucoes_busca, whatsapp,
                   whatsapp_envios, whatsapp_grupo
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
                           cobranca_alerta_dias, cnpj, nao_contatar_mala_direta,
                   canais_recebimento, emails_origem_documentos, instrucoes_busca, whatsapp,
                   whatsapp_envios, whatsapp_grupo
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
        return self._insert(
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

    def update_reception(
        self,
        empresa_id: int,
        canais_recebimento: str | None,
        emails_origem_documentos: str | None,
        instrucoes_busca: str | None,
    ) -> None:
        self._execute(
            """
            UPDATE empresas
            SET canais_recebimento = ?, emails_origem_documentos = ?, instrucoes_busca = ?
            WHERE id = ?
            """,
            (canais_recebimento, emails_origem_documentos, instrucoes_busca, empresa_id),
        )

    def update_directory(self, empresa_id: int, diretorio_documentos: str | None) -> None:
        self._execute(
            "UPDATE empresas SET diretorio_documentos = ? WHERE id = ?",
            (diretorio_documentos, empresa_id),
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

    def update_whatsapp(self, empresa_id: int, whatsapp: str | None) -> None:
        self._execute("UPDATE empresas SET whatsapp = ? WHERE id = ?", (whatsapp, empresa_id))

    def update_whatsapp_envios(self, empresa_id: int, usar: bool, grupo: str | None) -> None:
        self._execute(
            "UPDATE empresas SET whatsapp_envios = ?, whatsapp_grupo = ? WHERE id = ?",
            (1 if usar else 0, grupo, empresa_id),
        )

    def update_nao_contatar_mala_direta(self, empresa_id: int, nao_contatar: bool) -> None:
        self._execute(
            "UPDATE empresas SET nao_contatar_mala_direta = ? WHERE id = ?",
            (1 if nao_contatar else 0, empresa_id),
        )

    def clear_contact_info(self, empresa_id: int) -> None:
        self._execute(
            "UPDATE empresas SET email_contato = NULL, nome_contato = NULL, whatsapp = NULL, "
            "whatsapp_envios = 0, whatsapp_grupo = NULL WHERE id = ?",
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
        return self._insert("INSERT INTO meios_recebimento_sistema (nome_meio) VALUES (?)", (nome_meio,))

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
                alerta_apos_dias,
                dias_entre_cobrancas,
                max_recobrancas,
                problema_vai_para_pessoa
            FROM configuracoes_cobranca
            WHERE id = 1
            """
        )
        return row or {
            "id": 1,
            "inicio_cobranca_dia": 5,
            "encerramento_cobranca_dia": 12,
            "alerta_apos_dias": 4,
            "dias_entre_cobrancas": 3,
            "max_recobrancas": 3,
            "problema_vai_para_pessoa": 1,
        }

    def update_rules(self, dias_entre_cobrancas: int, max_recobrancas: int, problema_vai_para_pessoa: int) -> None:
        self._execute(
            """
            INSERT INTO configuracoes_cobranca (
                id, inicio_cobranca_dia, encerramento_cobranca_dia, alerta_apos_dias,
                dias_entre_cobrancas, max_recobrancas, problema_vai_para_pessoa
            )
            VALUES (1, 5, 12, 4, ?, ?, ?)
            ON CONFLICT (id) DO UPDATE SET
                dias_entre_cobrancas = excluded.dias_entre_cobrancas,
                max_recobrancas = excluded.max_recobrancas,
                problema_vai_para_pessoa = excluded.problema_vai_para_pessoa
            """,
            (dias_entre_cobrancas, max_recobrancas, problema_vai_para_pessoa),
        )

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
        return self._insert(
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
            """
            SELECT (SELECT COUNT(*) FROM documentos_empresa WHERE tipo_documento_id = ?)
                 + (SELECT COUNT(*) FROM envios_programados WHERE tipo_documento_id = ?) AS total
            """,
            (tipo_id, tipo_id),
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
        return self._insert(
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
        return self._insert(
            """
            INSERT INTO sessoes_lembradas (usuario_id, selector, token_hash)
            VALUES (?, ?, ?)
            """,
            (usuario_id, selector, token_hash),
        )

    def touch(self, session_id: int) -> None:
        self._execute(
            f"""
            UPDATE sessoes_lembradas
            SET ultimo_uso_em = {UTC_NOW_FUNCTION}
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
        return self._insert(
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
            SELECT id, empresa_id, tipo_documento_id, meios_recebimento, nome_documento, observacao
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
                d.observacao,
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
                        d.observacao,
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
                d.observacao,
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
                        d.observacao,
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
            filters.append("n.nome_documento ILIKE ?")
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
            filters.append("nome_documento ILIKE ?")
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
        return self._insert(
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
            filters.append("nome_documento ILIKE ?")
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
        observacao: str | None = None,
    ) -> int:
        return self._insert(
            """
            INSERT INTO documentos_empresa (empresa_id, tipo_documento_id, meios_recebimento, nome_documento, observacao)
            VALUES (?, ?, ?, ?, ?)
            """,
            (empresa_id, tipo_documento_id, meios_recebimento, nome_documento, observacao),
        )

    def update(
        self,
        documento_id: int,
        tipo_documento_id: int,
        meios_recebimento: str | None,
        nome_documento: str,
        observacao: str | None = None,
    ) -> None:
        self._execute(
            """
            UPDATE documentos_empresa
            SET tipo_documento_id = ?, meios_recebimento = ?, nome_documento = ?, observacao = ?
            WHERE id = ?
            """,
            (tipo_documento_id, meios_recebimento, nome_documento, observacao, documento_id),
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
        return self._insert("INSERT INTO periodos (ano, mes) VALUES (?, ?)", (ano, mes))

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
    def list_marked_between(self, start_utc: str, end_utc: str, status: str = "Recebido") -> list[dict]:
        """Documentos que receberam o status informado entre dois horarios (UTC, 'AAAA-MM-DD hh:mm:ss')."""
        return self._fetchall(
            """
            SELECT
                e.id AS empresa_id,
                e.codigo_empresa,
                e.nome_empresa,
                d.nome_documento,
                t.nome_tipo AS tipo_documento,
                p.ano,
                p.mes,
                s.updated_at,
                COALESCE(u.username, 'Sistema') AS username
            FROM status_documento_mensal s
            INNER JOIN documentos_empresa d ON d.id = s.documento_empresa_id
            INNER JOIN tipos_documento t ON t.id = d.tipo_documento_id
            INNER JOIN empresas e ON e.id = d.empresa_id
            INNER JOIN periodos p ON p.id = s.periodo_id
            LEFT JOIN usuarios u ON u.id = s.updated_by_user_id
            WHERE s.status = ? AND s.updated_at >= ? AND s.updated_at < ?
            ORDER BY e.codigo_empresa, p.ano, p.mes, d.nome_documento
            """,
            (status, start_utc, end_utc),
        )

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
            f"""
            INSERT INTO status_documento_mensal (
                documento_empresa_id,
                periodo_id,
                status,
                updated_by_user_id,
                updated_at
            )
            VALUES (?, ?, ?, ?, {UTC_NOW_FUNCTION})
            ON CONFLICT(documento_empresa_id, periodo_id)
            DO UPDATE SET
                status = excluded.status,
                updated_by_user_id = excluded.updated_by_user_id,
                updated_at = {UTC_NOW_FUNCTION}
            """,
            (documento_empresa_id, periodo_id, status, updated_by_user_id),
        )

    def list_for_documents_and_periods(self, documento_ids: list[int], periodo_ids: list[int]) -> list[dict]:
        unique_document_ids = self._unique_values(documento_ids)
        unique_period_ids = self._unique_values(periodo_ids)
        if not unique_document_ids or not unique_period_ids:
            return []
        max_document_chunk = max(MAX_QUERY_PARAMETERS - len(unique_period_ids), 1)
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


class CobrancaRepository(BaseRepository):
    def create(
        self,
        empresa_id: int,
        canal: str,
        destinatario: str | None,
        assunto: str | None,
        mensagem: str | None,
        observacao: str | None,
        usuario_id: int | None,
        rodada_id: int | None = None,
    ) -> int:
        return self._insert(
            """
            INSERT INTO cobrancas (empresa_id, canal, destinatario, assunto, mensagem, observacao, usuario_id, rodada_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (empresa_id, canal, destinatario, assunto, mensagem, observacao, usuario_id, rodada_id),
        )

    def next_sequence(self, documento_empresa_id: int, periodo_id: int) -> int:
        row = self._fetchone(
            """
            SELECT COALESCE(MAX(sequencia), 0) + 1 AS proxima
            FROM cobranca_itens
            WHERE documento_empresa_id = ? AND periodo_id = ?
            """,
            (documento_empresa_id, periodo_id),
        )
        return int(row["proxima"])

    def add_item(self, cobranca_id: int, documento_empresa_id: int, periodo_id: int, sequencia: int) -> int:
        return self._insert(
            """
            INSERT INTO cobranca_itens (cobranca_id, documento_empresa_id, periodo_id, sequencia)
            VALUES (?, ?, ?, ?)
            """,
            (cobranca_id, documento_empresa_id, periodo_id, sequencia),
        )

    def list_recent(self, limit: int = 100, empresa_id: int | None = None) -> list[dict]:
        query = """
            SELECT
                c.id,
                c.empresa_id,
                e.codigo_empresa,
                e.nome_empresa,
                c.canal,
                c.destinatario,
                c.assunto,
                c.mensagem,
                c.observacao,
                c.realizada_em,
                c.rodada_id,
                COALESCE(u.username, 'Sistema') AS username
            FROM cobrancas c
            INNER JOIN empresas e ON e.id = c.empresa_id
            LEFT JOIN usuarios u ON u.id = c.usuario_id
        """
        params: list = []
        if empresa_id is not None:
            query += " WHERE c.empresa_id = ?"
            params.append(empresa_id)
        query += " ORDER BY c.realizada_em DESC, c.id DESC LIMIT ?"
        params.append(limit)
        return self._fetchall(query, tuple(params))

    def list_items(self, cobranca_ids: list[int]) -> list[dict]:
        unique_ids = self._unique_values(cobranca_ids)
        if not unique_ids:
            return []
        rows: list[dict] = []
        for chunk in self._chunk_values(unique_ids):
            placeholders = ", ".join("?" for _ in chunk)
            rows.extend(
                self._fetchall(
                    f"""
                    SELECT
                        ci.cobranca_id,
                        ci.documento_empresa_id,
                        ci.periodo_id,
                        ci.sequencia,
                        d.nome_documento,
                        p.ano,
                        p.mes
                    FROM cobranca_itens ci
                    INNER JOIN documentos_empresa d ON d.id = ci.documento_empresa_id
                    INNER JOIN periodos p ON p.id = ci.periodo_id
                    WHERE ci.cobranca_id IN ({placeholders})
                    ORDER BY p.ano, p.mes, d.nome_documento
                    """,
                    tuple(chunk),
                )
            )
        return rows

    def document_stats(self, empresa_id: int) -> list[dict]:
        """Por documento da empresa: quantas cobrancas (primeira de cada competencia),
        quantas recobrancas e quando foi a ultima."""
        return self._fetchall(
            """
            SELECT
                ci.documento_empresa_id,
                COUNT(*) FILTER (WHERE ci.sequencia = 1) AS cobrancas,
                COUNT(*) FILTER (WHERE ci.sequencia > 1) AS recobrancas,
                MAX(c.realizada_em) AS ultima_cobranca_em
            FROM cobranca_itens ci
            INNER JOIN cobrancas c ON c.id = ci.cobranca_id
            WHERE c.empresa_id = ?
            GROUP BY ci.documento_empresa_id
            """,
            (empresa_id,),
        )

    def count_contacts(self, empresa_id: int) -> dict:
        """Contatos de cobranca da empresa: total e quantos foram recobranca (cobraram de
        novo algum documento/competencia ja cobrado antes)."""
        return self._fetchone(
            """
            SELECT
                COUNT(*) AS total,
                COUNT(*) FILTER (
                    WHERE EXISTS (
                        SELECT 1 FROM cobranca_itens ci WHERE ci.cobranca_id = c.id AND ci.sequencia > 1
                    )
                ) AS recobrancas
            FROM cobrancas c
            WHERE c.empresa_id = ?
            """,
            (empresa_id,),
        )

    def counts_by_document_period(self, documento_ids: list[int]) -> list[dict]:
        """Quantas vezes cada documento ja foi cobrado em cada competencia, e quando foi a
        ultima - alimenta a fila de cobranca (cobrar pela primeira vez x recobrar)."""
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
                        ci.documento_empresa_id,
                        ci.periodo_id,
                        COUNT(*) AS vezes,
                        MAX(c.realizada_em) AS ultima_cobranca_em
                    FROM cobranca_itens ci
                    INNER JOIN cobrancas c ON c.id = ci.cobranca_id
                    WHERE ci.documento_empresa_id IN ({placeholders})
                    GROUP BY ci.documento_empresa_id, ci.periodo_id
                    """,
                    tuple(chunk),
                )
            )
        return rows

    def list_items_by_document(self, documento_empresa_id: int) -> list[dict]:
        return self._fetchall(
            """
            SELECT
                c.id AS cobranca_id,
                c.canal,
                c.destinatario,
                c.realizada_em,
                COALESCE(u.username, 'Sistema') AS username,
                ci.periodo_id,
                ci.sequencia,
                p.ano,
                p.mes
            FROM cobranca_itens ci
            INNER JOIN cobrancas c ON c.id = ci.cobranca_id
            INNER JOIN periodos p ON p.id = ci.periodo_id
            LEFT JOIN usuarios u ON u.id = c.usuario_id
            WHERE ci.documento_empresa_id = ?
            ORDER BY c.realizada_em DESC, c.id DESC
            """,
            (documento_empresa_id,),
        )


class VerificacaoRepository(BaseRepository):
    def create(
        self, empresa_id: int, fontes: str, resumo: str | None, usuario_id: int | None, rodada_id: int | None = None
    ) -> int:
        return self._insert(
            "INSERT INTO verificacoes (empresa_id, fontes, resumo, usuario_id, rodada_id) VALUES (?, ?, ?, ?, ?)",
            (empresa_id, fontes, resumo, usuario_id, rodada_id),
        )

    def add_item(
        self,
        verificacao_id: int,
        documento_empresa_id: int,
        periodo_id: int,
        resultado: str,
        onde: str | None,
        observacao: str | None,
        motivo: str | None = None,
        baixa_feita: bool = False,
        baixa_erro: str | None = None,
        arquivo: str | None = None,
    ) -> int:
        encontrado = resultado in ("recebido", "documento_com_problema")
        return self._insert(
            """
            INSERT INTO verificacao_itens (
                verificacao_id, documento_empresa_id, periodo_id, encontrado, onde, observacao,
                resultado, motivo, baixa_feita, baixa_erro, arquivo
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                verificacao_id, documento_empresa_id, periodo_id, 1 if encontrado else 0, onde, observacao,
                resultado, motivo, 1 if baixa_feita else 0, baixa_erro, arquivo,
            ),
        )

    def list_recent(self, limit: int = 100, empresa_id: int | None = None) -> list[dict]:
        query = """
            SELECT
                v.id,
                v.empresa_id,
                e.codigo_empresa,
                e.nome_empresa,
                v.fontes,
                v.resumo,
                v.realizada_em,
                v.rodada_id,
                COALESCE(u.username, 'Sistema') AS username,
                (SELECT COUNT(*) FROM verificacao_itens i WHERE i.verificacao_id = v.id AND i.resultado = 'recebido')
                    AS recebidos,
                (SELECT COUNT(*) FROM verificacao_itens i
                    WHERE i.verificacao_id = v.id AND i.resultado = 'documento_com_problema') AS com_problema,
                (SELECT COUNT(*) FROM verificacao_itens i
                    WHERE i.verificacao_id = v.id AND i.resultado = 'nao_encontrado') AS nao_encontrados,
                (SELECT COUNT(*) FROM verificacao_itens i
                    WHERE i.verificacao_id = v.id AND i.resultado = 'verificacao_falhou') AS falhas,
                (SELECT COUNT(*) FROM verificacao_itens i
                    WHERE i.verificacao_id = v.id AND i.resultado = 'recebido' AND i.baixa_feita = 0) AS sem_baixa
            FROM verificacoes v
            INNER JOIN empresas e ON e.id = v.empresa_id
            LEFT JOIN usuarios u ON u.id = v.usuario_id
        """
        params: list = []
        if empresa_id is not None:
            query += " WHERE v.empresa_id = ?"
            params.append(empresa_id)
        query += " ORDER BY v.realizada_em DESC, v.id DESC LIMIT ?"
        params.append(limit)
        return self._fetchall(query, tuple(params))

    def list_items(self, verificacao_ids: list[int]) -> list[dict]:
        unique_ids = self._unique_values(verificacao_ids)
        if not unique_ids:
            return []
        rows: list[dict] = []
        for chunk in self._chunk_values(unique_ids):
            placeholders = ", ".join("?" for _ in chunk)
            rows.extend(
                self._fetchall(
                    f"""
                    SELECT
                        vi.verificacao_id,
                        vi.documento_empresa_id,
                        vi.periodo_id,
                        vi.encontrado,
                        vi.onde,
                        vi.observacao,
                        vi.resultado,
                        vi.motivo,
                        vi.baixa_feita,
                        vi.baixa_erro,
                        vi.arquivo,
                        d.nome_documento,
                        p.ano,
                        p.mes
                    FROM verificacao_itens vi
                    INNER JOIN documentos_empresa d ON d.id = vi.documento_empresa_id
                    INNER JOIN periodos p ON p.id = vi.periodo_id
                    WHERE vi.verificacao_id IN ({placeholders})
                    ORDER BY p.ano, p.mes, d.nome_documento
                    """,
                    tuple(chunk),
                )
            )
        return rows

    def list_items_by_document(self, documento_empresa_id: int) -> list[dict]:
        return self._fetchall(
            """
            SELECT
                v.id AS verificacao_id,
                v.fontes,
                v.realizada_em,
                COALESCE(u.username, 'Sistema') AS username,
                vi.periodo_id,
                vi.encontrado,
                vi.onde,
                vi.observacao,
                vi.resultado,
                vi.motivo,
                vi.baixa_feita,
                vi.baixa_erro,
                vi.arquivo,
                p.ano,
                p.mes
            FROM verificacao_itens vi
            INNER JOIN verificacoes v ON v.id = vi.verificacao_id
            INNER JOIN periodos p ON p.id = vi.periodo_id
            LEFT JOIN usuarios u ON u.id = v.usuario_id
            WHERE vi.documento_empresa_id = ?
            ORDER BY v.realizada_em DESC, v.id DESC
            """,
            (documento_empresa_id,),
        )


class SituacaoCobrancaRepository(BaseRepository):
    def list_for_documents(self, documento_ids: list[int]) -> list[dict]:
        unique_ids = self._unique_values(documento_ids)
        if not unique_ids:
            return []
        rows: list[dict] = []
        for chunk in self._chunk_values(unique_ids):
            placeholders = ", ".join("?" for _ in chunk)
            rows.extend(
                self._fetchall(
                    f"""
                    SELECT documento_empresa_id, periodo_id, situacao, motivo, detalhe, aguardar_ate,
                           atualizado_em, rodada_id
                    FROM situacoes_cobranca
                    WHERE documento_empresa_id IN ({placeholders})
                    """,
                    tuple(chunk),
                )
            )
        return rows

    def get(self, documento_empresa_id: int, periodo_id: int) -> dict | None:
        return self._fetchone(
            """
            SELECT documento_empresa_id, periodo_id, situacao, motivo, detalhe, aguardar_ate, atualizado_em, rodada_id
            FROM situacoes_cobranca
            WHERE documento_empresa_id = ? AND periodo_id = ?
            """,
            (documento_empresa_id, periodo_id),
        )

    def upsert(
        self,
        documento_empresa_id: int,
        periodo_id: int,
        situacao: str,
        motivo: str | None,
        detalhe: str | None,
        aguardar_ate: str | None,
        usuario_id: int | None,
        rodada_id: int | None,
    ) -> None:
        self._execute(
            f"""
            INSERT INTO situacoes_cobranca (
                documento_empresa_id, periodo_id, situacao, motivo, detalhe, aguardar_ate, usuario_id, rodada_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (documento_empresa_id, periodo_id) DO UPDATE SET
                situacao = excluded.situacao,
                motivo = excluded.motivo,
                detalhe = excluded.detalhe,
                aguardar_ate = excluded.aguardar_ate,
                usuario_id = excluded.usuario_id,
                rodada_id = excluded.rodada_id,
                atualizado_em = {UTC_NOW_FUNCTION}
            """,
            (documento_empresa_id, periodo_id, situacao, motivo, detalhe, aguardar_ate, usuario_id, rodada_id),
        )

    def add_event(
        self,
        documento_empresa_id: int,
        periodo_id: int,
        situacao_anterior: str | None,
        situacao_nova: str,
        motivo: str | None,
        detalhe: str | None,
        usuario_id: int | None,
        rodada_id: int | None,
    ) -> int:
        return self._insert(
            """
            INSERT INTO situacao_eventos (
                documento_empresa_id, periodo_id, situacao_anterior, situacao_nova, motivo, detalhe,
                usuario_id, rodada_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (documento_empresa_id, periodo_id, situacao_anterior, situacao_nova, motivo, detalhe, usuario_id, rodada_id),
        )

    def list_events_by_document(self, documento_empresa_id: int) -> list[dict]:
        return self._fetchall(
            """
            SELECT
                ev.periodo_id,
                p.ano,
                p.mes,
                ev.situacao_anterior,
                ev.situacao_nova,
                ev.motivo,
                ev.detalhe,
                ev.criado_em,
                ev.rodada_id,
                COALESCE(u.username, 'Sistema') AS username
            FROM situacao_eventos ev
            INNER JOIN periodos p ON p.id = ev.periodo_id
            LEFT JOIN usuarios u ON u.id = ev.usuario_id
            WHERE ev.documento_empresa_id = ?
            ORDER BY ev.criado_em DESC, ev.id DESC
            """,
            (documento_empresa_id,),
        )


class RodadaRepository(BaseRepository):
    def create(self, origem: str, usuario_id: int | None) -> int:
        return self._insert("INSERT INTO rodadas (origem, usuario_id) VALUES (?, ?)", (origem, usuario_id))

    def finish(self, rodada_id: int, status: str, resumo: str | None) -> None:
        self._execute(
            f"""
            UPDATE rodadas
            SET status = ?, resumo = ?, finalizada_em = {UTC_NOW_FUNCTION}
            WHERE id = ?
            """,
            (status, resumo, rodada_id),
        )

    def add_ocorrencia(self, rodada_id: int, empresa_id: int | None, tipo: str, mensagem: str) -> int:
        return self._insert(
            "INSERT INTO rodada_ocorrencias (rodada_id, empresa_id, tipo, mensagem) VALUES (?, ?, ?, ?)",
            (rodada_id, empresa_id, tipo, mensagem),
        )

    def get(self, rodada_id: int) -> dict | None:
        rows = self.list_recent(1, rodada_id=rodada_id)
        return rows[0] if rows else None

    def list_recent(self, limit: int = 30, rodada_id: int | None = None) -> list[dict]:
        query = """
            SELECT
                r.id,
                r.origem,
                r.iniciada_em,
                r.finalizada_em,
                r.status,
                r.resumo,
                COALESCE(u.username, 'Sistema') AS username,
                (SELECT COUNT(*) FROM rodada_ocorrencias o WHERE o.rodada_id = r.id AND o.tipo = 'falha') AS falhas,
                (SELECT COUNT(*) FROM rodada_ocorrencias o WHERE o.rodada_id = r.id AND o.tipo = 'aviso') AS avisos,
                (SELECT COUNT(*) FROM verificacoes v WHERE v.rodada_id = r.id) AS verificacoes,
                (SELECT COUNT(*) FROM cobrancas c WHERE c.rodada_id = r.id) AS cobrancas,
                (SELECT COUNT(DISTINCT empresa_id) FROM (
                    SELECT empresa_id FROM verificacoes WHERE rodada_id = r.id
                    UNION SELECT empresa_id FROM cobrancas WHERE rodada_id = r.id
                    UNION SELECT empresa_id FROM rodada_ocorrencias WHERE rodada_id = r.id AND empresa_id IS NOT NULL
                    UNION SELECT d.empresa_id FROM situacao_eventos se
                        INNER JOIN documentos_empresa d ON d.id = se.documento_empresa_id
                        WHERE se.rodada_id = r.id
                ) empresas_rodada) AS empresas
            FROM rodadas r
            LEFT JOIN usuarios u ON u.id = r.usuario_id
        """
        params: list = []
        if rodada_id is not None:
            query += " WHERE r.id = ?"
            params.append(rodada_id)
        query += " ORDER BY r.iniciada_em DESC, r.id DESC LIMIT ?"
        params.append(limit)
        return self._fetchall(query, tuple(params))

    def list_ocorrencias(self, rodada_ids: list[int]) -> list[dict]:
        unique_ids = self._unique_values(rodada_ids)
        if not unique_ids:
            return []
        placeholders = ", ".join("?" for _ in unique_ids)
        return self._fetchall(
            f"""
            SELECT o.id, o.rodada_id, o.tipo, o.mensagem, o.criado_em, e.codigo_empresa, e.nome_empresa
            FROM rodada_ocorrencias o
            LEFT JOIN empresas e ON e.id = o.empresa_id
            WHERE o.rodada_id IN ({placeholders})
            ORDER BY o.criado_em, o.id
            """,
            tuple(unique_ids),
        )


class ModeloMensagemRepository(BaseRepository):
    def list_all(self) -> list[dict]:
        return self._fetchall("SELECT * FROM modelos_mensagem ORDER BY nome")

    def get(self, modelo_id: int) -> dict | None:
        return self._fetchone("SELECT * FROM modelos_mensagem WHERE id = ?", (modelo_id,))

    def get_by_nome(self, nome: str) -> dict | None:
        return self._fetchone("SELECT * FROM modelos_mensagem WHERE nome = ?", (nome,))

    def save(self, nome: str, assunto: str | None, corpo: str, corpo_whatsapp: str | None) -> int:
        """Cria o modelo ou, se o nome ja existe, substitui o texto dele."""
        existente = self.get_by_nome(nome)
        if existente:
            self._execute(
                f"""
                UPDATE modelos_mensagem SET assunto = ?, corpo = ?, corpo_whatsapp = ?,
                       atualizado_em = {UTC_NOW_FUNCTION}
                WHERE id = ?
                """,
                (assunto, corpo, corpo_whatsapp, existente["id"]),
            )
            return existente["id"]
        return self._insert(
            "INSERT INTO modelos_mensagem (nome, assunto, corpo, corpo_whatsapp) VALUES (?, ?, ?, ?)",
            (nome, assunto, corpo, corpo_whatsapp),
        )

    def delete(self, modelo_id: int) -> int:
        return self._execute("DELETE FROM modelos_mensagem WHERE id = ?", (modelo_id,))


class ImagemEmailRepository(BaseRepository):
    def insert(self, nome: str | None, tipo: str, dados_base64: str) -> int:
        return self._insert(
            "INSERT INTO imagens_email (nome, tipo, dados) VALUES (?, ?, ?)", (nome, tipo, dados_base64)
        )

    def get(self, imagem_id: int) -> dict | None:
        return self._fetchone("SELECT * FROM imagens_email WHERE id = ?", (imagem_id,))


class EnvioProgramadoRepository(BaseRepository):
    _CAMPOS = (
        "nome",
        "ativo",
        "tipo_documento_id",
        "meses",
        "dia_envio",
        "enviar_em",
        "canal",
        "empresa_ids",
        "modo",
        "email_para",
        "empresa_ids_excluidas",
        "corpo_whatsapp",
        "somente_pendentes",
        "assunto",
        "corpo",
        "instrucoes",
    )

    def list_all(self) -> list[dict]:
        return self._fetchall(
            """
            SELECT ep.*, t.nome_tipo
            FROM envios_programados ep
            LEFT JOIN tipos_documento t ON t.id = ep.tipo_documento_id
            ORDER BY ep.nome
            """
        )

    def get(self, envio_id: int) -> dict | None:
        return self._fetchone(
            """
            SELECT ep.*, t.nome_tipo
            FROM envios_programados ep
            LEFT JOIN tipos_documento t ON t.id = ep.tipo_documento_id
            WHERE ep.id = ?
            """,
            (envio_id,),
        )

    def create(self, dados: dict) -> int:
        colunas = ", ".join(self._CAMPOS)
        placeholders = ", ".join("?" for _ in self._CAMPOS)
        return self._insert(
            f"INSERT INTO envios_programados ({colunas}) VALUES ({placeholders})",
            tuple(dados[campo] for campo in self._CAMPOS),
        )

    def update(self, envio_id: int, dados: dict) -> None:
        atribuicoes = ", ".join(f"{campo} = ?" for campo in self._CAMPOS)
        self._execute(
            f"UPDATE envios_programados SET {atribuicoes}, atualizado_em = {UTC_NOW_FUNCTION} WHERE id = ?",
            (*(dados[campo] for campo in self._CAMPOS), envio_id),
        )

    def delete(self, envio_id: int) -> int:
        return self._execute("DELETE FROM envios_programados WHERE id = ?", (envio_id,))

    def list_destinatarios(
        self,
        tipo_documento_id: int | None,
        empresa_ids: list[int] | None,
        ano: int,
        mes: int,
        somente_pendentes: bool,
    ) -> list[dict]:
        """Uma linha por empresa ativa (e documento, quando a regra e de um tipo) que deve
        receber a mensagem na competencia. Sem tipo: as empresas escolhidas ou, sem escolha,
        todas as ativas - nos dois casos sem quem pediu para ficar fora da mala direta."""
        colunas_empresa = """
            e.id AS empresa_id, e.codigo_empresa, e.nome_empresa, e.email_contato, e.nome_contato,
            e.whatsapp, e.canais_recebimento, e.whatsapp_envios, e.whatsapp_grupo
        """
        if tipo_documento_id is None:
            query = f"""
                SELECT {colunas_empresa}, NULL::integer AS documento_id, NULL::text AS nome_documento,
                       NULL::text AS status, NULL::text AS meios_recebimento
                FROM empresas e
                WHERE e.ativa = 1 AND e.nao_contatar_mala_direta = 0
            """
            params: tuple = ()
            if empresa_ids:
                placeholders = ", ".join("?" for _ in empresa_ids)
                query += f" AND e.id IN ({placeholders})"
                params = tuple(empresa_ids)
            return self._fetchall(query + " ORDER BY e.codigo_empresa", params)
        query = f"""
            SELECT {colunas_empresa}, d.id AS documento_id, d.nome_documento::text AS nome_documento,
                   s.status, d.meios_recebimento
            FROM documentos_empresa d
            INNER JOIN empresas e ON e.id = d.empresa_id
            LEFT JOIN periodos p ON p.ano = ? AND p.mes = ?
            LEFT JOIN status_documento_mensal s ON s.documento_empresa_id = d.id AND s.periodo_id = p.id
            WHERE e.ativa = 1 AND d.tipo_documento_id = ?
        """
        if somente_pendentes:
            # Vazio ou Pendente: Recebido, Encerrado e Nao cobrar ficam de fora.
            query += " AND (s.status IS NULL OR s.status = 'Pendente')"
        query += " ORDER BY e.codigo_empresa, d.nome_documento"
        return self._fetchall(query, (ano, mes, tipo_documento_id))

    def list_enviados(self, envio_id: int, ano: int, mes: int) -> set[int]:
        rows = self._fetchall(
            """
            SELECT empresa_id FROM envios_registrados
            WHERE envio_programado_id = ? AND ano = ? AND mes = ? AND status = 'enviado'
            """,
            (envio_id, ano, mes),
        )
        return {row["empresa_id"] for row in rows}

    def registrar(
        self,
        envio_id: int,
        empresa_id: int,
        ano: int,
        mes: int,
        status: str,
        destinatarios: str | None,
        detalhe: str | None,
        usuario_id: int | None,
        rodada_id: int | None,
        canal: str | None = None,
    ) -> int | None:
        """Devolve o id do registro, ou None se ja havia um envio com sucesso igual."""
        with self.db_manager.connect() as connection:
            row = connection.execute(
                """
                INSERT INTO envios_registrados (
                    envio_programado_id, empresa_id, ano, mes, status, destinatarios, detalhe, usuario_id,
                    rodada_id, canal
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (envio_programado_id, empresa_id, ano, mes) WHERE status = 'enviado' DO NOTHING
                RETURNING id
                """,
                (envio_id, empresa_id, ano, mes, status, destinatarios, detalhe, usuario_id, rodada_id, canal),
            ).fetchone()
        return int(row["id"]) if row else None

    def list_historico(self, envio_id: int | None = None, empresa_id: int | None = None, limit: int = 200) -> list[dict]:
        query = """
            SELECT r.id, r.envio_programado_id, ep.nome AS envio_nome, r.ano, r.mes, r.status, r.canal,
                   r.destinatarios, r.detalhe, r.registrado_em, r.rodada_id,
                   e.codigo_empresa, e.nome_empresa, COALESCE(u.username, 'Sistema') AS username
            FROM envios_registrados r
            INNER JOIN envios_programados ep ON ep.id = r.envio_programado_id
            INNER JOIN empresas e ON e.id = r.empresa_id
            LEFT JOIN usuarios u ON u.id = r.usuario_id
            WHERE 1 = 1
        """
        params: list = []
        if envio_id is not None:
            query += " AND r.envio_programado_id = ?"
            params.append(envio_id)
        if empresa_id is not None:
            query += " AND r.empresa_id = ?"
            params.append(empresa_id)
        query += " ORDER BY r.registrado_em DESC, r.id DESC LIMIT ?"
        params.append(limit)
        return self._fetchall(query, tuple(params))
