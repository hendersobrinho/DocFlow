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

    def test_claude_gets_the_signature_with_the_email(self) -> None:
        import base64
        from pathlib import Path
        import shutil
        import tempfile
        from unittest import mock

        pasta = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, pasta, True)
        imagem = pasta / "assinatura_email.png"
        imagem.write_bytes(b"\x89PNG-de-teste")
        assinatura = {"texto": "Att,\n<b>Maria</b>", "imagem": str(imagem), "largura": 320}
        patcher = mock.patch.object(docflow_server, "load_email_signature", return_value=assinatura)
        patcher.start()
        self.addCleanup(patcher.stop)

        self.call("gerar_periodos_ano", ano=2026)
        self.call("cadastrar_empresa", codigo_empresa=30, nome_empresa="Padaria", email_contato="fin@pao.com")
        self.call("cadastrar_documento", codigo_empresa=30, tipo="Informe de Rendimentos", nome_documento="Bradesco")
        envio = self.call(
            "cadastrar_envio_programado", nome="Informe", competencias="trimestral", dia_envio=5,
            assunto="Informe {competencia}", corpo="Olá <b>{empresa}</b>", tipo_documento="informe de rendimentos",
        )
        a_fazer = self.call("envios_a_fazer", data="2026-07-05")
        self.assertEqual(a_fazer["assinatura"]["texto"], "Att,\nMaria")
        self.assertEqual(a_fazer["assinatura"]["imagem"]["caminho"], str(imagem))
        self.assertEqual(a_fazer["assinatura"]["imagem"]["content_id"], "assinatura_docflow")
        item = a_fazer["itens"][0]
        self.assertEqual(item["corpo"], "Olá Padaria")
        self.assertIn("Olá <b>Padaria</b>", item["corpo_html"])
        self.assertIn('<img src="cid:assinatura_docflow" width="320"', item["corpo_html"])
        self.assertEqual(item["corpo_com_assinatura"], "Olá Padaria\n\nAtt,\nMaria")

        self.assertEqual(item["imagens"], [])
        imagem_id = self.services.envio_programado_service.salvar_imagem(b"\x89PNG-corpo", "png")
        from documentos_empresa_app.services import envio_programado_service as modulo_envio

        pasta_cfg = mock.patch.object(modulo_envio, "CONFIG_DIR", pasta)
        pasta_cfg.start()
        self.addCleanup(pasta_cfg.stop)
        self.services.envio_programado_service.atualizar(envio["envio_id"], {"corpo": f'Veja <img id="{imagem_id}">'})
        item = self.call("envios_a_fazer", data="2026-07-05")["itens"][0]
        self.assertIn(f'src="cid:docflow_img{imagem_id}"', item["corpo_html"])
        self.assertEqual(item["imagens"][0]["content_id"], f"docflow_img{imagem_id}")
        self.assertEqual(Path(item["imagens"][0]["caminho"]).read_bytes(), b"\x89PNG-corpo")

        dados = self.call("assinatura_email", incluir_base64=True)
        self.assertTrue(dados["cadastrada"])
        self.assertEqual(base64.b64decode(dados["imagem"]["base64"]), b"\x89PNG-de-teste")
        self.assertEqual(dados["imagem"]["tipo"], "image/png")

        patcher.stop()
        with mock.patch.object(docflow_server, "load_email_signature", return_value={"texto": "", "imagem": "", "largura": None}):
            self.assertFalse(self.call("assinatura_email")["cadastrada"])
        patcher.start()

    def test_scheduled_sending_flow(self) -> None:
        self.call("gerar_periodos_ano", ano=2026)
        self.call("cadastrar_empresa", codigo_empresa=20, nome_empresa="Padaria", email_contato="fin@pao.com")
        self.call("cadastrar_empresa", codigo_empresa=21, nome_empresa="Oficina")
        for codigo in (20, 21):
            self.call("cadastrar_documento", codigo_empresa=codigo, tipo="Informe de Rendimentos", nome_documento="Bradesco")
        empresa = self.call("definir_whatsapp_empresa", codigo_empresa=21, whatsapp="(27) 98888-7777")
        self.assertEqual((empresa["whatsapp"], empresa["whatsapp_usar_nos_envios"]), ("5527988887777", False))
        empresa = self.call("definir_whatsapp_empresa", codigo_empresa=21, usar_nos_envios=True)
        self.assertTrue(empresa["whatsapp_usar_nos_envios"])
        self.assertEqual(empresa["whatsapp"], "5527988887777")  # omitido: mantem o numero
        envio = self.call(
            "cadastrar_envio_programado",
            nome="Informe trimestral",
            competencias="trimestral",
            dia_envio=5,
            assunto="Informe {competencia}",
            corpo="Olá {contato}, faltam:\n{documentos}",
            tipo_documento="informe de rendimentos",
        )
        self.assertEqual((envio["competencias"], envio["enviar_em"], envio["canal"]), ([3, 6, 9, 12], "mes_seguinte", "automatico"))

        # A competencia 06 e cobrada em julho.
        self.assertEqual(self.call("envios_a_fazer", data="2026-06-05")["total"], 0)
        a_fazer = self.call("envios_a_fazer", data="2026-07-05")
        itens = {item["codigo_empresa"]: item for item in a_fazer["itens"]}
        self.assertEqual((itens[20]["assunto"], itens[20]["canal"]), ("Informe 06/2026", "email"))
        self.assertEqual(itens[21]["canal"], "whatsapp")  # liberou o WhatsApp: vai por ele
        previa = self.call("enviar_emails_pelo_docflow", envio_id=envio["envio_id"], competencia="06/2026")
        self.assertEqual(previa["emails_a_enviar"], 1)
        self.assertIn("confirmar=true", previa["aviso"])

        whatsapp = self.call("enviar_whatsapp", whatsapp=itens[21]["whatsapp"], mensagem=itens[21]["mensagem_whatsapp"])
        self.assertFalse(whatsapp["enviado"])  # sem API configurada: devolve o link
        self.assertTrue(whatsapp["link"].startswith("https://wa.me/5527988887777?text="))

        self.call("registrar_envio", envio_id=envio["envio_id"], codigo_empresa=20, competencia="06/2026",
                  status="enviado", destinatarios=["fin@pao.com"])
        self.call("registrar_envio", envio_id=envio["envio_id"], codigo_empresa=21, competencia="06/2026",
                  status="enviado", canal="whatsapp")
        self.assertEqual(self.call("envios_a_fazer", data="2026-07-05")["total"], 0)
        self.assertEqual({r["canal"] for r in self.call("historico_envios")}, {"email", "whatsapp"})

        mala = self.call(
            "cadastrar_envio_programado", nome="Aviso", competencias=[7], enviar_em="mesmo_mes", dia_envio=1,
            assunto="Aviso", corpo="Recesso", codigos_empresas=[20], canal="email",
        )
        self.assertEqual(mala["publico"], "Mala direta: 1 empresa(s) escolhida(s)")
        self.assertEqual([i["codigo_empresa"] for i in self.call("envios_a_fazer", data="2026-07-02", envio_id=mala["envio_id"])["itens"]], [20])

        cco = self.call(
            "cadastrar_envio_programado", nome="Distribuicao de lucros", competencias="mensal", dia_envio=5,
            assunto="Distribuicao {competencia}", corpo="Segue.", codigos_empresas=[20], modo="cco",
            email_para="contato@escritorio.com", canal="email",
        )
        self.call("incluir_na_mala_direta", envio_id=cco["envio_id"], codigos_empresas=[21])
        # Canal 'email' forcado: a Oficina (so WhatsApp) fica sem contato.
        self.assertEqual({e["situacao"] for e in self.call("lista_mala_direta", envio_id=cco["envio_id"])}, {"recebe", "sem_email"})
        modelo = self.call("salvar_modelo_mensagem", nome="Lucros", corpo="Segue a distribuicao.")
        self.assertEqual([m["nome"] for m in self.call("listar_modelos_mensagem")], ["Lucros"])
        self.call("excluir_modelo_mensagem", modelo_id=modelo["id"], confirmar=True)
        item = self.call("envios_a_fazer", data="2026-10-05", envio_id=cco["envio_id"])["itens"][0]
        self.assertEqual((item["para"], item["cco"], item["competencia"]), ("contato@escritorio.com", ["fin@pao.com"], "09/2026"))
        registro = self.call("registrar_envio", envio_id=cco["envio_id"], competencia="09/2026", status="enviado")
        self.assertEqual(registro["empresas"], 1)
        self.assertEqual(self.call("envios_a_fazer", data="2026-10-05", envio_id=cco["envio_id"])["total"], 0)
        self.call("remover_da_mala_direta", envio_id=cco["envio_id"], codigos_empresas=[21])
        self.assertIn("vazia", self.call_error("remover_da_mala_direta", envio_id=cco["envio_id"], codigos_empresas=[20]))
        self.call("excluir_envio_programado", envio_id=cco["envio_id"], confirmar=True)

        self.assertIn("confirmar=true", self.call_error("excluir_envio_programado", envio_id=envio["envio_id"]))
        self.call("excluir_envio_programado", envio_id=envio["envio_id"], confirmar=True)
        self.assertEqual([e["nome"] for e in self.call("listar_envios_programados")], ["Aviso"])

    def test_free_sql_read_and_write(self) -> None:
        self.call("cadastrar_empresa", codigo_empresa=30, nome_empresa="Antiga")
        consulta = self.call("consultar_banco", sql="SELECT codigo_empresa, nome_empresa FROM empresas")
        self.assertEqual(consulta["linhas"], [{"codigo_empresa": 30, "nome_empresa": "Antiga"}])
        self.call_error("consultar_banco", sql="DELETE FROM empresas")  # transacao READ ONLY
        self.assertEqual(len(self.call("listar_empresas", somente_ativas=False)), 1)

        self.assertIn("confirmar=true", self.call_error("executar_sql", sql="DELETE FROM empresas"))
        resultado = self.call("executar_sql", sql="DELETE FROM empresas WHERE codigo_empresa = 30", confirmar=True)
        self.assertEqual(resultado["linhas_afetadas"], 1)
        self.assertEqual(self.call("listar_empresas", somente_ativas=False), [])
        self.assertEqual(self.services.log_service.list_logs(limit=1)[0]["acao"], "SQL_DIRETO")

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

    def test_server_acts_as_claude_without_username_or_password(self) -> None:
        repositorio = self.services.user_service.usuario_repository
        self.assertIsNone(repositorio.get_by_username("claude"))

        user = docflow_server._usuario_do_claude(self.services)  # cria na primeira vez
        self.assertEqual((user["username"], user["tipo_usuario"]), ("claude", "admin"))
        self.assertEqual(docflow_server._usuario_do_claude(self.services)["id"], user["id"])  # depois reaproveita

        repositorio.update(user["id"], "claude", "admin", 0)
        with self.assertRaises(docflow_server.ToolError):
            docflow_server._usuario_do_claude(self.services)


if __name__ == "__main__":
    unittest.main()
