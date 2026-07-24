from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil

from documentos_empresa_app.database.repositories import DocumentoPendenteRevisaoRepository, EmpresaRepository
from documentos_empresa_app.services.audit_service import AuditService
from documentos_empresa_app.services.document_classification_service import (
    ClassificationResult,
    DocumentClassificationService,
)
from documentos_empresa_app.services.document_extraction_service import (
    DocumentExtractionError,
    DocumentExtractionService,
)
from documentos_empresa_app.services.empresa_service import EmpresaService
from documentos_empresa_app.services.session_service import SessionService
from documentos_empresa_app.utils.common import ValidationError
from documentos_empresa_app.utils.document_agent_diagnostics import (
    log_extraction_failure,
    log_move_failure,
    log_unmatched_cnpj,
)


@dataclass(slots=True)
class ProcessedFileResult:
    file_path: Path
    outcome: str
    detail: str


class DocumentAgentService:
    def __init__(
        self,
        extraction_service: DocumentExtractionService,
        classification_service: DocumentClassificationService,
        pendente_repository: DocumentoPendenteRevisaoRepository,
        empresa_repository: EmpresaRepository,
        empresa_service: EmpresaService,
        audit_service: AuditService | None = None,
        session_service: SessionService | None = None,
    ) -> None:
        self.extraction_service = extraction_service
        self.classification_service = classification_service
        self.pendente_repository = pendente_repository
        self.empresa_repository = empresa_repository
        self.empresa_service = empresa_service
        self.audit_service = audit_service
        self.session_service = session_service

    # Fase 1 - thread principal, leitura de banco

    def scan_folder(self, source_folder: str | Path) -> list[Path]:
        folder = Path(source_folder)
        if not folder.is_dir():
            return []

        files: list[Path] = []
        for entry in sorted(folder.iterdir()):
            if not entry.is_file() or not self.extraction_service.is_supported(entry):
                continue
            if self.pendente_repository.get_by_original_path(str(entry)):
                continue
            files.append(entry)
        return files

    def build_cnpj_index(self) -> dict[str, dict]:
        empresas = self.empresa_repository.list_all(active_only=True)
        return {empresa["cnpj"]: empresa for empresa in empresas if empresa.get("cnpj")}

    def build_known_company_names(self) -> list[str]:
        empresas = self.empresa_repository.list_all(active_only=True)
        return [empresa["nome_empresa"] for empresa in empresas]

    # Fase 2 - segura para thread de fundo, sem banco

    def classify_file(
        self,
        file_path: Path,
        empresa_cnpj_index: dict[str, dict],
        known_company_names: list[str],
    ) -> tuple[Path, ClassificationResult | None, str | None]:
        try:
            text = self.extraction_service.extract_text(file_path)
        except DocumentExtractionError as exc:
            log_extraction_failure(str(file_path), str(exc))
            return file_path, None, str(exc)

        result = self.classification_service.classify(text, empresa_cnpj_index, known_company_names)
        if result.origem != "regex_cnpj":
            # A camada local (sem IA) nao resolveu sozinha - registra pra permitir
            # ajustar o regex/casamento de CNPJ depois, com o texto real que falhou.
            candidates = self.classification_service.extract_cnpj_candidates(text)
            log_unmatched_cnpj(str(file_path), candidates, text)
        return file_path, result, None

    # Fase 3 - thread principal, escrita de banco + filesystem

    def apply_result(
        self,
        file_path: Path,
        result: ClassificationResult | None,
        extraction_error: str | None,
    ) -> ProcessedFileResult:
        file_path = Path(file_path)
        with self.empresa_repository.db_manager.connect():
            if extraction_error:
                self.pendente_repository.create(
                    str(file_path), file_path.name, None, None, None, None, None, "nenhuma", extraction_error,
                )
                return ProcessedFileResult(file_path, "pendente_revisao", extraction_error)

            assert result is not None

            if result.matched_empresa:
                diretorio = result.matched_empresa.get("diretorio_documentos")
                if diretorio:
                    try:
                        destino_dir = Path(diretorio)
                        destino_dir.mkdir(parents=True, exist_ok=True)
                        destino = self._resolve_destination_path(destino_dir, file_path)
                        shutil.move(str(file_path), str(destino))
                    except OSError as exc:
                        motivo = f"Falha ao mover arquivo automaticamente: {exc}"
                        log_move_failure(str(file_path), diretorio, str(exc))
                        self.pendente_repository.create(
                            str(file_path),
                            file_path.name,
                            result.cnpj_extraido,
                            result.matched_empresa["id"],
                            result.matched_empresa.get("nome_empresa"),
                            result.tipo_documento_sugerido,
                            result.confianca,
                            result.origem,
                            motivo,
                        )
                        return ProcessedFileResult(file_path, "erro", motivo)

                    self._log(
                        "DOCUMENTO_MOVIDO_AUTOMATICO",
                        "documento_pendente_revisao",
                        None,
                        (
                            f'Documento "{file_path.name}" movido automaticamente para a empresa '
                            f'"{result.matched_empresa["nome_empresa"]}".'
                        ),
                        empresa_id=result.matched_empresa["id"],
                        empresa_nome=result.matched_empresa.get("nome_empresa"),
                    )
                    return ProcessedFileResult(file_path, "movido", str(destino))

                self.pendente_repository.create(
                    str(file_path),
                    file_path.name,
                    result.cnpj_extraido,
                    result.matched_empresa["id"],
                    result.matched_empresa.get("nome_empresa"),
                    result.tipo_documento_sugerido,
                    result.confianca,
                    result.origem,
                    "Empresa identificada, mas sem pasta de destino configurada.",
                )
                return ProcessedFileResult(file_path, "pendente_revisao", "Empresa sem pasta configurada.")

            self.pendente_repository.create(
                str(file_path),
                file_path.name,
                result.cnpj_extraido,
                None,
                result.empresa_sugerida_nome,
                result.tipo_documento_sugerido,
                result.confianca,
                result.origem,
                result.motivo,
            )
            return ProcessedFileResult(
                file_path,
                "pendente_revisao",
                result.motivo or "Nao foi possivel identificar a empresa.",
            )

    def list_pendentes(self) -> list[dict]:
        return self.pendente_repository.list_pendentes()

    def resolve_pending_document(
        self,
        pendente_id: int,
        empresa_id: int,
        diretorio_documentos: str | None = None,
    ) -> None:
        with self.empresa_repository.db_manager.connect():
            pendente = self.pendente_repository.get_by_id(pendente_id)
            if not pendente or pendente["status"] != "pendente":
                raise ValidationError("Documento pendente nao encontrado.")

            empresa = self.empresa_repository.get_by_id(empresa_id)
            if not empresa:
                raise ValidationError("Empresa nao encontrada.")

            if diretorio_documentos:
                self.empresa_service.set_empresa_directory(empresa_id, diretorio_documentos)
                empresa = self.empresa_repository.get_by_id(empresa_id)

            diretorio = empresa.get("diretorio_documentos")
            if not diretorio:
                raise ValidationError("Selecione uma pasta de destino para a empresa antes de confirmar.")

            origem = Path(pendente["caminho_arquivo_original"])
            if not origem.exists():
                raise ValidationError("O arquivo original nao foi encontrado no disco.")

            destino_dir = Path(diretorio)
            try:
                destino_dir.mkdir(parents=True, exist_ok=True)
                destino = self._resolve_destination_path(destino_dir, origem)
                shutil.move(str(origem), str(destino))
            except OSError as exc:
                raise ValidationError(f"Nao foi possivel mover o arquivo: {exc}") from exc

            usuario_id = self.session_service.get_user_id() if self.session_service else None
            self.pendente_repository.mark_resolved(pendente_id, empresa_id, usuario_id)
            self._log(
                "DOCUMENTO_REVISADO_CONFIRMADO",
                "documento_pendente_revisao",
                pendente_id,
                (
                    f'Usuario {self._actor_name()} confirmou o documento "{pendente["nome_arquivo"]}" '
                    f'para a empresa "{empresa["nome_empresa"]}".'
                ),
                empresa_id=empresa_id,
                empresa_nome=empresa["nome_empresa"],
            )

    def ignore_pending_document(self, pendente_id: int) -> None:
        with self.empresa_repository.db_manager.connect():
            pendente = self.pendente_repository.get_by_id(pendente_id)
            if not pendente or pendente["status"] != "pendente":
                raise ValidationError("Documento pendente nao encontrado.")

            self.pendente_repository.mark_ignored(pendente_id)
            self._log(
                "DOCUMENTO_REVISADO_IGNORADO",
                "documento_pendente_revisao",
                pendente_id,
                f'Usuario {self._actor_name()} ignorou o documento "{pendente["nome_arquivo"]}" da fila de revisao.',
            )

    def _resolve_destination_path(self, directory: Path, source_path: Path) -> Path:
        candidate = directory / source_path.name
        if not candidate.exists():
            return candidate

        stem, suffix = source_path.stem, source_path.suffix
        counter = 1
        while True:
            candidate = directory / f"{stem} ({counter}){suffix}"
            if not candidate.exists():
                return candidate
            counter += 1

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
        empresa_id: int | None = None,
        empresa_nome: str | None = None,
    ) -> None:
        if self.audit_service:
            self.audit_service.log(
                acao,
                entidade,
                entidade_id,
                descricao,
                empresa_id=empresa_id,
                empresa_nome=empresa_nome,
            )
