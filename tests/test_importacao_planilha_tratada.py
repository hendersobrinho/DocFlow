from __future__ import annotations

from datetime import date
from pathlib import Path
import tempfile
import unittest

from openpyxl import Workbook
from psycopg.conninfo import make_conninfo

from documentos_empresa_app.app_context import build_application_services

from tests.postgres_support import create_test_database_manager, get_test_database_url


class ImportacaoPlanilhaTratadaTests(unittest.TestCase):
    """Cadastro completo com as colunas novas: observacao do documento, regra do tipo e
    reimportacao sem duplicar."""

    def setUp(self) -> None:
        db_manager = create_test_database_manager(self)
        conninfo = make_conninfo(get_test_database_url(), options=f"-c search_path={db_manager.schema},public")
        self.services = build_application_services(conninfo)
        self.addCleanup(self.services.database_maintenance_service.db_manager.close)
        self.services.session_service.login(self.services.auth_service.authenticate("admin", "admin"))
        self.ano = date.today().year
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.arquivo = Path(tmp.name) / "tratada.xlsx"
        wb = Workbook()
        ws = wb.active
        meses = ["Janeiro", "Fevereiro", "Marco", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro",
                 "Outubro", "Novembro", "Dezembro"]
        ws.append(["Codigo", "Nome da empresa", "Email", "Contato", "Nome do documento", "Meio de recebimento",
                   "Tipo do documento", "Observacao", *[f"{m} {self.ano}" for m in meses],
                   "Observação do documento", "Regra do tipo"])
        vazio = [""] * 11
        ws.append([7, "Padaria", "fin@pao.com", "Ana", "Bradesco", "Email, Físico", "Extratos CC",
                   "Cliente só envia os extratos", "OK", *vazio, "C/C 3.502-5", "mensal"])
        ws.append(["", "", "", "", "CRM", "", "Anuidades", "", "OK", *vazio, "", "anual"])
        wb.save(self.arquivo)

    def test_imports_document_observation_rule_and_new_channel(self) -> None:
        resultado = self.services.import_service.import_cadastros_completos(str(self.arquivo))
        self.assertEqual((resultado["failed"], resultado["documents_imported"]), (0, 2), resultado["errors"])

        empresa = self.services.empresa_service.get_empresa_by_code(7, active_only=False)
        docs = {d["nome_documento"]: d for d in self.services.documento_service.list_documentos_empresa(empresa["id"])}
        self.assertEqual(docs["Bradesco"]["nome_tipo"], "Extratos CC")  # tipo e nome em campos separados
        self.assertEqual(docs["Bradesco"]["observacao"], "C/C 3.502-5")
        self.assertEqual(docs["CRM"]["regra_ocorrencia"], "anual_janeiro")
        meios = {m["nome_meio"] for m in self.services.delivery_method_service.list_methods()}
        self.assertIn("Físico", meios)

    def test_reimport_reuses_existing_documents(self) -> None:
        self.services.import_service.import_cadastros_completos(str(self.arquivo))
        de_novo = self.services.import_service.import_cadastros_completos(str(self.arquivo))

        self.assertEqual(de_novo["failed"], 0, de_novo["errors"])
        empresa = self.services.empresa_service.get_empresa_by_code(7, active_only=False)
        self.assertEqual(len(self.services.documento_service.list_documentos_empresa(empresa["id"])), 2)

    def test_reimport_never_overwrites_what_was_marked_in_the_system(self) -> None:
        self.services.import_service.import_cadastros_completos(str(self.arquivo))
        empresa = self.services.empresa_service.get_empresa_by_code(7, active_only=False)
        doc = next(d for d in self.services.documento_service.list_documentos_empresa(empresa["id"])
                   if d["nome_documento"] == "Bradesco")
        janeiro = next(p["id"] for p in self.services.periodo_service.list_periodos()
                       if p["ano"] == self.ano and p["mes"] == 1)
        self.services.status_service.update_status(doc["id"], janeiro, "Pendente")

        self.services.import_service.import_cadastros_completos(str(self.arquivo))  # planilha diz OK
        status = self.services.status_service.status_repository.get_by_document_and_period(doc["id"], janeiro)
        self.assertEqual(status["status"], "Pendente")

    def test_failed_first_row_does_not_send_next_rows_to_the_previous_company(self) -> None:
        from openpyxl import load_workbook

        wb = load_workbook(self.arquivo)
        ws = wb.active
        vazio = [""] * 11
        # Empresa 8: a primeira linha tem um status invalido; a segunda (sem codigo) e dela.
        # Empresa que ja existe e cuja linha falha continua recebendo as linhas seguintes.
        ws.append([8, "Clinica", "", "", "Sicoob", "Email", "Extratos CC", "", "ZZ", *vazio, "", "mensal"])
        ws.append(["", "", "", "", "Itaú", "Email", "Extratos CC", "", "OK", *vazio, "", "mensal"])
        wb.save(self.arquivo)

        resultado = self.services.import_service.import_cadastros_completos(str(self.arquivo))

        # A empresa nova e desfeita junto com a linha que falhou; a linha seguinte tambem
        # falha (pedindo o codigo) em vez de ir parar na Padaria.
        self.assertEqual(resultado["failed"], 2)
        padaria = self.services.empresa_service.get_empresa_by_code(7, active_only=False)
        nomes = {d["nome_documento"] for d in self.services.documento_service.list_documentos_empresa(padaria["id"])}
        self.assertNotIn("Itaú", nomes)

    def test_observation_is_kept_when_editing_without_it(self) -> None:
        self.services.import_service.import_cadastros_completos(str(self.arquivo))
        empresa = self.services.empresa_service.get_empresa_by_code(7, active_only=False)
        doc = next(d for d in self.services.documento_service.list_documentos_empresa(empresa["id"])
                   if d["nome_documento"] == "Bradesco")
        service = self.services.documento_service
        service.update_documento(doc["id"], doc["tipo_documento_id"], "Bradesco", ["Email"])
        self.assertEqual(service.get_documento(doc["id"])["observacao"], "C/C 3.502-5")
        service.update_documento(doc["id"], doc["tipo_documento_id"], "Bradesco", ["Email"], observacao="")
        self.assertIsNone(service.get_documento(doc["id"])["observacao"])


if __name__ == "__main__":
    unittest.main()
