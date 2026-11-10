from __future__ import annotations

from datetime import date, timedelta
import unittest

from psycopg.conninfo import make_conninfo

from documentos_empresa_app.app_context import build_application_services
from documentos_empresa_app.utils.common import ValidationError

from tests.postgres_support import create_test_database_manager, get_test_database_url


class SituacoesCobrancaTests(unittest.TestCase):
    """O "cerebro" da cobranca: cada resultado de verificacao leva o documento para uma
    situacao, e o planejador decide o que fazer depois pelas regras do sistema."""

    def setUp(self) -> None:
        db_manager = create_test_database_manager(self)
        conninfo = make_conninfo(get_test_database_url(), options=f"-c search_path={db_manager.schema},public")
        self.services = build_application_services(conninfo)
        self.addCleanup(self.services.database_maintenance_service.db_manager.close)
        self.services.session_service.login(self.services.auth_service.authenticate("admin", "admin"))

        # Competencia do ano passado: ja esta em atraso, entao sempre aparece na fila.
        self.ano = date.today().year - 1
        self.services.periodo_service.generate_year(self.ano)
        self.janeiro = next(
            p["id"] for p in self.services.periodo_service.list_periodos() if p["ano"] == self.ano and p["mes"] == 1
        )
        self.empresa_id = self.services.empresa_service.create_empresa(1, "Padaria Pao Quente", "fin@pao.com")
        tipo_id = self.services.tipo_service.get_or_create_tipo("Extratos CC")["id"]
        self.doc = self.services.documento_service.create_documento(self.empresa_id, tipo_id, "Itau CC", ["Email"])
        self.services.status_service.update_status(self.doc, self.janeiro, "Pendente")
        self.cobranca = self.services.cobranca_service
        self.par = (self.doc, self.janeiro)

    def _acao(self, hoje: date | None = None) -> dict:
        plano = self.cobranca.proximas_acoes(hoje=hoje)
        for empresa in plano["empresas"]:
            for doc in empresa["documentos"]:
                if (doc["documento_id"], doc["periodo_id"]) == self.par:
                    return doc
        return {}

    def _verificar(self, **item) -> dict:
        return self.cobranca.registrar_verificacao(
            self.empresa_id, ["Email"], [{"documento_id": self.doc, "periodo_id": self.janeiro, **item}]
        )

    def test_never_verified_document_must_be_verified_first(self) -> None:
        self.assertEqual(self._acao()["acao"], "verificar")

    def test_not_found_goes_to_charge_then_waits_then_recharges(self) -> None:
        self._verificar(resultado="nao_encontrado")
        self.assertEqual(self._acao()["acao"], "cobrar")

        self.cobranca.registrar_cobranca(self.empresa_id, "Email", [self.par])
        esperando = self._acao()
        self.assertEqual(esperando["acao"], "aguardar")
        self.assertEqual(esperando["situacao"], "cobrado_aguardando")

        depois = date.today() + timedelta(days=4)
        self.assertEqual(self._acao(depois)["acao"], "verificar")
        self._verificar(resultado="nao_encontrado")
        self.assertEqual(self._acao(depois)["acao"], "recobrar")

    def test_recharge_limit_sends_to_a_person(self) -> None:
        self.services.collection_service.update_followup_rules(0, 1, True)
        for _ in range(2):
            self._verificar(resultado="nao_encontrado")
            self.cobranca.registrar_cobranca(self.empresa_id, "Email", [self.par])
        self._verificar(resultado="nao_encontrado")

        acao = self._acao()
        self.assertEqual(acao["acao"], "com_pessoa")
        self.assertIn("Limite", acao["porque"])
        self.assertEqual(len(self.cobranca.precisa_de_atencao()), 1)

    def test_failed_verification_is_not_treated_as_missing(self) -> None:
        resultado = self._verificar(resultado="verificacao_falhou", motivo="Sem acesso ao Onvio")

        self.assertFalse(resultado["itens"][0]["encontrado"])
        acao = self._acao()
        self.assertEqual(acao["acao"], "verificar")
        self.assertIn("Sem acesso", acao["porque"])
        with self.assertRaises(ValidationError):
            self._verificar(resultado="verificacao_falhou")

    def test_problem_document_goes_to_person_or_back_to_charge_by_rule(self) -> None:
        resultado = self._verificar(resultado="documento_com_problema", motivo="competencia_errada")
        self.assertFalse(resultado["itens"][0]["baixa_feita"])
        self.assertEqual(self._acao()["acao"], "com_pessoa")

        self.services.collection_service.update_followup_rules(3, 3, False)
        self.assertEqual(self._acao()["acao"], "cobrar")

    def test_found_document_gets_baixa_and_leaves_the_queue(self) -> None:
        resultado = self._verificar(resultado="recebido", onde="Email de fin@pao.com")

        self.assertTrue(resultado["itens"][0]["baixa_feita"])
        self.assertEqual(self._acao(), {})
        registro = self.cobranca.registro_documento(self.doc)
        competencia = registro["competencias"][0]
        self.assertEqual(competencia["situacao"], "recebido")
        self.assertEqual(competencia["caminho"][0]["para"], "recebido")

    def test_found_without_baixa_waits_for_a_person(self) -> None:
        self.cobranca.registrar_verificacao(
            self.empresa_id,
            ["Email"],
            [{"documento_id": self.doc, "periodo_id": self.janeiro, "resultado": "recebido"}],
            marcar_recebidos=False,
        )
        acao = self._acao()
        self.assertEqual(acao["acao"], "com_pessoa")
        self.assertEqual(acao["situacao_motivo"], "baixa_pendente")

        self.cobranca.dar_baixa_manual([self.par])
        self.assertEqual(self._acao(), {})

    def test_promise_waits_until_the_promised_date(self) -> None:
        prazo = date.today() + timedelta(days=2)
        self.cobranca.registrar_promessa([self.par], prazo.isoformat(), "Cliente disse que manda sexta")

        self.assertEqual(self._acao()["acao"], "aguardar")
        self.assertEqual(self._acao(prazo + timedelta(days=1))["acao"], "verificar")

    def test_person_can_return_a_case_to_the_flow(self) -> None:
        self.cobranca.encaminhar_para_pessoa([self.par], "cliente_respondeu", "Pediu prazo maior")
        self.assertEqual(self._acao()["acao"], "com_pessoa")

        self.cobranca.devolver_para_fluxo([self.par], "Combinado por telefone")
        self.assertEqual(self._acao()["acao"], "verificar")
        caminho = self.cobranca.registro_documento(self.doc)["competencias"][0]["caminho"]
        self.assertEqual([p["para"] for p in caminho], ["a_verificar", "precisa_pessoa"])

    def test_downloaded_file_is_kept_with_the_verification(self) -> None:
        self._verificar(resultado="documento_com_problema", motivo="documento_errado", arquivo="/tmp/itau-jan.pdf")

        verificacao = self.cobranca.listar_verificacoes(1)[0]
        self.assertEqual(verificacao["itens"][0]["arquivo"], "/tmp/itau-jan.pdf")
        competencia = self.cobranca.registro_documento(self.doc)["competencias"][0]
        self.assertEqual(competencia["verificacoes"][0]["arquivo"], "/tmp/itau-jan.pdf")
        self.assertEqual(competencia["periodo_id"], self.janeiro)

    def test_manual_check_from_the_screen(self) -> None:
        self.cobranca.registrar_conferencia_manual(self.doc, self.janeiro, False)
        self.assertEqual(self._acao()["acao"], "cobrar")

        self.cobranca.registrar_conferencia_manual(self.doc, self.janeiro, True)
        self.assertEqual(self._acao(), {})
        self.assertEqual(self.cobranca.listar_verificacoes(1)[0]["fontes"], "Conferencia manual")

    def test_manual_problem_with_reason_and_note(self) -> None:
        self.cobranca.resolver_manual(
            [self.par], "documento_com_problema", motivo="ilegivel_ou_incompleto", observacao="Foto borrada"
        )
        registro = self.cobranca.registro_documento(self.doc)["competencias"][0]
        self.assertEqual(registro["situacao"], "documento_com_problema")
        self.assertEqual(registro["verificacoes"][0]["observacao"], "Foto borrada")

    def test_year_map_has_status_and_situation_per_month(self) -> None:
        self._verificar(resultado="nao_encontrado")
        mapa = self.cobranca.mapa_empresa(self.empresa_id, meses=24)

        linha = next(d for d in mapa["documentos"] if d["documento_id"] == self.doc)
        celula = next(c for c in linha["celulas"] if c["periodo_id"] == self.janeiro)
        self.assertEqual((celula["status"], celula["situacao"]), ("Pendente", "nao_encontrado"))
        self.assertEqual(len(linha["celulas"]), len(mapa["periodos"]))

    def test_marking_many_cells_at_once(self) -> None:
        fevereiro = next(
            p["id"] for p in self.services.periodo_service.list_periodos() if p["ano"] == self.ano and p["mes"] == 2
        )
        resultado = self.services.status_service.update_status_many(
            [(self.doc, self.janeiro), (self.doc, fevereiro)], "Recebido"
        )
        self.assertEqual(resultado["updated"], 2)
        mapa = self.cobranca.mapa_empresa(self.empresa_id, meses=2, ate_periodo_id=fevereiro)
        self.assertEqual([p["mes"] for p in mapa["periodos"]], [1, 2])
        celulas = mapa["documentos"][0]["celulas"]
        self.assertEqual([c["status"] for c in celulas], ["Recebido", "Recebido"])
        self.assertEqual(celulas[0]["marcado_por"], "admin")

    def test_round_collects_actions_and_failures(self) -> None:
        rodadas = self.services.rodada_service
        rodada = rodadas.iniciar()
        self.cobranca.registrar_verificacao(
            self.empresa_id,
            ["Email"],
            [{"documento_id": self.doc, "periodo_id": self.janeiro, "resultado": "nao_encontrado"}],
            rodada_id=rodada["id"],
        )
        rodadas.registrar_ocorrencia(rodada["id"], "falha", "Onvio fora do ar", self.empresa_id)
        finalizada = rodadas.finalizar(rodada["id"], "1 empresa verificada")

        self.assertEqual(finalizada["status"], "concluida_com_falhas")
        self.assertEqual(finalizada["verificacoes"], 1)
        self.assertEqual(finalizada["ocorrencias"][0]["mensagem"], "Onvio fora do ar")
        self.assertEqual(len(rodadas.rodadas_com_problema()), 1)
        with self.assertRaises(ValidationError):
            rodadas.finalizar(rodada["id"])


    def test_daily_round_report_gathers_what_was_found_charged_and_downloaded(self) -> None:
        import json
        from pathlib import Path
        import shutil
        import tempfile

        from documentos_empresa_app.services.relatorio_rodada import coletar_dia
        from documentos_empresa_app.services.report_rodada_html import build_rodada_html

        tipo_id = self.services.tipo_service.get_or_create_tipo("Extratos CC")["id"]
        doc2 = self.services.documento_service.create_documento(self.empresa_id, tipo_id, "Bradesco CC", ["Email"])
        self.services.status_service.update_status(doc2, self.janeiro, "Pendente")

        rodadas = self.services.rodada_service
        rodada = rodadas.iniciar()
        self.cobranca.registrar_verificacao(
            self.empresa_id,
            ["Email", "Onvio"],
            [
                {"documento_id": self.doc, "periodo_id": self.janeiro, "resultado": "recebido", "onde": "Onvio > Extrato"},
                {"documento_id": doc2, "periodo_id": self.janeiro, "resultado": "nao_encontrado"},
            ],
            rodada_id=rodada["id"],
        )
        self.cobranca.registrar_cobranca(self.empresa_id, "Email", [(doc2, self.janeiro)], rodada_id=rodada["id"])
        rodadas.registrar_ocorrencia(rodada["id"], "falha", "Onvio fora do ar", empresa_id=self.empresa_id)
        rodadas.finalizar(rodada["id"], "1 empresa verificada")

        pasta = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, pasta, True)
        (pasta / "01-2025").mkdir()
        (pasta / "01-2025" / "_resumo.json").write_text(
            json.dumps(
                {
                    "competencia": "01/2025",
                    "pasta": str(pasta / "01-2025"),
                    "gerado_em": date.today().isoformat() + "T08:30:00",
                    "empresas": [{"codigo": "1", "nome": "Padaria Pao Quente", "situacao": "baixada", "arquivos": 4, "novos": ["a", "b", "c", "d"]}],
                }
            ),
            encoding="utf-8",
        )

        pending = self.services.pending_report_service
        # O proprio sistema sabe o que chegou: marcar como recebido entra no relatorio do dia.
        self.services.status_service.update_status(self.doc, self.janeiro, "Recebido")

        dados = coletar_dia(self.cobranca, rodadas, date.today(), pasta, recebidos_no_dia=pending.recebidos_no_dia)
        self.assertEqual([r["nome_documento"] for r in dados["recebidos"]], ["Itau CC"])
        self.assertEqual(dados["recebidos"][0]["competencia"], f"01/{self.ano}")
        self.assertEqual(len(dados["rodadas"]), 1)
        self.assertEqual([i["nome_documento"] for i in dados["encontrados"]], ["Itau CC"])
        self.assertEqual([i["nome_documento"] for i in dados["nao_encontrados"]], ["Bradesco CC"])
        self.assertEqual(len(dados["cobrancas"]), 1)
        self.assertEqual(dados["totais"]["empresas"], 1)
        self.assertEqual(dados["onvio"][0]["empresas"][0]["arquivos"], 4)

        html = build_rodada_html(dados, "10/11/2026 11:00")
        for texto in (
            "Relatório da cobrança do dia", "Padaria Pao Quente", "Itau CC", "Bradesco CC", "Onvio fora do ar",
            "Baixado do Onvio", "marcado como recebido",
        ):
            self.assertIn(texto, html)

        # Sem nenhuma rodada do Claude o sistema ainda monta o relatorio com o que ele mesmo registrou.
        sem_claude = coletar_dia(self.cobranca, rodadas, date.today(), None, recebidos_no_dia=pending.recebidos_no_dia)
        sem_claude["rodadas"], sem_claude["verificacoes"] = [], []
        html_sem_claude = build_rodada_html(sem_claude, "10/11/2026 11:00")
        self.assertIn("Itau CC", html_sem_claude)
        self.assertNotIn("Como foi a rodada", html_sem_claude)

        # Outro dia: nada registrado, mas o relatorio sai (com o aviso de dia vazio).
        vazio = coletar_dia(self.cobranca, rodadas, date.today() - timedelta(days=3), pasta, recebidos_no_dia=pending.recebidos_no_dia)
        self.assertEqual((vazio["totais"]["empresas"], len(vazio["onvio"]), len(vazio["recebidos"])), (0, 0, 0))
        self.assertIn("Nada foi registrado", build_rodada_html(vazio, "10/11/2026 11:00"))


if __name__ == "__main__":
    unittest.main()
