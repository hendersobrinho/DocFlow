from __future__ import annotations

import re

from documentos_empresa_app.database.connection import DatabaseManager
from documentos_empresa_app.utils.common import (
    AUTO_STATUS_NAO_COBRAR,
    DOCUMENT_DELIVERY_OPTIONS,
    MAX_COMPANY_OBSERVATION_LENGTH,
    normalize_delivery_methods,
    normalize_type_occurrence_rule,
    TYPE_OCCURRENCE_MENSAL,
)
from documentos_empresa_app.utils.security import hash_password
from documentos_empresa_app.utils.type_names import canonicalize_tipo_name


INITIAL_TYPES = (
    "Extratos CC",
    "Extratos aplicacao",
    "Contratos",
    "Comprovantes",
    "Outros",
)

INITIAL_DELIVERY_METHODS = DOCUMENT_DELIVERY_OPTIONS


SCHEMA_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS empresas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        codigo_empresa INTEGER NOT NULL UNIQUE,
        nome_empresa TEXT NOT NULL COLLATE NOCASE,
        meios_recebimento TEXT NULL,
        email_contato TEXT NULL,
        nome_contato TEXT NULL,
        observacao TEXT NULL CHECK (observacao IS NULL OR length(observacao) <= 255),
        diretorio_documentos TEXT NULL,
        ativa INTEGER NOT NULL DEFAULT 1 CHECK (ativa IN (0, 1))
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS tipos_documento (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome_tipo TEXT NOT NULL UNIQUE COLLATE NOCASE,
        regra_ocorrencia TEXT NOT NULL DEFAULT 'mensal'
            CHECK (regra_ocorrencia IN ('mensal', 'trimestral', 'anual_janeiro'))
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS meios_recebimento_sistema (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome_meio TEXT NOT NULL UNIQUE COLLATE NOCASE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS configuracoes_cobranca (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        inicio_cobranca_dia INTEGER NOT NULL CHECK (inicio_cobranca_dia BETWEEN 1 AND 31),
        encerramento_cobranca_dia INTEGER NOT NULL CHECK (encerramento_cobranca_dia BETWEEN 1 AND 31),
        alerta_apos_dias INTEGER NOT NULL CHECK (alerta_apos_dias >= 0)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS nomes_documento_padrao_sistema (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tipo_documento_id INTEGER NOT NULL,
        nome_documento TEXT NOT NULL COLLATE NOCASE,
        FOREIGN KEY (tipo_documento_id) REFERENCES tipos_documento(id) ON DELETE CASCADE,
        CONSTRAINT uq_nome_documento_padrao UNIQUE (tipo_documento_id, nome_documento)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS documentos_empresa (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        empresa_id INTEGER NOT NULL,
        tipo_documento_id INTEGER NOT NULL,
        meios_recebimento TEXT NULL,
        nome_documento TEXT NOT NULL COLLATE NOCASE,
        FOREIGN KEY (empresa_id) REFERENCES empresas(id) ON DELETE CASCADE,
        FOREIGN KEY (tipo_documento_id) REFERENCES tipos_documento(id) ON DELETE RESTRICT,
        CONSTRAINT uq_documento UNIQUE (empresa_id, tipo_documento_id, nome_documento)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS periodos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ano INTEGER NOT NULL,
        mes INTEGER NOT NULL CHECK (mes BETWEEN 1 AND 12),
        CONSTRAINT uq_periodo UNIQUE (ano, mes)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS status_documento_mensal (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        documento_empresa_id INTEGER NOT NULL,
        periodo_id INTEGER NOT NULL,
        status TEXT NULL CHECK (
            status IN ('Recebido', 'Pendente', 'Encerrado', 'Nao cobrar')
            OR status IS NULL
        ),
        updated_by_user_id INTEGER NULL,
        updated_at TEXT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (documento_empresa_id) REFERENCES documentos_empresa(id) ON DELETE CASCADE,
        FOREIGN KEY (periodo_id) REFERENCES periodos(id) ON DELETE CASCADE,
        CONSTRAINT uq_status UNIQUE (documento_empresa_id, periodo_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS usuarios (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL UNIQUE COLLATE NOCASE,
        senha_hash TEXT NOT NULL,
        tipo_usuario TEXT NOT NULL CHECK (tipo_usuario IN ('admin', 'comum')),
        ativa INTEGER NOT NULL DEFAULT 1 CHECK (ativa IN (0, 1)),
        deve_trocar_senha INTEGER NOT NULL DEFAULT 0 CHECK (deve_trocar_senha IN (0, 1)),
        criado_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS sessoes_lembradas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        usuario_id INTEGER NOT NULL,
        selector TEXT NOT NULL UNIQUE,
        token_hash TEXT NOT NULL,
        criado_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        ultimo_uso_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        usuario_id INTEGER NULL,
        acao TEXT NOT NULL,
        entidade TEXT NOT NULL,
        entidade_id INTEGER NULL,
        empresa_id INTEGER NULL,
        empresa_nome TEXT NULL,
        periodo_ano INTEGER NULL,
        periodo_mes INTEGER NULL,
        descricao TEXT NOT NULL,
        data_hora TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE SET NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_documentos_empresa_empresa ON documentos_empresa (empresa_id)",
    "CREATE INDEX IF NOT EXISTS idx_documentos_empresa_tipo ON documentos_empresa (tipo_documento_id)",
    "CREATE INDEX IF NOT EXISTS idx_periodos_ano_mes ON periodos (ano, mes)",
    "CREATE INDEX IF NOT EXISTS idx_status_documento_periodo ON status_documento_mensal (documento_empresa_id, periodo_id)",
    """
    CREATE INDEX IF NOT EXISTS idx_status_documento_encerrado_periodo
    ON status_documento_mensal (documento_empresa_id, periodo_id)
    WHERE status = 'Encerrado'
    """,
    "CREATE INDEX IF NOT EXISTS idx_usuarios_username ON usuarios (username)",
    "CREATE INDEX IF NOT EXISTS idx_sessoes_lembradas_usuario ON sessoes_lembradas (usuario_id)",
    "CREATE INDEX IF NOT EXISTS idx_logs_data_hora ON logs (data_hora DESC)",
    "CREATE INDEX IF NOT EXISTS idx_logs_usuario_id ON logs (usuario_id)",
    "CREATE INDEX IF NOT EXISTS idx_logs_empresa_data_hora ON logs (empresa_id, data_hora DESC)",
    "CREATE INDEX IF NOT EXISTS idx_logs_periodo_data_hora ON logs (periodo_ano, periodo_mes, data_hora DESC)",
    """
    CREATE TABLE IF NOT EXISTS documentos_pendentes_revisao (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        caminho_arquivo_original TEXT NOT NULL,
        nome_arquivo TEXT NOT NULL,
        cnpj_extraido TEXT NULL,
        empresa_sugerida_id INTEGER NULL,
        empresa_sugerida_nome TEXT NULL,
        tipo_documento_sugerido TEXT NULL,
        confianca_sugestao REAL NULL CHECK (confianca_sugestao IS NULL OR (confianca_sugestao BETWEEN 0 AND 1)),
        origem_sugestao TEXT NOT NULL DEFAULT 'nenhuma' CHECK (origem_sugestao IN ('regex_cnpj', 'llm', 'nenhuma')),
        status TEXT NOT NULL DEFAULT 'pendente' CHECK (status IN ('pendente', 'resolvido', 'ignorado')),
        motivo TEXT NULL,
        criado_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        resolvido_em TEXT NULL,
        resolvido_por_usuario_id INTEGER NULL,
        empresa_confirmada_id INTEGER NULL,
        FOREIGN KEY (empresa_sugerida_id) REFERENCES empresas(id) ON DELETE SET NULL,
        FOREIGN KEY (empresa_confirmada_id) REFERENCES empresas(id) ON DELETE SET NULL,
        FOREIGN KEY (resolvido_por_usuario_id) REFERENCES usuarios(id) ON DELETE SET NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_pendentes_revisao_status ON documentos_pendentes_revisao (status)",
    "CREATE INDEX IF NOT EXISTS idx_pendentes_revisao_caminho ON documentos_pendentes_revisao (caminho_arquivo_original)",
    """
    CREATE TABLE IF NOT EXISTS usuario_preferencias (
        usuario_id INTEGER PRIMARY KEY,
        pasta_entrada TEXT NULL,
        FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE
    )
    """,
)


def initialize_schema(db_manager: DatabaseManager) -> None:
    with db_manager.connect() as connection:
        for statement in SCHEMA_STATEMENTS:
            connection.execute(statement)

        ensure_empresa_extra_columns(connection)
        ensure_empresa_collection_columns(connection)
        ensure_empresa_cnpj_column(connection)
        ensure_empresa_privacy_columns(connection)
        ensure_usuario_extra_columns(connection)
        ensure_usuario_preferencia_extra_columns(connection)
        ensure_tipo_extra_columns(connection)
        ensure_documento_extra_columns(connection)
        ensure_empresa_observacao_constraints(connection)
        normalize_tipo_occurrence_rules(connection)
        normalize_empresa_delivery_methods(connection)
        migrate_empresa_delivery_methods_to_documentos(connection)
        normalize_documento_delivery_methods(connection)
        ensure_log_metadata_columns(connection)
        ensure_status_allowed_values(connection)
        ensure_status_audit_columns(connection)
        backfill_log_metadata(connection)

        for tipo in INITIAL_TYPES:
            connection.execute(
                """
                INSERT INTO tipos_documento (nome_tipo, regra_ocorrencia)
                VALUES (?, ?)
                ON CONFLICT(nome_tipo) DO NOTHING
                """,
                (tipo, TYPE_OCCURRENCE_MENSAL),
            )

        for method in INITIAL_DELIVERY_METHODS:
            connection.execute(
                """
                INSERT INTO meios_recebimento_sistema (nome_meio)
                VALUES (?)
                ON CONFLICT(nome_meio) DO NOTHING
                """,
                (method,),
            )

        connection.execute(
            """
            INSERT INTO configuracoes_cobranca (
                id,
                inicio_cobranca_dia,
                encerramento_cobranca_dia,
                alerta_apos_dias
            )
            VALUES (1, 5, 12, 4)
            ON CONFLICT(id) DO NOTHING
            """
        )

        ensure_default_admin(connection)
        consolidate_duplicate_types(connection)


def ensure_empresa_extra_columns(connection) -> None:
    columns = {
        row["name"]: row
        for row in connection.execute("PRAGMA table_info(empresas)").fetchall()
    }
    required_columns = {
        "meios_recebimento": "TEXT NULL",
        "email_contato": "TEXT NULL",
        "nome_contato": "TEXT NULL",
        "observacao": f"TEXT NULL CHECK (observacao IS NULL OR length(observacao) <= {MAX_COMPANY_OBSERVATION_LENGTH})",
        "diretorio_documentos": "TEXT NULL",
    }
    for column_name, column_definition in required_columns.items():
        if column_name in columns:
            continue
        connection.execute(f"ALTER TABLE empresas ADD COLUMN {column_name} {column_definition}")


def ensure_empresa_collection_columns(connection) -> None:
    columns = {
        row["name"]: row
        for row in connection.execute("PRAGMA table_info(empresas)").fetchall()
    }
    required_columns = {
        "cobranca_inicio_dia": "INTEGER NULL CHECK (cobranca_inicio_dia BETWEEN 1 AND 31)",
        "cobranca_fim_dia": "INTEGER NULL CHECK (cobranca_fim_dia BETWEEN 1 AND 31)",
        "cobranca_alerta_dias": "INTEGER NULL CHECK (cobranca_alerta_dias >= 0)",
    }
    for column_name, column_definition in required_columns.items():
        if column_name in columns:
            continue
        connection.execute(f"ALTER TABLE empresas ADD COLUMN {column_name} {column_definition}")


def ensure_empresa_cnpj_column(connection) -> None:
    columns = {
        row["name"]: row
        for row in connection.execute("PRAGMA table_info(empresas)").fetchall()
    }
    if "cnpj" not in columns:
        connection.execute("ALTER TABLE empresas ADD COLUMN cnpj TEXT NULL")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_empresas_cnpj ON empresas (cnpj)")


def ensure_empresa_privacy_columns(connection) -> None:
    columns = {
        row["name"]: row
        for row in connection.execute("PRAGMA table_info(empresas)").fetchall()
    }
    if "nao_contatar_mala_direta" not in columns:
        connection.execute(
            "ALTER TABLE empresas ADD COLUMN nao_contatar_mala_direta "
            "INTEGER NOT NULL DEFAULT 0 CHECK (nao_contatar_mala_direta IN (0, 1))"
        )


def ensure_usuario_extra_columns(connection) -> None:
    columns = {
        row["name"]: row
        for row in connection.execute("PRAGMA table_info(usuarios)").fetchall()
    }
    if "deve_trocar_senha" not in columns:
        connection.execute(
            "ALTER TABLE usuarios ADD COLUMN deve_trocar_senha "
            "INTEGER NOT NULL DEFAULT 0 CHECK (deve_trocar_senha IN (0, 1))"
        )


def ensure_usuario_preferencia_extra_columns(connection) -> None:
    columns = {
        row["name"]: row
        for row in connection.execute("PRAGMA table_info(usuario_preferencias)").fetchall()
    }
    if "pasta_raiz_empresas" not in columns:
        connection.execute("ALTER TABLE usuario_preferencias ADD COLUMN pasta_raiz_empresas TEXT NULL")


def ensure_tipo_extra_columns(connection) -> None:
    columns = {
        row["name"]: row
        for row in connection.execute("PRAGMA table_info(tipos_documento)").fetchall()
    }
    required_columns = {
        "regra_ocorrencia": f"TEXT NOT NULL DEFAULT '{TYPE_OCCURRENCE_MENSAL}'",
    }
    for column_name, column_definition in required_columns.items():
        if column_name in columns:
            continue
        connection.execute(f"ALTER TABLE tipos_documento ADD COLUMN {column_name} {column_definition}")


def ensure_documento_extra_columns(connection) -> None:
    columns = {
        row["name"]: row
        for row in connection.execute("PRAGMA table_info(documentos_empresa)").fetchall()
    }
    required_columns = {
        "meios_recebimento": "TEXT NULL",
    }
    for column_name, column_definition in required_columns.items():
        if column_name in columns:
            continue
        connection.execute(f"ALTER TABLE documentos_empresa ADD COLUMN {column_name} {column_definition}")


def normalize_tipo_occurrence_rules(connection) -> None:
    rows = connection.execute(
        """
        SELECT id, regra_ocorrencia
        FROM tipos_documento
        """
    ).fetchall()

    for row in rows:
        normalized = normalize_type_occurrence_rule(row["regra_ocorrencia"])
        if normalized == row["regra_ocorrencia"]:
            continue
        connection.execute(
            "UPDATE tipos_documento SET regra_ocorrencia = ? WHERE id = ?",
            (normalized, row["id"]),
        )


def ensure_empresa_observacao_constraints(connection) -> None:
    connection.execute(
        f"""
        CREATE TRIGGER IF NOT EXISTS trg_empresas_observacao_insert
        BEFORE INSERT ON empresas
        FOR EACH ROW
        WHEN NEW.observacao IS NOT NULL AND length(NEW.observacao) > {MAX_COMPANY_OBSERVATION_LENGTH}
        BEGIN
            SELECT RAISE(FAIL, 'observacao_too_long');
        END
        """
    )
    connection.execute(
        f"""
        CREATE TRIGGER IF NOT EXISTS trg_empresas_observacao_update
        BEFORE UPDATE OF observacao ON empresas
        FOR EACH ROW
        WHEN NEW.observacao IS NOT NULL AND length(NEW.observacao) > {MAX_COMPANY_OBSERVATION_LENGTH}
        BEGIN
            SELECT RAISE(FAIL, 'observacao_too_long');
        END
        """
    )


def normalize_empresa_delivery_methods(connection) -> None:
    rows = connection.execute(
        """
        SELECT id, meios_recebimento
        FROM empresas
        WHERE meios_recebimento IS NOT NULL
        """
    ).fetchall()

    for row in rows:
        normalized = _normalize_delivery_methods_value(row["meios_recebimento"])
        if normalized == row["meios_recebimento"]:
            continue
        connection.execute(
            "UPDATE empresas SET meios_recebimento = ? WHERE id = ?",
            (normalized, row["id"]),
        )


def migrate_empresa_delivery_methods_to_documentos(connection) -> None:
    rows = connection.execute(
        """
        SELECT d.id, e.meios_recebimento
        FROM documentos_empresa d
        INNER JOIN empresas e ON e.id = d.empresa_id
        WHERE (d.meios_recebimento IS NULL OR trim(d.meios_recebimento) = '')
          AND e.meios_recebimento IS NOT NULL
          AND trim(e.meios_recebimento) <> ''
        """
    ).fetchall()

    for row in rows:
        normalized = _normalize_delivery_methods_value(row["meios_recebimento"])
        if not normalized:
            continue
        connection.execute(
            "UPDATE documentos_empresa SET meios_recebimento = ? WHERE id = ?",
            (normalized, row["id"]),
        )


def normalize_documento_delivery_methods(connection) -> None:
    rows = connection.execute(
        """
        SELECT id, meios_recebimento
        FROM documentos_empresa
        WHERE meios_recebimento IS NOT NULL
        """
    ).fetchall()

    for row in rows:
        normalized = _normalize_delivery_methods_value(row["meios_recebimento"])
        if normalized == row["meios_recebimento"]:
            continue
        connection.execute(
            "UPDATE documentos_empresa SET meios_recebimento = ? WHERE id = ?",
            (normalized, row["id"]),
        )


def _normalize_delivery_methods_value(raw_value: str | None) -> str | None:
    return normalize_delivery_methods(raw_value)


def ensure_log_metadata_columns(connection) -> None:
    columns = {
        row["name"]: row
        for row in connection.execute("PRAGMA table_info(logs)").fetchall()
    }
    required_columns = {
        "empresa_id": "INTEGER NULL",
        "empresa_nome": "TEXT NULL",
        "periodo_ano": "INTEGER NULL",
        "periodo_mes": "INTEGER NULL",
    }

    for column_name, column_definition in required_columns.items():
        if column_name in columns:
            continue
        connection.execute(f"ALTER TABLE logs ADD COLUMN {column_name} {column_definition}")

    connection.execute("CREATE INDEX IF NOT EXISTS idx_logs_empresa_id ON logs (empresa_id)")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_logs_periodo ON logs (periodo_ano, periodo_mes)")


def ensure_status_audit_columns(connection) -> None:
    columns = {
        row["name"]: row
        for row in connection.execute("PRAGMA table_info(status_documento_mensal)").fetchall()
    }
    required_columns = {
        "updated_by_user_id": "INTEGER NULL",
        "updated_at": "TEXT NULL",
    }

    for column_name, column_definition in required_columns.items():
        if column_name in columns:
            continue
        connection.execute(f"ALTER TABLE status_documento_mensal ADD COLUMN {column_name} {column_definition}")

    connection.execute(
        """
        UPDATE status_documento_mensal
        SET updated_at = CURRENT_TIMESTAMP
        WHERE updated_at IS NULL
        """
    )


def ensure_status_allowed_values(connection) -> None:
    row = connection.execute(
        """
        SELECT sql
        FROM sqlite_master
        WHERE type = 'table' AND name = 'status_documento_mensal'
        """
    ).fetchone()
    table_sql = row["sql"] if row else ""
    if AUTO_STATUS_NAO_COBRAR in str(table_sql or ""):
        return

    connection.execute("ALTER TABLE status_documento_mensal RENAME TO status_documento_mensal_legacy")
    connection.execute(
        """
        CREATE TABLE status_documento_mensal (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            documento_empresa_id INTEGER NOT NULL,
            periodo_id INTEGER NOT NULL,
            status TEXT NULL CHECK (
                status IN ('Recebido', 'Pendente', 'Encerrado', 'Nao cobrar')
                OR status IS NULL
            ),
            updated_by_user_id INTEGER NULL,
            updated_at TEXT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (documento_empresa_id) REFERENCES documentos_empresa(id) ON DELETE CASCADE,
            FOREIGN KEY (periodo_id) REFERENCES periodos(id) ON DELETE CASCADE,
            CONSTRAINT uq_status UNIQUE (documento_empresa_id, periodo_id)
        )
        """
    )

    legacy_columns = {
        info["name"]
        for info in connection.execute("PRAGMA table_info(status_documento_mensal_legacy)").fetchall()
    }
    copy_columns = [
        column_name
        for column_name in (
            "id",
            "documento_empresa_id",
            "periodo_id",
            "status",
            "updated_by_user_id",
            "updated_at",
        )
        if column_name in legacy_columns
    ]
    if copy_columns:
        column_list = ", ".join(copy_columns)
        connection.execute(
            f"""
            INSERT INTO status_documento_mensal ({column_list})
            SELECT {column_list}
            FROM status_documento_mensal_legacy
            """
        )

    connection.execute("DROP TABLE status_documento_mensal_legacy")
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_status_documento_periodo
        ON status_documento_mensal (documento_empresa_id, periodo_id)
        """
    )


def backfill_log_metadata(connection) -> None:
    rows = connection.execute(
        """
        SELECT id, entidade, entidade_id, empresa_id, empresa_nome, periodo_ano, periodo_mes, descricao
        FROM logs
        WHERE empresa_id IS NULL
           OR empresa_nome IS NULL
           OR (entidade = 'documento_status' AND (periodo_ano IS NULL OR periodo_mes IS NULL))
        ORDER BY id
        """
    ).fetchall()

    for row in rows:
        log = dict(row)
        empresa_id = log["empresa_id"]
        empresa_nome = log["empresa_nome"]
        periodo_ano = log["periodo_ano"]
        periodo_mes = log["periodo_mes"]

        resolved_company = _resolve_log_company(connection, log["entidade"], log["entidade_id"])
        if resolved_company:
            empresa_id = empresa_id or resolved_company["id"]
            empresa_nome = empresa_nome or resolved_company["nome_empresa"]

        if not empresa_nome:
            empresa_nome = _extract_company_name_from_description(log["descricao"])

        if log["entidade"] == "documento_status" and (periodo_ano is None or periodo_mes is None):
            extracted_period = _extract_period_from_description(log["descricao"])
            if extracted_period:
                periodo_mes = periodo_mes or extracted_period[0]
                periodo_ano = periodo_ano or extracted_period[1]

        connection.execute(
            """
            UPDATE logs
            SET empresa_id = ?, empresa_nome = ?, periodo_ano = ?, periodo_mes = ?
            WHERE id = ?
            """,
            (empresa_id, empresa_nome, periodo_ano, periodo_mes, log["id"]),
        )


def _resolve_log_company(connection, entidade: str, entidade_id: int | None) -> dict | None:
    if entidade_id is None:
        return None
    if entidade == "empresa":
        row = connection.execute(
            "SELECT id, nome_empresa FROM empresas WHERE id = ?",
            (entidade_id,),
        ).fetchone()
        return dict(row) if row else None
    if entidade in {"documento", "documento_status"}:
        row = connection.execute(
            """
            SELECT e.id, e.nome_empresa
            FROM documentos_empresa d
            INNER JOIN empresas e ON e.id = d.empresa_id
            WHERE d.id = ?
            """,
            (entidade_id,),
        ).fetchone()
        return dict(row) if row else None
    return None


def _extract_company_name_from_description(descricao: str) -> str | None:
    match = re.search(r'empresa "([^"]+)"', descricao)
    return match.group(1) if match else None


def _extract_period_from_description(descricao: str) -> tuple[int, int] | None:
    match = re.search(r"periodo (\d{2})/(\d{4})", descricao)
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))


def ensure_default_admin(connection) -> None:
    total_users = connection.execute("SELECT COUNT(*) AS total FROM usuarios").fetchone()["total"]
    if total_users:
        return

    connection.execute(
        """
        INSERT INTO usuarios (username, senha_hash, tipo_usuario, ativa, deve_trocar_senha)
        VALUES (?, ?, 'admin', 1, 1)
        """,
        ("admin", hash_password("admin")),
    )


def consolidate_duplicate_types(connection) -> None:
    rows = connection.execute(
        """
        SELECT id, nome_tipo, regra_ocorrencia
        FROM tipos_documento
        ORDER BY id
        """
    ).fetchall()

    grouped_rows: dict[str, list[dict]] = {}
    for row in rows:
        row_dict = dict(row)
        canonical_name = canonicalize_tipo_name(row_dict["nome_tipo"])
        grouped_rows.setdefault(canonical_name, []).append(row_dict)

    for canonical_name, items in grouped_rows.items():
        canonical_row = _select_canonical_type_row(items, canonical_name)
        canonical_type_id = canonical_row["id"]
        canonical_rule = _select_canonical_type_rule(items, canonical_row)

        for row in items:
            if row["id"] == canonical_type_id:
                continue
            _merge_type_into(connection, row["id"], canonical_type_id)
            connection.execute("DELETE FROM tipos_documento WHERE id = ?", (row["id"],))

        if canonical_row["nome_tipo"] != canonical_name or canonical_row["regra_ocorrencia"] != canonical_rule:
            connection.execute(
                "UPDATE tipos_documento SET nome_tipo = ?, regra_ocorrencia = ? WHERE id = ?",
                (canonical_name, canonical_rule, canonical_type_id),
            )


def _select_canonical_type_row(items: list[dict], canonical_name: str) -> dict:
    exact_match = next((item for item in items if item["nome_tipo"] == canonical_name), None)
    if exact_match:
        return exact_match
    return min(items, key=lambda item: item["id"])


def _select_canonical_type_rule(items: list[dict], canonical_row: dict) -> str:
    canonical_rule = normalize_type_occurrence_rule(canonical_row.get("regra_ocorrencia"))
    if canonical_rule != TYPE_OCCURRENCE_MENSAL:
        return canonical_rule

    for item in items:
        item_rule = normalize_type_occurrence_rule(item.get("regra_ocorrencia"))
        if item_rule != TYPE_OCCURRENCE_MENSAL:
            return item_rule
    return TYPE_OCCURRENCE_MENSAL


def _merge_type_into(connection, source_type_id: int, target_type_id: int) -> None:
    documents = connection.execute(
        """
        SELECT id, empresa_id, nome_documento
        FROM documentos_empresa
        WHERE tipo_documento_id = ?
        ORDER BY id
        """,
        (source_type_id,),
    ).fetchall()

    for document in documents:
        duplicate_target = connection.execute(
            """
            SELECT id
            FROM documentos_empresa
            WHERE empresa_id = ?
              AND tipo_documento_id = ?
              AND nome_documento = ?
            """,
            (document["empresa_id"], target_type_id, document["nome_documento"]),
        ).fetchone()

        if duplicate_target:
            _merge_document_statuses(connection, document["id"], duplicate_target["id"])
            connection.execute("DELETE FROM documentos_empresa WHERE id = ?", (document["id"],))
            continue

        connection.execute(
            "UPDATE documentos_empresa SET tipo_documento_id = ? WHERE id = ?",
            (target_type_id, document["id"]),
        )


def _merge_document_statuses(connection, source_document_id: int, target_document_id: int) -> None:
    connection.execute(
        """
        INSERT INTO status_documento_mensal (documento_empresa_id, periodo_id, status)
        SELECT ?, periodo_id, status
        FROM status_documento_mensal
        WHERE documento_empresa_id = ?
        ON CONFLICT(documento_empresa_id, periodo_id)
        DO UPDATE SET status = COALESCE(status_documento_mensal.status, excluded.status)
        """,
        (target_document_id, source_document_id),
    )
