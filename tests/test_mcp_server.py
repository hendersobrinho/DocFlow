from __future__ import annotations

import asyncio
import unittest

from psycopg.conninfo import make_conninfo

try:
    from mcp.server.mcpserver.exceptions import ToolError

    from docflow_mcp import server as docflow_server
except ImportError:  # pragma: no cover - depende do requirements-mcp.txt
    docflow_server = None

from documentos_empresa_app.app_context import build_application_services

from tests.postgres_support import create_test_database_manager, get_test_database_url


@unittest.skipIf(docflow_server is None, "pacote mcp nao instalado (requirements-mcp.txt)")
class DocflowMcpServerTests(unittest.TestCase):
    def setUp(self) -> None:
        db_manager = create_test_database_manager(self)
        conninfo = make_conninfo(get_test_database_url(), options=f"-c search_path={db_manager.schema},public")
        services = build_application_services(conninfo)
        services.session_service.login(services.auth_service.authenticate("admin", "admin"))
        self.addCleanup(services.database_maintenance_service.db_manager.close)

        self.previous_services = docflow_server._services
        docflow_server._services = services
        self.addCleanup(setattr, docflow_server, "_services", self.previous_services)
        self.services = services

    def call(self, name: str, **arguments):
        result = asyncio.run(docflow_server.mcp.call_tool(name, arguments))
        self.assertFalse(result.is_error, result.content)
        structured = result.structured_content
        if isinstance(structured, dict) and set(structured) == {"result"}:
            return structured["result"]
        return structured

    def call_error(self, name: str, **arguments) -> str:
        with self.assertRaises(ToolError) as ctx:
            asyncio.run(docflow_server.mcp.call_tool(name, arguments))
        return str(ctx.exception)

    def test_lists_read_and_write_tools(self) -> None:
        tools = asyncio.run(docflow_server.mcp.list_tools())
        names = {tool.name for tool in tools}
        self.assertTrue({"panorama", "cadastrar_empresa", "marcar_status", "excluir_empresa"} <= names)
        panorama = next(tool for tool in tools if tool.name == "panorama")
        excluir = next(tool for tool in tools if tool.name == "excluir_empresa")
        self.assertTrue(panorama.annotations.read_only_hint)
        self.assertTrue(excluir.annotations.destructive_hint)

    def test_full_flow_company_document_status(self) -> None:
        self.call("gerar_periodos_ano", ano=2026)
        empresa = self.call("cadastrar_empresa", codigo_empresa=10, nome_empresa="Empresa MCP")
        self.assertEqual(empresa["nome_empresa"], "Empresa MCP")

        documento = self.call(
            "cadastrar_documento",
            codigo_empresa=10,
            tipo="extratos cc",
            nome_documento="Itau CC",
            meios_recebimento=["Email"],
        )
        self.call("marcar_status", documento_ids=[documento["documento_id"]], competencia="03/2026", status="Recebido")

        controle = self.call("controle_empresa", codigo_empresa=10, competencia_inicial="03/2026")
        self.assertEqual(controle["documentos"][0]["status"], {"03/2026": "Recebido"})

        panorama = self.call("panorama", competencia="03/2026")
        linha = next(row for row in panorama["empresas"] if row["codigo_empresa"] == 10)
        self.assertEqual(linha["recebidos"], 1)

        logs = self.call("listar_logs", limite=5)
        self.assertTrue(any(log["acao"] == "ALTERACAO_STATUS" for log in logs))

    def test_business_errors_reach_the_client_with_their_message(self) -> None:
        self.call("cadastrar_empresa", codigo_empresa=11, nome_empresa="Empresa A")
        message = self.call_error("cadastrar_empresa", codigo_empresa=11, nome_empresa="Empresa B")
        self.assertIn("Ja existe uma empresa", message)
        self.assertIn("nao existe", self.call_error("panorama", competencia="05/2031"))

    def test_partial_update_keeps_other_fields(self) -> None:
        self.call("cadastrar_empresa", codigo_empresa=12, nome_empresa="Empresa C", email_contato="a@b.com")
        empresa = self.call("atualizar_empresa", codigo_empresa=12, nome_empresa="Empresa C Renomeada")
        self.assertEqual(empresa["nome_empresa"], "Empresa C Renomeada")
        self.assertEqual(empresa["email_contato"], "a@b.com")

    def test_destructive_tools_require_confirmation(self) -> None:
        self.call("cadastrar_empresa", codigo_empresa=13, nome_empresa="Empresa D")
        self.assertIn("confirmar=true", self.call_error("excluir_empresa", codigo_empresa=13))
        self.assertEqual(len(self.call("listar_empresas", somente_ativas=False)), 1)

        self.call("excluir_empresa", codigo_empresa=13, confirmar=True)
        self.assertEqual(self.call("listar_empresas", somente_ativas=False), [])

    def test_collection_routine_verify_then_charge_then_recharge(self) -> None:
        self.call("gerar_periodos_ano", ano=2026)
        self.call("cadastrar_empresa", codigo_empresa=20, nome_empresa="Empresa Rotina", email_contato="fin@rotina.com")
        empresa = self.call(
            "definir_recebimento_empresa",
            codigo_empresa=20,
            canais_recebimento=["Email", "Onvio"],
            emails_origem_documentos=["docs@rotina.com"],
            instrucoes_busca="Assunto 'Extrato'; Onvio > Bancos",
        )
        self.assertEqual(empresa["canais_recebimento"], "Email, Onvio")
        itau = self.call("cadastrar_documento", codigo_empresa=20, tipo="Extratos CC", nome_documento="Itau CC")
        bb = self.call("cadastrar_documento", codigo_empresa=20, tipo="Extratos CC", nome_documento="BB CC")

        verificacao = self.call(
            "registrar_verificacao",
            codigo_empresa=20,
            fontes=["Email", "Onvio"],
            itens=[
                {"documento_id": itau["documento_id"], "competencia": "01/2026", "resultado": "recebido",
                 "onde": "Email de docs@rotina.com em 05/02, assunto Extrato"},
                {"documento_id": bb["documento_id"], "competencia": "01/2026", "resultado": "nao_encontrado"},
            ],
            resumo="So o Itau chegou.",
        )
        self.assertEqual(verificacao["itens"][0]["status_aplicado"], "Recebido")

        item_bb = [{"documento_id": bb["documento_id"], "competencia": "01/2026"}]
        primeira = self.call("registrar_cobranca", codigo_empresa=20, canal="Email", itens=item_bb)
        segunda = self.call("registrar_cobranca", codigo_empresa=20, canal="WhatsApp", itens=item_bb)
        self.assertEqual(primeira["itens"][0]["tipo"], "Cobranca")
        self.assertEqual(segunda["itens"][0]["tipo"], "Recobranca")

        ficha = self.call("ficha_empresa", codigo_empresa=20)
        self.assertEqual(ficha["totais"]["recobrancas"], 1)
        self.assertEqual([evento["evento"] for evento in ficha["historico"]], ["Recobranca", "Cobranca", "Verificacao"])

        registro = self.call("registro_documento", documento_id=bb["documento_id"])
        janeiro = registro["competencias"][0]
        self.assertEqual((janeiro["cobrancas"], janeiro["recobrancas"]), (1, 1))
        self.assertFalse(janeiro["verificacoes"][0]["encontrado"])

    def test_round_plan_and_failures_are_recorded(self) -> None:
        self.addCleanup(setattr, docflow_server, "_rodada_atual", None)
        self.call("gerar_periodos_ano", ano=2025)
        self.call("cadastrar_empresa", codigo_empresa=30, nome_empresa="Empresa Rodada", email_contato="a@b.com")
        doc = self.call("cadastrar_documento", codigo_empresa=30, tipo="Extratos CC", nome_documento="Itau CC")
        self.call("marcar_status", documento_ids=[doc["documento_id"]], competencia="01/2025", status="Pendente")

        rodada = self.call("iniciar_rodada")
        plano = self.call("o_que_fazer_agora", codigo_empresa=30)
        self.assertEqual(plano["rodada_aberta"], rodada["rodada_id"])
        primeiro = next(d for d in plano["empresas"][0]["documentos"] if d["competencia"] == "01/2025")
        self.assertEqual(primeiro["acao"], "verificar")

        self.call(
            "registrar_verificacao",
            codigo_empresa=30,
            fontes=["Onvio"],
            itens=[{"documento_id": doc["documento_id"], "competencia": "01/2025",
                    "resultado": "verificacao_falhou", "motivo": "Onvio pediu novo login"}],
        )
        self.call("registrar_ocorrencia", tipo="falha", mensagem="Sem acesso ao Onvio", codigo_empresa=30)
        self.call(
            "encaminhar_para_pessoa",
            codigo_empresa=30,
            motivo="cliente_respondeu",
            detalhe="Cliente pediu para ligar",
            itens=[{"documento_id": doc["documento_id"], "competencia": "01/2025"}],
        )
        plano = self.call("o_que_fazer_agora", codigo_empresa=30, incluir_aguardando=True)
        primeiro = next(d for d in plano["empresas"][0]["documentos"] if d["competencia"] == "01/2025")
        self.assertEqual(primeiro["acao"], "com_pessoa")

        fim = self.call("finalizar_rodada", resumo="1 empresa")
        self.assertEqual(fim["status"], "Concluída com falhas")
        self.assertEqual(fim["verificacoes"], 1)
        self.assertIn("Sem acesso", self.call("historico_rodadas")[0]["ocorrencias"][0]["mensagem"])
        self.assertIn("Nao ha rodada", self.call_error("finalizar_rodada"))


if __name__ == "__main__":
    unittest.main()
