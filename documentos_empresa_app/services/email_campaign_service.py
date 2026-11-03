from __future__ import annotations

from dataclasses import dataclass, field

from documentos_empresa_app.database.repositories import EmpresaRepository
from documentos_empresa_app.services.session_service import SessionService
from documentos_empresa_app.utils.common import ValidationError
from documentos_empresa_app.utils.helpers import (
    load_mailing_campaign,
    open_bcc_email_draft,
    save_mailing_campaign,
    split_contact_emails,
)


@dataclass(slots=True)
class MailingCampaign:
    subject: str = ""
    body: str = ""
    empresa_ids: list[int] = field(default_factory=list)


class EmailCampaignService:
    """Monta um rascunho de email com todas as empresas selecionadas em copia
    oculta (BCC), usando o cliente de email padrao do usuario - nao envia nada
    por conta propria, so abre o rascunho ja pronto pra revisao e envio manual."""

    def __init__(self, session_service: SessionService, empresa_repository: EmpresaRepository) -> None:
        self.session_service = session_service
        self.empresa_repository = empresa_repository

    def get_campaign(self) -> MailingCampaign:
        self._ensure_admin()
        stored = load_mailing_campaign()
        empresa_ids = stored.get("empresa_ids")
        return MailingCampaign(
            subject=str(stored.get("subject") or ""),
            body=str(stored.get("body") or ""),
            empresa_ids=[int(value) for value in empresa_ids] if isinstance(empresa_ids, list) else [],
        )

    def save_campaign(self, subject: str, body: str, empresa_ids: list[int]) -> MailingCampaign:
        self._ensure_admin()
        save_mailing_campaign(
            {
                "subject": str(subject or "").strip(),
                "body": str(body or ""),
                "empresa_ids": [int(value) for value in empresa_ids],
            }
        )
        return self.get_campaign()

    def build_recipients(self, empresa_ids: list[int]) -> tuple[list[str], list[str], list[str]]:
        """Retorna (emails_validos_sem_duplicata, nomes_das_empresas_sem_email,
        nomes_das_empresas_que_pediram_para_nao_receber)."""
        self._ensure_admin()
        emails: list[str] = []
        missing: list[str] = []
        opted_out: list[str] = []
        seen: set[str] = set()
        for empresa_id in empresa_ids:
            empresa = self.empresa_repository.get_by_id(int(empresa_id))
            if not empresa:
                continue
            if empresa.get("nao_contatar_mala_direta"):
                opted_out.append(empresa["nome_empresa"])
                continue
            # A empresa pode ter mais de um email: todos entram na copia oculta.
            emails_empresa = split_contact_emails(empresa.get("email_contato"))
            if not emails_empresa:
                missing.append(empresa["nome_empresa"])
                continue
            for email in emails_empresa:
                if email.casefold() not in seen:
                    seen.add(email.casefold())
                    emails.append(email)
        return emails, missing, opted_out

    def open_draft(self, subject: str, body: str, empresa_ids: list[int]) -> dict:
        self._ensure_admin()
        normalized_subject = str(subject or "").strip()
        if not empresa_ids:
            raise ValidationError("Selecione ao menos uma empresa para o envio.")
        if not normalized_subject:
            raise ValidationError("Informe o assunto do email.")

        emails, missing, opted_out = self.build_recipients(empresa_ids)
        if not emails:
            raise ValidationError("Nenhuma das empresas selecionadas possui email de contato cadastrado.")

        open_bcc_email_draft(emails, normalized_subject, body)
        return {"recipient_count": len(emails), "missing_companies": missing, "opted_out_companies": opted_out}

    def _ensure_admin(self) -> None:
        if not self.session_service.is_admin():
            raise ValidationError("Apenas usuarios admin podem gerenciar a mala direta por email.")
