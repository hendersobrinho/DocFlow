from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class Empresa:
    id: int | None
    codigo_empresa: int
    nome_empresa: str
    meios_recebimento: str | None = None
    email_contato: str | None = None
    nome_contato: str | None = None
    diretorio_documentos: str | None = None
    ativa: int = 1


@dataclass(slots=True)
class TipoDocumento:
    id: int | None
    nome_tipo: str


@dataclass(slots=True)
class DocumentoEmpresa:
    id: int | None
    empresa_id: int
    tipo_documento_id: int
    nome_documento: str


@dataclass(slots=True)
class Periodo:
    id: int | None
    ano: int
    mes: int


@dataclass(slots=True)
class StatusDocumentoMensal:
    id: int | None
    documento_empresa_id: int
    periodo_id: int
    status: str | None


@dataclass(slots=True)
class Usuario:
    id: int | None
    username: str
    senha_hash: str
    tipo_usuario: str
    ativa: int = 1
    criado_em: str | None = None


@dataclass(slots=True)
class LogRegistro:
    id: int | None
    usuario_id: int | None
    acao: str
    entidade: str
    entidade_id: int | None
    descricao: str
    empresa_id: int | None = None
    empresa_nome: str | None = None
    periodo_ano: int | None = None
    periodo_mes: int | None = None
    data_hora: str | None = None
