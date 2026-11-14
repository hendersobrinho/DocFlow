from __future__ import annotations

from pathlib import Path
import shutil
import tempfile
import unittest

from psycopg.conninfo import make_conninfo

from documentos_empresa_app.app_context import build_application_services
from documentos_empresa_app.services.socios_service import (
    formatar_cpf,
    formatar_reais,
    ler_planilha_socios,
    normalizar_cpf,
    para_centavos,
)
from documentos_empresa_app.utils.common import ValidationError

from tests.postgres_support import create_test_database_manager, get_test_database_url

CPF_ANA = "529.982.247-25"
CPF_BRUNO = "111.444.777-35"


class ValoresECpfTests(unittest.TestCase):
    def test_cpf_aceita_pontuacao_e_recusa_invalido(self) -> None:
        self.assertEqual(normalizar_cpf(CPF_ANA), "52998224725")
        self.assertEqual(formatar_cpf("52998224725"), CPF_ANA)
        for invalido in ("123", "529.982.247-26", "111.111.111-11", ""):
            with self.assertRaises(ValidationError):
                normalizar_cpf(invalido)

    def test_valores_em_reais_viram_centavos(self) -> None:
        self.assertEqual(para_centavos("55.000,50"), 5_500_050)
        self.assertEqual(para_centavos("R$ 1.234,56"), 123_456)
        self.assertEqual(para_centavos(30000), 3_000_000)
        self.assertEqual(para_centavos("30000.10"), 3_000_010)
        self.assertEqual(para_centavos(-25000), 2_500_000)  # saida no extrato vem negativa
        self.assertEqual(formatar_reais(5_500_050), "R$ 55.000,50")
        with self.assertRaises(ValidationError):
            para_centavos("abc")


