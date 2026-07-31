from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import shutil

from documentos_empresa_app.services.audit_service import AuditService
from documentos_empresa_app.services.file_check_service import (
    detect_document_bank,
    detect_document_type,
    document_match_terms,
    is_bank_statement_document,
    resolve_company_folder,
    resolve_document_folder,
    resolve_extratos_folder,
    resolve_month_folder,
    resolve_type_subfolder,
    resolve_year_folder,
    suggest_company_folder_path,
)
from documentos_empresa_app.services.filename_pattern_service import (
    has_conflicting_naming_templates,
    infer_filename_from_siblings,
    synthesize_default_filename,
)
from documentos_empresa_app.services.session_service import SessionService
from documentos_empresa_app.utils.common import ValidationError
from documentos_empresa_app.utils.file_naming import list_missing_ancestor_dirs, resolve_unique_path


@dataclass(slots=True)
class OrganizeProposal:
    destination_dir: Path
    new_filename: str
    based_on_sibling: Path | None
    company_dir: Path
    new_folders: list[Path] = field(default_factory=list)
    filename_is_synthesized: bool = False


@dataclass(slots=True)
class OrganizeNeedsInput:
    reason: str
    candidate_dir: Path | None
    message: str


def resolve_organize_target(
    company_dir: Path,
    mes: int,
    ano: int,
    *,
    bank_key: str | None = None,
    doc_type: str | None = None,
    doc_terms: list[str] | None = None,
    doc_label: str | None = None,
    original_filename: str | None = None,
) -> OrganizeProposal | OrganizeNeedsInput:
    year_dir, _score, _note = resolve_year_folder(company_dir, ano)
    if year_dir is None:
        leaf_dir = company_dir / str(ano)
    elif doc_terms:
        leaf_dir = year_dir
        doc_dir, _score, _note = resolve_document_folder(year_dir, doc_terms)
        if doc_dir is not None:
            leaf_dir = doc_dir
        else:
            month_dir, _score, _note = resolve_month_folder(year_dir, mes, ano)
            if month_dir is not None:
                leaf_dir = month_dir
    else:
        leaf_dir = year_dir
        extratos_dir, _score, _note = resolve_extratos_folder(year_dir)
        if extratos_dir is not None:
            type_dir, _score, _note = resolve_type_subfolder(extratos_dir, doc_type)
            leaf_dir = type_dir or extratos_dir
        else:
            month_dir, _score, _note = resolve_month_folder(year_dir, mes, ano)
            if month_dir is not None:
                leaf_dir = month_dir

    inferred = infer_filename_from_siblings(
        leaf_dir, mes, ano, bank_key=bank_key, doc_type=doc_type, doc_terms=doc_terms
    )
    if inferred is not None:
        return OrganizeProposal(
            destination_dir=leaf_dir,
            new_filename=inferred.new_filename,
            based_on_sibling=inferred.based_on,
            company_dir=company_dir,
            new_folders=list_missing_ancestor_dirs(leaf_dir),
        )

    if has_conflicting_naming_templates(leaf_dir, bank_key=bank_key, doc_type=doc_type, doc_terms=doc_terms):
        return OrganizeNeedsInput(
            reason="pasta_sem_padrao",
            candidate_dir=leaf_dir,
            message=(
                f'Encontrei arquivos em "{leaf_dir}" mas com nomes que seguem convencoes diferentes '
                "(nao consigo saber qual seguir com seguranca). Qual nome de arquivo devo usar?"
            ),
        )

    new_filename = synthesize_default_filename(
        mes, ano, bank_key=bank_key, doc_type=doc_type, doc_label=doc_label, original_filename=original_filename
    )
    return OrganizeProposal(
        destination_dir=leaf_dir,
        new_filename=new_filename,
        based_on_sibling=None,
        company_dir=company_dir,
        new_folders=list_missing_ancestor_dirs(leaf_dir),
        filename_is_synthesized=True,
    )


