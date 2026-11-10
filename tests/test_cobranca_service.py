from __future__ import annotations

from datetime import date
from pathlib import Path
import tempfile
import unittest

from psycopg.conninfo import make_conninfo

from documentos_empresa_app.app_context import build_application_services
from documentos_empresa_app.utils.common import ValidationError

from tests.postgres_support import create_test_database_manager, get_test_database_url


class CobrancaServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        db_manager = create_test_database_manager(self)
        conninfo = make_conninfo(get_test_database_url(), options=f"-c search_path={db_manager.schema},public")
        self.services = build_application_services(conninfo)
        self.addCleanup(self.services.database_maintenance_service.db_manager.close)
        self.services.session_service.login(self.services.auth_service.authenticate("admin", "admin"))

        self.ano = date.today().year
        self.services.periodo_service.generate_year(self.ano)
        self.periodos = {p["mes"]: p for p in self.services.periodo_service.list_periodos() if p["ano"] == self.ano}

        self.empresa_id = self.services.empresa_service.create_empresa(1, "Padaria Pao Quente", "fin@pao.com")
        tipo_id = self.services.tipo_service.get_or_create_tipo("Extratos CC")["id"]
        self.doc_itau = self.services.documento_service.create_documento(self.empresa_id, tipo_id, "Itau CC", ["Email"])
        self.doc_bb = self.services.documento_service.create_documento(self.empresa_id, tipo_id, "BB CC", ["Onvio"])
        self.cobranca = self.services.cobranca_service

    def test_second_charge_of_same_document_and_month_is_recobranca(self) -> None:
        janeiro = self.periodos[1]["id"]
        primeira = self.cobranca.registrar_cobranca(self.empresa_id, "Email", [(self.doc_itau, janeiro)])
        segunda = self.cobranca.registrar_cobranca(self.empresa_id, "WhatsApp", [(self.doc_itau, janeiro)])

        self.assertEqual(primeira["itens"][0]["tipo"], "Cobranca")
        self.assertEqual(segunda["itens"][0]["sequencia"], 2)
        self.assertEqual(segunda["itens"][0]["tipo"], "Recobranca")

        ficha = self.cobranca.ficha_empresa(self.empresa_id)
        itau = next(d for d in ficha["documentos"] if d["documento_id"] == self.doc_itau)
        self.assertEqual((itau["cobrancas"], itau["recobrancas"]), (1, 1))
        self.assertEqual(ficha["totais"]["contatos"], 2)

    def test_charge_without_items_covers_everything_still_open(self) -> None:
        resultado = self.cobranca.registrar_cobranca(self.empresa_id, "Email", destinatario="fin@pao.com")

        self.assertTrue(resultado["itens"])
        self.assertEqual({item["documento_id"] for item in resultado["itens"]}, {self.doc_itau, self.doc_bb})

    def test_verification_marks_found_documents_as_received(self) -> None:
        janeiro = self.periodos[1]["id"]
        resultado = self.cobranca.registrar_verificacao(
            self.empresa_id,
            ["Email", "Onvio"],
            [
                {"documento_id": self.doc_itau, "periodo_id": janeiro, "encontrado": True,
                 "onde": "Email de fin@pao.com, assunto Extrato janeiro"},
                {"documento_id": self.doc_bb, "periodo_id": janeiro, "encontrado": False},
            ],
            resumo="Itau chegou por email; BB ainda nao apareceu no Onvio.",
        )

        self.assertEqual(resultado["itens"][0]["status_aplicado"], "Recebido")
        status = self.services.status_service.build_control_view(
            self.empresa_id, janeiro, janeiro
        )
        statuses = {doc["nome_documento"]: doc["cells"][0].get("status") for g in status["groups"] for doc in g["documentos"]}
        self.assertEqual(statuses["Itau CC"], "Recebido")
        self.assertEqual(statuses["BB CC"], "Pendente")  # procurou e nao achou: fica pendente

        registro = self.cobranca.registro_documento(self.doc_itau)
        janeiro_label = f"01/{self.ano}"
        competencia = next(c for c in registro["competencias"] if c["competencia"] == janeiro_label)
        self.assertEqual(competencia["status"], "Recebido")
        self.assertIn("assunto Extrato", competencia["verificacoes"][0]["onde"])

        ficha = self.cobranca.ficha_empresa(self.empresa_id)
        self.assertEqual(ficha["historico"][0]["tipo_evento"], "verificacao")

    def test_rejects_document_from_another_company(self) -> None:
        outra_id = self.services.empresa_service.create_empresa(2, "Outra Empresa")
        with self.assertRaises(ValidationError):
            self.cobranca.registrar_cobranca(outra_id, "Email", [(self.doc_itau, self.periodos[1]["id"])])

    def test_ficha_joins_company_channels_with_each_document_channel(self) -> None:
        recebimento = self.cobranca.ficha_empresa(self.empresa_id)["recebimento"]
        # Nada marcado na empresa: os canais vem dos documentos do cadastro.
        self.assertEqual(sorted(recebimento["canais"]), ["Email", "Onvio"])
        self.assertEqual(recebimento["canais_dos_documentos"], {"Email": ["Itau CC"], "Onvio": ["BB CC"]})
        self.assertEqual(recebimento["email_contato"], "fin@pao.com")

        self.services.empresa_service.set_recebimento(self.empresa_id, ["WhatsApp", "Email"], None, None)
        recebimento = self.cobranca.ficha_empresa(self.empresa_id)["recebimento"]
        self.assertEqual(recebimento["canais"][:2], ["WhatsApp", "Email"])  # os da empresa primeiro
        self.assertIn("Onvio", recebimento["canais"])

    def test_company_reception_settings_are_normalized(self) -> None:
        self.services.empresa_service.set_recebimento(
            self.empresa_id,
            ["Email", "Onvio"],
            "Fin@Pao.com; contador@pao.com, fin@pao.com",
            "  Procurar no Onvio > Bancos  ",
        )
        empresa = self.services.empresa_service.get_empresa(self.empresa_id)
        self.assertEqual(empresa["canais_recebimento"], "Email, Onvio")
        self.assertEqual(empresa["emails_origem_documentos"], "Fin@Pao.com, contador@pao.com")
        self.assertEqual(empresa["instrucoes_busca"], "Procurar no Onvio > Bancos")

    def test_queue_shows_how_many_times_each_document_was_charged(self) -> None:
        janeiro = self.periodos[1]["id"]
        self.cobranca.registrar_cobranca(self.empresa_id, "Email", [(self.doc_itau, janeiro)])
        fila = self.cobranca.fila()
        empresa = next(item for item in fila if item["empresa_id"] == self.empresa_id)
        itau_janeiro = next(
            d for d in empresa["documentos"] if d["documento_id"] == self.doc_itau and d["periodo_id"] == janeiro
        )
        self.assertEqual(itau_janeiro["vezes_cobrado"], 1)

    def test_backup_keeps_collection_history(self) -> None:
        janeiro = self.periodos[1]["id"]
        self.cobranca.registrar_cobranca(self.empresa_id, "Email", [(self.doc_itau, janeiro)])
        with tempfile.TemporaryDirectory() as tmp:
            backup = Path(tmp) / "historico.dfbak"
            self.services.database_maintenance_service.create_backup(backup)
            self.cobranca.registrar_cobranca(self.empresa_id, "Email", [(self.doc_itau, janeiro)])
            self.services.database_maintenance_service.restore_backup(backup)
        self.assertEqual(len(self.cobranca.listar_cobrancas(empresa_id=self.empresa_id)), 1)
        nova = self.cobranca.registrar_cobranca(self.empresa_id, "Email", [(self.doc_itau, janeiro)])
        self.assertEqual(nova["itens"][0]["sequencia"], 2)


if __name__ == "__main__":
    unittest.main()