class SociosServiceTests(unittest.TestCase):
    """Lei 15.270/2025: acima de R$ 50 mil no mes, da mesma empresa ao mesmo socio, retem 10%
    sobre o total. O Claude registra o que achou em cada extrato; o sistema soma o mes."""

    def setUp(self) -> None:
        db_manager = create_test_database_manager(self)
        conninfo = make_conninfo(get_test_database_url(), options=f"-c search_path={db_manager.schema},public")
        self.services = build_application_services(conninfo)
        self.addCleanup(self.services.database_maintenance_service.db_manager.close)
        self.services.session_service.login(self.services.auth_service.authenticate("admin", "admin"))
        self.services.periodo_service.generate_year(2026)
        self.marco = next(p["id"] for p in self.services.periodo_service.list_periodos() if (p["ano"], p["mes"]) == (2026, 3))
        self.empresa_id = self.services.empresa_service.create_empresa(10, "Clinica Sorriso")
        tipo = self.services.tipo_service.get_or_create_tipo("Extratos CC")["id"]
        self.itau = self.services.documento_service.create_documento(self.empresa_id, tipo, "Itau CC")
        self.bb = self.services.documento_service.create_documento(self.empresa_id, tipo, "BB CC")
        self.socios = self.services.socios_service
        self.ana = self.socios.cadastrar_socio(self.empresa_id, "Ana Souza", CPF_ANA)
        self.bruno = self.socios.cadastrar_socio(self.empresa_id, "Bruno Lima", CPF_BRUNO)

    def test_cadastro_nao_repete_cpf_na_mesma_empresa(self) -> None:
        with self.assertRaises(ValidationError):
            self.socios.cadastrar_socio(self.empresa_id, "Ana de Novo", "52998224725")
        outra = self.services.empresa_service.create_empresa(11, "Outra")
        self.socios.cadastrar_socio(outra, "Ana Souza", CPF_ANA)  # socio de duas empresas
        self.assertEqual(len(self.socios.listar_socios()), 3)

    def test_soma_o_mes_de_todos_os_extratos_e_abre_alerta_acima_de_50_mil(self) -> None:
        primeira = self.socios.registrar_revisao(
            self.empresa_id, self.marco,
            [{"cpf": CPF_ANA, "valor": "30.000,00", "data": "10/03/2026", "descricao": "PIX ANA SOUZA"}],
            documento_id=self.itau, arquivo=r"C:\docs\itau.pdf",
        )
        self.assertEqual(primeira["alertas"], [])  # 30 mil: ainda nao passou

        segunda = self.socios.registrar_revisao(
            self.empresa_id, self.marco,
            [
                {"cpf": CPF_ANA, "valor": 25000, "data": "25/03/2026", "descricao": "TED ANA"},
                {"cpf": CPF_BRUNO, "valor": 40000, "data": "05/03/2026", "descricao": "PIX BRUNO"},
            ],
            documento_id=self.bb, arquivo=r"C:\docs\bb.pdf",
        )
        self.assertEqual(len(segunda["alertas"]), 1)
        alerta = segunda["alertas"][0]
        self.assertEqual(alerta["nome_socio"], "Ana Souza")
        self.assertEqual(alerta["total"], "R$ 55.000,00")
        self.assertEqual(alerta["retencao_estimada"], "R$ 5.500,00")  # 10% sobre o total
        self.assertEqual(alerta["status"], "aberto")

        detalhe = self.socios.obter_alerta(alerta["id"])
        self.assertEqual([p["valor"] for p in detalhe["pagamentos"]], ["R$ 30.000,00", "R$ 25.000,00"])

    def test_exatamente_50_mil_nao_passa_do_limite(self) -> None:
        resultado = self.socios.registrar_revisao(
            self.empresa_id, self.marco, [{"cpf": CPF_ANA, "valor": "50.000,00"}], documento_id=self.itau
        )
        self.assertEqual(resultado["alertas"], [])

    def test_revisar_de_novo_o_mesmo_extrato_substitui(self) -> None:
        self.socios.registrar_revisao(
            self.empresa_id, self.marco, [{"cpf": CPF_ANA, "valor": 60000}], documento_id=self.itau, arquivo="itau.pdf"
        )
        self.assertEqual(len(self.socios.listar_alertas(status="aberto")), 1)
        # O Claude leu errado e corrigiu: o mesmo extrato agora tem 20 mil.
        self.socios.registrar_revisao(
            self.empresa_id, self.marco, [{"cpf": CPF_ANA, "valor": 20000}], documento_id=self.itau, arquivo="ITAU.pdf"
        )
        self.assertEqual(self.socios.listar_alertas(), [])
        self.assertEqual(len(self.socios.listar_revisoes(self.marco)), 1)

    def test_alerta_resolvido_reabre_se_o_total_mudar(self) -> None:
        self.socios.registrar_revisao(self.empresa_id, self.marco, [{"cpf": CPF_ANA, "valor": 60000}], documento_id=self.itau)
        alerta = self.socios.listar_alertas()[0]
        resolvido = self.socios.resolver_alerta(alerta["id"], "resolvido", "IR retido no DARF de abril")
        self.assertEqual((resolvido["status"], resolvido["observacao"]), ("resolvido", "IR retido no DARF de abril"))

        self.socios.registrar_revisao(self.empresa_id, self.marco, [{"cpf": CPF_ANA, "valor": 10000}], documento_id=self.bb)
        reaberto = self.socios.listar_alertas()[0]
        self.assertEqual((reaberto["status"], reaberto["total"]), ("aberto", "R$ 70.000,00"))

    def test_pagamento_para_quem_nao_e_socio_e_recusado(self) -> None:
        with self.assertRaises(ValidationError):
            self.socios.registrar_revisao(
                self.empresa_id, self.marco, [{"cpf": "390.533.447-05", "valor": 60000}], documento_id=self.itau
            )
        sem_socio = self.services.empresa_service.create_empresa(12, "Sem Socio")
        with self.assertRaises(ValidationError):
            self.socios.registrar_revisao(sem_socio, self.marco, [], documento_id=None)

    def test_extratos_para_revisar_lista_o_que_chegou_e_ainda_nao_foi_revisado(self) -> None:
        self.services.status_service.update_status(self.itau, self.marco, "Recebido")
        self.services.status_service.update_status(self.bb, self.marco, "Recebido")
        sem_socio = self.services.empresa_service.create_empresa(12, "Sem Socio")
        tipo = self.services.tipo_service.get_or_create_tipo("Extratos CC")["id"]
        doc = self.services.documento_service.create_documento(sem_socio, tipo, "Caixa CC")
        self.services.status_service.update_status(doc, self.marco, "Recebido")

        lista = self.socios.extratos_para_revisar(self.marco)
        self.assertEqual(lista["extratos_pendentes"], 2)
        self.assertEqual([e["nome_documento"] for e in lista["empresas"][0]["extratos"]], ["BB CC", "Itau CC"])
        self.assertEqual(lista["empresas_sem_socio_cadastrado"][0]["codigo_empresa"], 12)

        self.socios.registrar_revisao(self.empresa_id, self.marco, [], documento_id=self.itau)
        lista = self.socios.extratos_para_revisar(self.marco)
        self.assertEqual((lista["extratos_pendentes"], lista["extratos_revisados"]), (1, 1))
        self.assertEqual([e["nome_documento"] for e in lista["empresas"][0]["extratos"]], ["BB CC"])

    def test_nao_deu_para_revisar_precisa_do_motivo(self) -> None:
        with self.assertRaises(ValidationError):
            self.socios.registrar_revisao(self.empresa_id, self.marco, [], documento_id=self.itau, resultado="nao_deu")
        self.socios.registrar_revisao(
            self.empresa_id, self.marco, [], documento_id=self.itau, resultado="nao_deu", resumo="PDF escaneado ilegivel"
        )
        self.assertEqual(self.socios.listar_revisoes(self.marco)[0]["resultado"], "nao_deu")

    def test_importa_planilha_csv(self) -> None:
        pasta = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, pasta, True)
        arquivo = pasta / "socios.csv"
        arquivo.write_text(
            "Codigo;Nome;CPF\n10;Ana Souza Lima;529.982.247-25\n10;Carla Dias;390.533.447-05\n99;Fulano;111.444.777-35\n"
            "10;Sem CPF;123\n",
            encoding="utf-8",
        )
        self.assertEqual(len(ler_planilha_socios(arquivo)), 4)
        resultado = self.socios.importar_planilha(arquivo)
        self.assertEqual((resultado["criados"], resultado["atualizados"]), (1, 1))
        self.assertEqual(len(resultado["erros"]), 2)
        nomes = sorted(s["nome"] for s in self.socios.listar_socios(self.empresa_id))
        self.assertEqual(nomes, ["Ana Souza Lima", "Bruno Lima", "Carla Dias"])


if __name__ == "__main__":
    unittest.main()
