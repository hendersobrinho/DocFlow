from __future__ import annotations

from datetime import date
import unittest

from psycopg.conninfo import make_conninfo

from documentos_empresa_app.app_context import build_application_services
from documentos_empresa_app.services.email_sender_service import MAX_DESTINATARIOS_POR_EMAIL, EmailSenderService
from documentos_empresa_app.services.envio_programado_service import data_de_envio, parse_meses, split_emails
from documentos_empresa_app.services.whatsapp_service import (
    PROVEDOR_CLOUD_API,
    WhatsAppService,
    build_link,
    format_whatsapp,
    normalize_whatsapp,
)
from documentos_empresa_app.utils.common import ValidationError

from tests.postgres_support import create_test_database_manager, get_test_database_url


class EnvioProgramadoHelpersTests(unittest.TestCase):
    def test_parse_meses_accepts_lists_text_and_presets(self) -> None:
        self.assertEqual(parse_meses("12, 3;6 9"), [3, 6, 9, 12])
        self.assertEqual(parse_meses("trimestral"), [3, 6, 9, 12])
        self.assertEqual(parse_meses([1, 1, 2]), [1, 2])
        with self.assertRaises(ValidationError):
            parse_meses([13])
        with self.assertRaises(ValidationError):
            parse_meses([])

    def test_day_31_falls_back_to_last_day_of_month(self) -> None:
        self.assertEqual(data_de_envio(2026, 2, 31), date(2026, 2, 28))
        self.assertEqual(data_de_envio(2026, 6, 31), date(2026, 6, 30))

    def test_split_emails_ignores_noise_and_duplicates(self) -> None:
        self.assertEqual(split_emails("a@x.com; B@y.com.br, a@X.com (financeiro)"), ["a@x.com", "B@y.com.br"])


class WhatsAppHelpersTests(unittest.TestCase):
    def test_normalizes_brazilian_numbers(self) -> None:
        self.assertEqual(normalize_whatsapp("(27) 99999-8888"), "5527999998888")
        self.assertEqual(normalize_whatsapp("+55 27 3333-4444"), "552733334444")
        self.assertIsNone(normalize_whatsapp("  "))
        with self.assertRaises(ValidationError):
            normalize_whatsapp("1234")
        self.assertEqual(format_whatsapp("5527999998888"), "+55 (27) 99999-8888")

    def test_link_carries_the_message(self) -> None:
        self.assertEqual(build_link("5527999998888", "Olá, tudo bem?"), "https://wa.me/5527999998888?text=Ol%C3%A1%2C%20tudo%20bem%3F")

    def test_without_api_returns_link_and_with_api_sends(self) -> None:
        sem_api = WhatsAppService(settings_loader=lambda: {"provedor": "link", "phone_number_id": "", "token": "", "api_version": "v21.0"})
        self.assertEqual(sem_api.enviar("27999998888", "oi")["link"], "https://wa.me/5527999998888?text=oi")

        enviados = []

        class FakeSender:
            def __init__(self, phone_number_id, token, api_version) -> None:
                self.credenciais = (phone_number_id, token)

            def send_text(self, numero, mensagem):
                enviados.append((numero, mensagem))
                return {"messages": [{"id": "wamid.1"}]}

        com_api = WhatsAppService(
            settings_loader=lambda: {"provedor": PROVEDOR_CLOUD_API, "phone_number_id": "123", "token": "t", "api_version": "v21.0"},
            sender_factory=FakeSender,
        )
        resultado = com_api.enviar("(27) 99999-8888", "oi")
        self.assertTrue(resultado["enviado"])
        self.assertEqual(resultado["mensagem_id"], "wamid.1")
        self.assertEqual(enviados, [("5527999998888", "oi")])


class EnvioProgramadoServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        db_manager = create_test_database_manager(self)
        conninfo = make_conninfo(get_test_database_url(), options=f"-c search_path={db_manager.schema},public")
        self.services = build_application_services(conninfo)
        self.addCleanup(self.services.database_maintenance_service.db_manager.close)
        self.services.session_service.login(self.services.auth_service.authenticate("admin", "admin"))
        self.services.periodo_service.generate_year(2026)

        # Tipo padrao do sistema (trimestral). O envio em si usa os meses da propria regra.
        tipo_id = self.services.tipo_service.get_or_create_tipo("Informe de Rendimentos")["id"]
        self.tipo_id = tipo_id
        self.empresas = {}
        for codigo, nome, email in ((1, "Padaria", "fin@pao.com"), (2, "Oficina", None), (3, "Mercado", "m@m.com")):
            empresa_id = self.services.empresa_service.create_empresa(codigo, nome, email_contato=email, nome_contato="Ana")
            documento_id = self.services.documento_service.create_documento(empresa_id, tipo_id, "Informe Bradesco")
            self.empresas[codigo] = (empresa_id, documento_id)

        self.envio = self.services.envio_programado_service.criar(
            {
                "nome": "Informe trimestral",
                "tipo_documento_id": tipo_id,
                "meses": "trimestral",
                "dia_envio": 5,
                "assunto": "Informe {competencia} - {empresa}",
                "corpo": "Olá {contato},\nFaltam:\n{documentos}\n{campo_desconhecido}",
            }
        )

    def _marcar(self, codigo: int, status: str) -> None:
        periodo = next(p for p in self.services.periodo_service.list_periodos() if (p["ano"], p["mes"]) == (2026, 6))
        self.services.status_service.update_status(self.empresas[codigo][1], periodo["id"], status)

    def test_competence_is_charged_in_the_following_month(self) -> None:
        servico = self.services.envio_programado_service
        # Competencia 06 (informe do 2o trimestre) fica pronta no fim de junho: cobra em julho.
        self.assertEqual(servico.a_enviar(date(2026, 6, 20)), [])
        self.assertEqual(servico.a_enviar(date(2026, 7, 4)), [])
        itens = servico.a_enviar(date(2026, 7, 5))
        self.assertEqual({item["codigo_empresa"] for item in itens}, {1, 2, 3})
        self.assertEqual({item["competencia"] for item in itens}, {"06/2026"})
        self.assertEqual(servico.proximo_envio(self.envio, date(2026, 7, 6)), (date(2026, 10, 5), (2026, 9)))
        # Competencia 12 vira o ano: cobrada em janeiro.
        self.assertEqual(servico.proximo_envio(self.envio, date(2026, 11, 2)), (date(2027, 1, 5), (2026, 12)))
        self.assertEqual(self.envio["proxima_competencia"] is not None, True)

    def test_renders_text_and_flags_companies_without_email(self) -> None:
        itens = {item["codigo_empresa"]: item for item in self.services.envio_programado_service.a_enviar(date(2026, 7, 10))}
        self.assertEqual(itens[1]["assunto"], "Informe 06/2026 - Padaria")
        self.assertIn("- Informe Bradesco", itens[1]["corpo"])
        self.assertIn("{campo_desconhecido}", itens[1]["corpo"])
        self.assertEqual(itens[1]["destinatarios"], ["fin@pao.com"])
        self.assertTrue(itens[2]["sem_email"])
        self.assertTrue(itens[2]["sem_contato"])
        self.assertEqual(itens[1]["canal"], "email")

    def test_skips_received_and_already_sent(self) -> None:
        self._marcar(3, "Recebido")
        servico = self.services.envio_programado_service
        resultado = servico.registrar(self.envio["id"], self.empresas[1][0], (2026, 6), "enviado", ["fin@pao.com"])
        self.assertTrue(resultado["registrado"])

        codigos = {item["codigo_empresa"] for item in servico.a_enviar(date(2026, 7, 10))}
        self.assertEqual(codigos, {2})
        de_novo = servico.registrar(self.envio["id"], self.empresas[1][0], (2026, 6), "enviado")
        self.assertFalse(de_novo["registrado"])
        self.assertEqual(len(servico.historico()), 1)

    def test_failure_needs_reason_and_keeps_item_due(self) -> None:
        servico = self.services.envio_programado_service
        with self.assertRaises(ValidationError):
            servico.registrar(self.envio["id"], self.empresas[2][0], (2026, 6), "falhou")
        servico.registrar(self.envio["id"], self.empresas[2][0], (2026, 6), "falhou", detalhe="sem email")
        self.assertIn(2, {item["codigo_empresa"] for item in servico.a_enviar(date(2026, 7, 10))})

    def test_same_month_option_and_mailing_to_all(self) -> None:
        servico = self.services.envio_programado_service
        servico.atualizar(self.envio["id"], {"enviar_em": "mesmo_mes", "meses": [7]})
        self.assertEqual(servico.a_enviar(date(2026, 7, 5))[0]["competencia"], "07/2026")

        aviso = servico.criar(
            {"nome": "Aviso", "meses": [7], "enviar_em": "mesmo_mes", "dia_envio": 1, "assunto": "Aviso", "corpo": "Recesso {ano}"}
        )
        self.assertEqual(aviso["publico_label"], "Mala direta: todas as empresas ativas")
        itens = servico.a_enviar(date(2026, 7, 1), envio_id=aviso["id"])
        self.assertEqual(len(itens), 3)
        self.assertEqual(itens[0]["documentos"], [])

    def test_mailing_to_chosen_companies_respects_opt_out(self) -> None:
        servico = self.services.envio_programado_service
        padaria, oficina, mercado = (self.empresas[c][0] for c in (1, 2, 3))
        self.services.empresa_service.set_nao_contatar_mala_direta(mercado, True)
        mala = servico.criar(
            {
                "nome": "Mala",
                "meses": "mensal",
                "dia_envio": 1,
                "empresa_ids": [padaria, mercado],
                "assunto": "Novidade",
                "corpo": "Oi {empresa}",
            }
        )
        self.assertEqual(mala["empresa_ids_lista"], sorted([padaria, mercado]))
        itens = servico.a_enviar(date(2026, 8, 1), envio_id=mala["id"])
        self.assertEqual([item["empresa_id"] for item in itens], [padaria])
        with self.assertRaises(ValidationError):
            servico.atualizar(mala["id"], {"empresa_ids": [999999]})
        self.assertNotIn(oficina, mala["empresa_ids_lista"])

    def test_whatsapp_only_for_companies_that_allowed_it(self) -> None:
        servico = self.services.envio_programado_service
        empresas = self.services.empresa_service
        padaria, oficina, mercado = (self.empresas[c][0] for c in (1, 2, 3))
        empresas.set_whatsapp(padaria, "(27) 99999-8888")  # tem numero, mas nao liberou: email
        empresas.set_whatsapp(oficina, "27 98888-7777")
        empresas.set_whatsapp_envios(oficina, True)
        empresas.set_whatsapp_envios(mercado, True, "chat.whatsapp.com/AbCdEfGhIjKlMnOp")  # atendida num grupo
        with self.assertRaises(ValidationError):
            empresas.set_whatsapp_envios(padaria, True, "https://exemplo.com/grupo")
        servico.atualizar(self.envio["id"], {"corpo_whatsapp": "Oi {contato}! Faltam:\n{documentos}"})

        itens = {item["codigo_empresa"]: item for item in servico.a_enviar(date(2026, 7, 10))}
        self.assertEqual({c: itens[c]["canal"] for c in itens}, {1: "email", 2: "whatsapp", 3: "whatsapp"})
        self.assertTrue(itens[2]["whatsapp_link"].startswith("https://wa.me/5527988887777?text=Oi%20Ana"))
        self.assertEqual(itens[2]["mensagem_whatsapp"], "Oi Ana! Faltam:\n- Informe Bradesco")
        self.assertIn("{campo_desconhecido}", itens[1]["corpo"])  # o email continua com o texto dele
        self.assertTrue(itens[3]["whatsapp_e_grupo"])
        self.assertEqual(itens[3]["whatsapp_link"], "https://chat.whatsapp.com/AbCdEfGhIjKlMnOp")
        self.assertFalse(itens[2]["sem_contato"])

        servico.registrar(self.envio["id"], oficina, (2026, 7 - 1), "enviado", "+55 (27) 98888-7777", canal="whatsapp")
        self.assertEqual(servico.historico()[0]["canal"], "whatsapp")
        so_email = servico.atualizar(self.envio["id"], {"canal": "email"})
        self.assertEqual(so_email["canal"], "email")
        self.assertEqual({i["canal"] for i in servico.a_enviar(date(2026, 7, 10))}, {"email"})
        conferencia = servico.conferencia(self.envio["id"], 2026, 6)
        self.assertEqual(conferencia["por_canal"], {"email": 2, "whatsapp": 0})

    def test_companies_can_be_taken_out_of_a_document_rule(self) -> None:
        servico = self.services.envio_programado_service
        padaria, oficina, _mercado = (self.empresas[c][0] for c in (1, 2, 3))
        envio = servico.remover_empresas(self.envio["id"], [padaria])
        self.assertEqual(envio["empresa_ids_excluidas_lista"], [padaria])
        self.assertIn("menos 1", envio["publico_label"])
        self.assertEqual({i["codigo_empresa"] for i in servico.a_enviar(date(2026, 7, 10))}, {2, 3})
        linhas = {l["codigo_empresa"]: l for l in servico.conferencia(self.envio["id"], 2026, 6)["linhas"]}
        self.assertEqual((linhas[1]["situacao"], linhas[1]["motivo"]), ("fora", "Tirada deste envio"))
        # Tirar todas e possivel num envio por tipo (a lista vem do tipo); incluir devolve.
        servico.remover_empresas(self.envio["id"], [oficina])
        envio = servico.incluir_empresas(self.envio["id"], [padaria, oficina])
        self.assertEqual(envio["empresa_ids_excluidas_lista"], [])

    def test_message_templates_can_be_saved_and_loaded(self) -> None:
        servico = self.services.envio_programado_service
        modelo = servico.salvar_modelo("Cobranca informe", "Informe {competencia}", "Olá {contato}", "Oi {contato}")
        self.assertEqual(modelo["corpo_whatsapp"], "Oi {contato}")
        servico.salvar_modelo("cobranca informe", None, "Texto novo")  # mesmo nome: substitui
        modelos = servico.listar_modelos()
        self.assertEqual([(m["nome"], m["corpo"]) for m in modelos], [("Cobranca informe", "Texto novo")])
        with self.assertRaises(ValidationError):
            servico.salvar_modelo("Vazio", None, "  ")
        servico.excluir_modelo(modelos[0]["id"])
        self.assertEqual(servico.listar_modelos(), [])

    def test_sends_emails_through_the_office_login(self) -> None:
        servico = self.services.envio_programado_service
        enviados = []

        class FakeSmtp:
            def __init__(self, recusar=()) -> None:
                self.recusar = recusar

            def send_message(self, mensagem, to_addrs):
                if set(to_addrs) & set(self.recusar):
                    raise __import__("smtplib").SMTPRecipientsRefused({to_addrs[0]: (550, b"no")})
                enviados.append((mensagem["To"], mensagem["Subject"], list(to_addrs), "Bcc" in mensagem))

            def quit(self):
                pass

        settings = {
            "host": "smtp.exemplo.com",
            "porta": 587,
            "seguranca": "starttls",
            "usuario": "envios@escritorio.com",
            "senha": "x",
            "remetente_nome": "Escritorio",
            "remetente_email": "envios@escritorio.com",
        }
        sender = EmailSenderService(settings_loader=lambda: settings, connect=lambda s: FakeSmtp(recusar=["m@m.com"]))
        resultado = servico.enviar_emails(self.envio["id"], 2026, 6, sender)
        # Padaria vai; Mercado e recusado (fica como falha); Oficina nao tem email.
        self.assertEqual((resultado["mensagens"], resultado["enviadas"], resultado["empresas"]), (2, 1, 1))
        self.assertEqual(len(resultado["falhas"]), 1)
        self.assertEqual(enviados, [("fin@pao.com", "Informe 06/2026 - Padaria", ["fin@pao.com"], False)])
        historico = {h["codigo_empresa"]: h["status"] for h in servico.historico(self.envio["id"])}
        self.assertEqual(historico, {1: "enviado", 3: "falhou"})
        # Ja enviado nao sai de novo.
        enviados.clear()
        sender = EmailSenderService(settings_loader=lambda: settings, connect=lambda s: FakeSmtp())
        self.assertEqual(servico.enviar_emails(self.envio["id"], 2026, 6, sender)["enviadas"], 1)
        self.assertEqual([e[2] for e in enviados], [["m@m.com"]])

        # Copia oculta grande vira varios emails, sem mostrar a lista no cabecalho.
        partes = EmailSenderService._partes(
            {"para": [], "cco": [f"c{i}@x.com" for i in range(MAX_DESTINATARIOS_POR_EMAIL + 5)], "assunto": "a", "corpo": "b"},
            "envios@escritorio.com",
        )
        self.assertEqual([len(p["cco"]) for p in partes], [MAX_DESTINATARIOS_POR_EMAIL, 5])
        self.assertEqual(partes[0]["para"], ["envios@escritorio.com"])

    def test_conference_explains_who_receives_and_why(self) -> None:
        servico = self.services.envio_programado_service
        self._marcar(3, "Recebido")
        servico.registrar(self.envio["id"], self.empresas[1][0], (2026, 6), "enviado", ["fin@pao.com"])
        conferencia = servico.conferencia(self.envio["id"], 2026, 6)
        situacoes = {linha["codigo_empresa"]: linha["situacao"] for linha in conferencia["linhas"]}
        self.assertEqual(situacoes, {1: "ja_recebeu", 2: "sem_contato", 3: "ja_entregou"})
        self.assertEqual(conferencia["data_envio"], "2026-07-05")
        self.assertEqual(conferencia["resumo"]["ja_entregou"], 1)
        self.assertIn((2026, 6), servico.competencias_para_conferir(self.envio, date(2026, 7, 1)))

    def test_bcc_mailing_is_one_email_to_the_office(self) -> None:
        servico = self.services.envio_programado_service
        padaria, oficina, mercado = (self.empresas[c][0] for c in (1, 2, 3))
        mala = servico.criar(
            {
                "nome": "Distribuicao de lucros",
                "modo": "cco",
                "email_para": "Escritorio <contato@escritorio.com>",
                "empresa_ids": [padaria, oficina],
                "meses": "mensal",
                "dia_envio": 5,
                "assunto": "Lucros {competencia}",
                "corpo": "Prezados, segue a competencia {competencia}. {empresa}",
            }
        )
        self.assertEqual((mala["canal"], mala["email_para"]), ("automatico", "contato@escritorio.com"))
        # Outubro cobra a competencia de setembro.
        itens = servico.a_enviar(date(2026, 10, 5), envio_id=mala["id"])
        self.assertEqual(len(itens), 1)
        item = itens[0]
        self.assertEqual((item["para"], item["cco"], item["competencia"]), ("contato@escritorio.com", ["fin@pao.com"], "09/2026"))
        self.assertEqual(item["assunto"], "Lucros 09/2026")
        self.assertIn("{empresa}", item["corpo"])  # no email unico nao ha empresa
        self.assertEqual(item["empresas_sem_email"], ["2 - Oficina"])

        # Quem liberou o WhatsApp sai da copia oculta e recebe a mensagem dele no WhatsApp.
        self.services.empresa_service.set_whatsapp(oficina, "27 98888-7777")
        self.services.empresa_service.set_whatsapp_envios(oficina, True)
        itens = servico.a_enviar(date(2026, 10, 5), envio_id=mala["id"])
        self.assertEqual([(i["modo"], i["canal"]) for i in itens], [("cco", "email"), ("individual", "whatsapp")])
        self.assertEqual(itens[0]["empresas_sem_email"], [])
        self.assertIn("Oficina", itens[1]["mensagem_whatsapp"])

        servico.incluir_empresas(mala["id"], [mercado])
        conferencia = servico.conferencia(mala["id"], 2026, 9)
        self.assertEqual(conferencia["resumo"]["vai_receber"], 3)
        self.assertEqual(conferencia["por_canal"], {"email": 2, "whatsapp": 1})
        self.assertEqual(servico.registrar_mala_direta(mala["id"], (2026, 9), "enviado")["empresas"], 2)
        self.assertEqual([i["canal"] for i in servico.a_enviar(date(2026, 10, 5), envio_id=mala["id"])], ["whatsapp"])

        servico.remover_empresas(mala["id"], [padaria, mercado])
        with self.assertRaises(ValidationError):
            servico.remover_empresas(mala["id"], [oficina])
        with self.assertRaises(ValidationError):
            servico.atualizar(mala["id"], {"tipo_documento_id": self.tipo_id})

    def test_type_used_by_rule_cannot_be_deleted(self) -> None:
        for _empresa_id, documento_id in self.empresas.values():
            self.services.documento_service.delete_documento(documento_id)
        with self.assertRaises(ValidationError):
            self.services.tipo_service.delete_tipo(self.tipo_id)
        self.services.envio_programado_service.excluir(self.envio["id"])
        self.services.tipo_service.delete_tipo(self.tipo_id)


if __name__ == "__main__":
    unittest.main()
