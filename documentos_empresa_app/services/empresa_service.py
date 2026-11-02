from __future__ import annotations

from pathlib import Path
import re

from documentos_empresa_app.database.connection import IntegrityError
from documentos_empresa_app.database.repositories import EmpresaRepository
from documentos_empresa_app.services.audit_service import AuditService
from documentos_empresa_app.services.session_service import SessionService
from documentos_empresa_app.services.whatsapp_service import (
    format_whatsapp,
    normalize_grupo_link,
    normalize_whatsapp,
)
from documentos_empresa_app.utils.common import (
    MAX_COMPANY_OBSERVATION_LENGTH,
    ValidationError,
    normalize_delivery_methods,
)


class EmpresaService:
    def __init__(
        self,
        empresa_repository: EmpresaRepository,
        audit_service: AuditService | None = None,
        session_service: SessionService | None = None,
    ) -> None:
        self.empresa_repository = empresa_repository
        self.audit_service = audit_service
        self.session_service = session_service

    def list_empresas(self, active_only: bool = False) -> list[dict]:
        return self.empresa_repository.list_all(active_only=active_only)

    def get_empresa(self, empresa_id: int) -> dict:
        empresa = self.empresa_repository.get_by_id(empresa_id)
        if not empresa:
            raise ValidationError("Empresa nao encontrada.")
        return empresa

    def get_empresa_by_code(self, codigo_empresa, active_only: bool = False) -> dict | None:
        try:
            codigo = int(str(codigo_empresa).strip())
        except ValueError:
            return None
        return self.empresa_repository.get_by_code(codigo, active_only=active_only)

    def create_empresa(
        self,
        codigo_empresa,
        nome_empresa: str,
        email_contato: str | None = None,
        nome_contato: str | None = None,
        observacao: str | None = None,
        cnpj: str | None = None,
    ) -> int:
        codigo = self._parse_codigo(codigo_empresa)
        nome = self._normalize_name(nome_empresa, "O nome da empresa nao pode ficar vazio.")
        email = self._normalize_optional_email(email_contato)
        contato = self._normalize_optional_text(nome_contato)
        obs = self._normalize_observacao(observacao)
        cnpj_normalizado = self._normalize_optional_cnpj(cnpj)

        try:
            with self.empresa_repository.db_manager.connect():
                if self.empresa_repository.get_by_code(codigo):
                    raise ValidationError("Ja existe uma empresa cadastrada com esse codigo.")
                empresa_id = self.empresa_repository.create(
                    codigo,
                    nome,
                    None,
                    email,
                    contato,
                    obs,
                    None,
                    None,
                    None,
                    cnpj_normalizado,
                )
                self._log(
                    "CADASTRO_EMPRESA",
                    "empresa",
                    empresa_id,
                    self._build_company_description("cadastrou", nome, codigo, email, contato, obs),
                    empresa_id=empresa_id,
                    empresa_nome=nome,
                )
        except IntegrityError as exc:
            raise ValidationError("Nao foi possivel cadastrar a empresa.") from exc
        return empresa_id

    def update_empresa_nome(self, empresa_id: int, nome_empresa: str) -> None:
        empresa = self.get_empresa(empresa_id)
        self.update_empresa(
            empresa_id,
            nome_empresa,
            empresa.get("email_contato"),
            empresa.get("nome_contato"),
            empresa.get("observacao"),
            empresa.get("cnpj"),
        )

    def update_empresa(
        self,
        empresa_id: int,
        nome_empresa: str,
        email_contato: str | None = None,
        nome_contato: str | None = None,
        observacao: str | None = None,
        cnpj: str | None = None,
    ) -> None:
        nome = self._normalize_name(nome_empresa, "O nome da empresa nao pode ficar vazio.")
        email = self._normalize_optional_email(email_contato)
        contato = self._normalize_optional_text(nome_contato)
        obs = self._normalize_observacao(observacao)
        cnpj_normalizado = self._normalize_optional_cnpj(cnpj)

        try:
            with self.empresa_repository.db_manager.connect():
                empresa = self.get_empresa(empresa_id)
                self.empresa_repository.update_details(
                    empresa_id,
                    nome,
                    None,
                    email,
                    contato,
                    obs,
                    empresa.get("cobranca_inicio_dia"),
                    empresa.get("cobranca_fim_dia"),
                    empresa.get("cobranca_alerta_dias"),
                    cnpj_normalizado,
                )

                changes = []
                if empresa["nome_empresa"] != nome:
                    changes.append(f'nome: "{empresa["nome_empresa"]}" -> "{nome}"')
                # Email e nome de contato sao dado pessoal de uma pessoa fisica (LGPD) - o log
                # registra que o campo mudou, mas nao guarda o valor em si, pra nao deixar
                # dado pessoal preso pra sempre em texto livre e sem possibilidade de expurgo.
                if (empresa.get("email_contato") or "") != (email or ""):
                    changes.append("email de contato alterado")
                if (empresa.get("nome_contato") or "") != (contato or ""):
                    changes.append("nome de contato alterado")
                if (empresa.get("observacao") or "") != (obs or ""):
                    changes.append(f'observacao: "{empresa.get("observacao") or "-"}" -> "{obs or "-"}"')
                if (empresa.get("cnpj") or "") != (cnpj_normalizado or ""):
                    changes.append(f'cnpj: "{empresa.get("cnpj") or "-"}" -> "{cnpj_normalizado or "-"}"')

                if changes:
                    self._log(
                        "EDICAO_EMPRESA",
                        "empresa",
                        empresa_id,
                        (
                            f'Usuario {self._actor_name()} atualizou a empresa "{nome}". '
                            f'Alteracoes: {"; ".join(changes)}.'
                        ),
                        empresa_id=empresa_id,
                        empresa_nome=nome,
                    )
        except IntegrityError as exc:
            raise ValidationError("Nao foi possivel atualizar a empresa.") from exc

    def set_empresa_ativa(self, empresa_id: int, ativa: bool) -> None:
        ativo_int = 1 if ativa else 0
        with self.empresa_repository.db_manager.connect():
            empresa = self.get_empresa(empresa_id)
            self.empresa_repository.update_active(empresa_id, ativo_int)
            if empresa["ativa"] != ativo_int:
                acao = "REATIVACAO_EMPRESA" if ativa else "INATIVACAO_EMPRESA"
                descricao = (
                    f'Usuario {self._actor_name()} reativou a empresa "{empresa["nome_empresa"]}".'
                    if ativa
                    else f'Usuario {self._actor_name()} inativou a empresa "{empresa["nome_empresa"]}".'
                )
                self._log(
                    acao,
                    "empresa",
                    empresa_id,
                    descricao,
                    empresa_id=empresa_id,
                    empresa_nome=empresa["nome_empresa"],
                )

    def set_recebimento(
        self,
        empresa_id: int,
        canais_recebimento: str | list[str] | tuple[str, ...] | None,
        emails_origem_documentos: str | list[str] | tuple[str, ...] | None,
        instrucoes_busca: str | None,
    ) -> None:
        """Como a empresa envia os documentos: canais (Email, Onvio...), enderecos de email
        de onde os documentos chegam e instrucoes livres de onde/como procura-los."""
        canais = normalize_delivery_methods(canais_recebimento)
        if isinstance(emails_origem_documentos, (list, tuple)):
            emails_origem_documentos = ", ".join(emails_origem_documentos)
        emails = self._normalize_email_list(emails_origem_documentos)
        instrucoes = self._normalize_optional_text(instrucoes_busca)
        with self.empresa_repository.db_manager.connect():
            empresa = self.get_empresa(empresa_id)
            antes = (
                empresa.get("canais_recebimento") or "",
                empresa.get("emails_origem_documentos") or "",
                empresa.get("instrucoes_busca") or "",
            )
            if antes == (canais or "", emails or "", instrucoes or ""):
                return
            self.empresa_repository.update_reception(empresa_id, canais, emails, instrucoes)
            self._log(
                "EDICAO_EMPRESA",
                "empresa",
                empresa_id,
                (
                    f'Usuario {self._actor_name()} atualizou como a empresa "{empresa["nome_empresa"]}" '
                    f'envia os documentos (canais: {canais or "-"}).'
                ),
                empresa_id=empresa_id,
                empresa_nome=empresa["nome_empresa"],
            )

    def set_empresa_directory(self, empresa_id: int, diretorio_documentos: str | None) -> None:
        normalized_directory = self._normalize_optional_directory(diretorio_documentos)
        with self.empresa_repository.db_manager.connect():
            empresa = self.get_empresa(empresa_id)
            previous_directory = empresa.get("diretorio_documentos")
            if (previous_directory or "") == (normalized_directory or ""):
                return

            self.empresa_repository.update_directory(empresa_id, normalized_directory)
            previous_label = previous_directory or "-"
            current_label = normalized_directory or "-"
            self._log(
                "EDICAO_EMPRESA",
                "empresa",
                empresa_id,
                (
                    f'Usuario {self._actor_name()} atualizou a pasta vinculada da empresa '
                    f'"{empresa["nome_empresa"]}" de "{previous_label}" para "{current_label}".'
                ),
                empresa_id=empresa_id,
                empresa_nome=empresa["nome_empresa"],
            )

    def delete_empresa(self, empresa_id: int) -> None:
        with self.empresa_repository.db_manager.connect():
            empresa = self.get_empresa(empresa_id)
            self.empresa_repository.delete(empresa_id)
            self._log(
                "EXCLUSAO_EMPRESA",
                "empresa",
                empresa_id,
                f'Usuario {self._actor_name()} excluiu a empresa "{empresa["nome_empresa"]}".',
                empresa_id=empresa_id,
                empresa_nome=empresa["nome_empresa"],
            )

    def set_nao_contatar_mala_direta(self, empresa_id: int, nao_contatar: bool) -> None:
        with self.empresa_repository.db_manager.connect():
            empresa = self.get_empresa(empresa_id)
            if bool(empresa.get("nao_contatar_mala_direta")) == bool(nao_contatar):
                return
            self.empresa_repository.update_nao_contatar_mala_direta(empresa_id, nao_contatar)
            descricao = (
                f'Usuario {self._actor_name()} marcou a empresa "{empresa["nome_empresa"]}" '
                "para nao receber mala direta por email."
                if nao_contatar
                else (
                    f'Usuario {self._actor_name()} removeu o bloqueio de mala direta por email '
                    f'da empresa "{empresa["nome_empresa"]}".'
                )
            )
            self._log(
                "EDICAO_EMPRESA",
                "empresa",
                empresa_id,
                descricao,
                empresa_id=empresa_id,
                empresa_nome=empresa["nome_empresa"],
            )

    def set_whatsapp(self, empresa_id: int, whatsapp: str | None) -> str | None:
        """Grava o WhatsApp de cobranca da empresa (so digitos, com DDI). Vazio apaga."""
        numero = normalize_whatsapp(whatsapp)
        with self.empresa_repository.db_manager.connect():
            empresa = self.get_empresa(empresa_id)
            if (empresa.get("whatsapp") or None) == numero:
                return numero
            self.empresa_repository.update_whatsapp(empresa_id, numero)
            self._log(
                "EDICAO_EMPRESA",
                "empresa",
                empresa_id,
                (
                    f'Usuario {self._actor_name()} alterou o WhatsApp da empresa "{empresa["nome_empresa"]}" '
                    f'para {format_whatsapp(numero) or "(vazio)"}.'
                ),
                empresa_id=empresa_id,
                empresa_nome=empresa["nome_empresa"],
            )
        return numero

    def set_whatsapp_envios(self, empresa_id: int, usar: bool, grupo: str | None = None) -> None:
        """Autoriza (ou nao) mandar as cobrancas e malas diretas pelo WhatsApp da empresa e
        guarda o link do grupo, quando ela e atendida num grupo."""
        grupo = normalize_grupo_link(grupo)
        with self.empresa_repository.db_manager.connect():
            empresa = self.get_empresa(empresa_id)
            if usar and not (empresa.get("whatsapp") or grupo):
                raise ValidationError("Para enviar pelo WhatsApp, cadastre o número ou o link do grupo.")
            if bool(empresa.get("whatsapp_envios")) == bool(usar) and (empresa.get("whatsapp_grupo") or None) == grupo:
                return
            self.empresa_repository.update_whatsapp_envios(empresa_id, usar, grupo)
            descricao = (
                f'Usuario {self._actor_name()} '
                + ("autorizou" if usar else "desligou")
                + f' os envios por WhatsApp da empresa "{empresa["nome_empresa"]}"'
                + (" (grupo)" if grupo else "")
                + "."
            )
            self._log(
                "EDICAO_EMPRESA", "empresa", empresa_id, descricao,
                empresa_id=empresa_id, empresa_nome=empresa["nome_empresa"],
            )

    def clear_contact_info(self, empresa_id: int) -> None:
        """Remove email/nome de contato sem excluir o cadastro da empresa -
        atende ao direito ao esquecimento da LGPD para dados de uma pessoa
        fisica de contato, mantendo o historico fiscal/documental da empresa."""
        with self.empresa_repository.db_manager.connect():
            empresa = self.get_empresa(empresa_id)
            if not any(empresa.get(c) for c in ("email_contato", "nome_contato", "whatsapp", "whatsapp_grupo")):
                return
            self.empresa_repository.clear_contact_info(empresa_id)
            self._log(
                "EDICAO_EMPRESA",
                "empresa",
                empresa_id,
                (
                    f'Usuario {self._actor_name()} removeu os dados de contato (email/nome/WhatsApp) '
                    f'da empresa "{empresa["nome_empresa"]}" a pedido do titular.'
                ),
                empresa_id=empresa_id,
                empresa_nome=empresa["nome_empresa"],
            )

    def _parse_codigo(self, codigo_empresa) -> int:
        if isinstance(codigo_empresa, bool):
            raise ValidationError("O codigo da empresa deve ser um numero inteiro.")
        try:
            return int(str(codigo_empresa).strip())
        except ValueError:
            try:
                numeric_value = float(str(codigo_empresa).strip())
            except ValueError as exc:
                raise ValidationError("O codigo da empresa deve ser um numero inteiro.") from exc

            if not numeric_value.is_integer():
                raise ValidationError("O codigo da empresa deve ser um numero inteiro.")
            return int(numeric_value)

    def _normalize_name(self, value: str, error_message: str) -> str:
        normalized = str(value).strip()
        if not normalized:
            raise ValidationError(error_message)
        return normalized

    def _normalize_optional_email(self, email: str | None) -> str | None:
        normalized = self._normalize_optional_text(email)
        if not normalized:
            return None
        if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", normalized):
            raise ValidationError("Informe um email valido ou deixe o campo em branco.")
        return normalized

    def _normalize_email_list(self, value: str | None) -> str | None:
        """Aceita virgula, ponto-e-virgula ou quebra de linha como separador, valida cada
        email e remove duplicatas (sem diferenciar maiusculas)."""
        normalized_items: list[str] = []
        seen: set[str] = set()
        for raw_item in re.split(r"[,;\n]+", str(value or "")):
            email = self._normalize_optional_email(raw_item)
            if not email or email.casefold() in seen:
                continue
            seen.add(email.casefold())
            normalized_items.append(email)
        return ", ".join(normalized_items) if normalized_items else None

    def _normalize_optional_text(self, value: str | None) -> str | None:
        normalized = str(value or "").strip()
        return normalized or None

    def _normalize_observacao(self, value: str | None) -> str | None:
        normalized = self._normalize_optional_text(value)
        if normalized and len(normalized) > MAX_COMPANY_OBSERVATION_LENGTH:
            raise ValidationError(
                f"A observacao deve ter no maximo {MAX_COMPANY_OBSERVATION_LENGTH} caracteres."
            )
        return normalized

    def _normalize_optional_cnpj(self, value: str | None) -> str | None:
        # So remove a pontuacao de formatacao (. / - e espacos) - o formato novo do
        # CNPJ (Receita Federal, 2026) permite letras nas 12 primeiras posicoes, so os
        # 2 digitos verificadores finais continuam sempre numericos.
        cleaned = re.sub(r"[.\-/\s]", "", str(value or "")).upper()
        if not cleaned:
            return None
        if not re.fullmatch(r"[A-Z0-9]{12}\d{2}", cleaned):
            raise ValidationError(
                "O CNPJ deve ter 14 caracteres (letras ou numeros nas 12 primeiras posicoes e 2 "
                "numeros no final) ou ficar em branco."
            )
        return cleaned

    def _normalize_optional_directory(self, value: str | None) -> str | None:
        normalized = self._normalize_optional_text(value)
        if not normalized:
            return None
        return str(Path(normalized).expanduser())

    def _build_company_description(
        self,
        action_text: str,
        nome_empresa: str,
        codigo_empresa: int,
        email_contato: str | None,
        nome_contato: str | None,
        observacao: str | None = None,
    ) -> str:
        details = [f'Usuario {self._actor_name()} {action_text} a empresa "{nome_empresa}" de codigo {codigo_empresa}.']
        # Nao embutir o email/nome de contato em si no log (dado pessoal - LGPD), so
        # registrar que foram informados.
        if email_contato:
            details.append("Email de contato informado.")
        if nome_contato:
            details.append("Nome de contato informado.")
        if observacao:
            details.append(f"Observacao: {observacao}.")
        return " ".join(details)

    def _actor_name(self) -> str:
        if not self.session_service:
            return "Sistema"
        return self.session_service.get_username()

    def _log(
        self,
        acao: str,
        entidade: str,
        entidade_id: int,
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