class DocumentOrganizerService:
    def __init__(
        self,
        empresa_repository,
        pendente_repository,
        audit_service: AuditService | None = None,
        session_service: SessionService | None = None,
    ) -> None:
        self.empresa_repository = empresa_repository
        self.pendente_repository = pendente_repository
        self.audit_service = audit_service
        self.session_service = session_service

    def propose(
        self,
        pendente_id: int,
        empresa_id: int,
        mes: int,
        ano: int,
        *,
        banco: str | None = None,
        tipo_conta: str | None = None,
        diretorio_documentos: str | None = None,
        empresas_root_dir: str | None = None,
        documento_empresa: dict | None = None,
    ) -> OrganizeProposal | OrganizeNeedsInput:
        pendente = self.pendente_repository.get_by_id(pendente_id)
        if not pendente or pendente["status"] != "pendente":
            raise ValidationError("Documento pendente nao encontrado.")

        empresa = self.empresa_repository.get_by_id(empresa_id)
        if not empresa:
            raise ValidationError("Empresa nao encontrada.")

        company_dir = self._resolve_company_dir(empresa, diretorio_documentos, empresas_root_dir)
        if isinstance(company_dir, OrganizeNeedsInput):
            return company_dir

        bank_key: str | None
        normalized_doc_type: str | None
        doc_terms: list[str] | None
        doc_label: str | None

        if documento_empresa is not None:
            nome_tipo = documento_empresa.get("nome_tipo", "")
            nome_documento = documento_empresa.get("nome_documento", "")
            if is_bank_statement_document(nome_tipo, nome_documento):
                bank_key = detect_document_bank(banco) if banco else detect_document_bank(nome_documento)
                normalized_doc_type = (
                    tipo_conta if tipo_conta in ("cc", "aplicacao") else detect_document_type(nome_documento)
                )
                doc_terms = None
                doc_label = None
            else:
                bank_key = None
                normalized_doc_type = None
                doc_terms = document_match_terms(nome_tipo, nome_documento)
                doc_label = nome_documento
        else:
            bank_key = detect_document_bank(banco) if banco else None
            normalized_doc_type = tipo_conta if tipo_conta in ("cc", "aplicacao") else None
            doc_terms = None
            doc_label = None

        return resolve_organize_target(
            company_dir,
            mes,
            ano,
            bank_key=bank_key,
            doc_type=normalized_doc_type,
            doc_terms=doc_terms,
            doc_label=doc_label,
            original_filename=pendente["nome_arquivo"],
        )

    def _resolve_company_dir(
        self,
        empresa: dict,
        diretorio_override: str | None,
        empresas_root_dir: str | None,
    ) -> Path | OrganizeNeedsInput:
        if diretorio_override:
            candidate = Path(diretorio_override)
            if not candidate.is_dir():
                return OrganizeNeedsInput(
                    reason="empresa_sem_pasta",
                    candidate_dir=candidate,
                    message=(
                        f'A pasta escolhida para "{empresa["nome_empresa"]}" ("{candidate}") nao existe '
                        "ou nao esta acessivel. Qual pasta devo usar?"
                    ),
                )
            return candidate

        if not empresa.get("diretorio_documentos") and not empresas_root_dir:
            return OrganizeNeedsInput(
                reason="empresa_sem_pasta",
                candidate_dir=None,
                message=(
                    f'A empresa "{empresa["nome_empresa"]}" ainda nao tem uma pasta de documentos '
                    "configurada, e nenhuma pasta raiz de empresas foi definida. Qual pasta devo usar?"
                ),
            )

        # resolve_company_folder ja prioriza empresa["diretorio_documentos"] internamente e so cai
        # pra busca na raiz quando esse campo esta vazio - por isso root_dir so importa nesse segundo
        # caso (quando ha diretorio configurado, o valor de root_dir eh ignorado por essa funcao).
        root_dir = Path(empresas_root_dir) if empresas_root_dir else Path(empresa["diretorio_documentos"])
        found_dir, _score, note = resolve_company_folder(empresa, root_dir)
        if found_dir is None:
            # So propoe criar uma pasta de empresa nova quando a busca foi feita numa pasta raiz
            # de fato (nunca quando "diretorio_documentos" ja estava configurado mas sumiu do
            # disco - nesse caso e mais provavel ter sido movida/renomeada do que ser empresa nova).
            if not empresa.get("diretorio_documentos") and root_dir.is_dir():
                return suggest_company_folder_path(empresa, root_dir)
            return OrganizeNeedsInput(
                reason="empresa_sem_pasta",
                candidate_dir=None,
                message=f'Nao encontrei a pasta de "{empresa["nome_empresa"]}" ({note}). Qual pasta devo usar?',
            )
        return found_dir

    def execute(self, pendente_id: int, empresa_id: int, proposal: OrganizeProposal) -> Path:
        with self.empresa_repository.db_manager.connect():
            pendente = self.pendente_repository.get_by_id(pendente_id)
            if not pendente or pendente["status"] != "pendente":
                raise ValidationError("Documento pendente nao encontrado.")

            empresa = self.empresa_repository.get_by_id(empresa_id)
            if not empresa:
                raise ValidationError("Empresa nao encontrada.")

            origem = Path(pendente["caminho_arquivo_original"])
            if not origem.exists():
                raise ValidationError("O arquivo original nao foi encontrado no disco.")

            # Recalcula no momento do execute (nao confia cegamente no que propose() previu -
            # pode ter passado tempo entre propor e confirmar, ex. na tela em lote).
            newly_created = [p for p in proposal.new_folders if not p.exists()]

            try:
                proposal.destination_dir.mkdir(parents=True, exist_ok=True)
                destino = resolve_unique_path(proposal.destination_dir, proposal.new_filename)
                shutil.move(str(origem), str(destino))
            except OSError as exc:
                raise ValidationError(f"Nao foi possivel mover o arquivo: {exc}") from exc

            if not empresa.get("diretorio_documentos"):
                self.empresa_repository.update_directory(empresa_id, str(proposal.company_dir))
                empresa = self.empresa_repository.get_by_id(empresa_id)

            pastas_texto = ""
            if newly_created:
                pastas_texto = " Foram criadas a(s) pasta(s): " + ", ".join(str(p) for p in newly_created) + "."

            usuario_id = self.session_service.get_user_id() if self.session_service else None
            self.pendente_repository.mark_resolved(pendente_id, empresa_id, usuario_id)
            self._log(
                "DOCUMENTO_ORGANIZADO_IA",
                "documento_pendente_revisao",
                pendente_id,
                (
                    f'Agente de IA organizou o documento "{pendente["nome_arquivo"]}" para a empresa '
                    f'"{empresa["nome_empresa"]}" como "{destino.name}"{pastas_texto}, a pedido de '
                    f"{self._actor_name()}."
                ),
                empresa_id=empresa_id,
                empresa_nome=empresa["nome_empresa"],
            )
            return destino

    def _actor_name(self) -> str:
        if not self.session_service:
            return "Sistema"
        return self.session_service.get_username()

    def _log(
        self,
        acao: str,
        entidade: str,
        entidade_id: int | None,
        descricao: str,
        *,
        empresa_id: int | None = None,
        empresa_nome: str | None = None,
    ) -> None:
        if self.audit_service:
            self.audit_service.log(
                acao, entidade, entidade_id, descricao, empresa_id=empresa_id, empresa_nome=empresa_nome
            )
