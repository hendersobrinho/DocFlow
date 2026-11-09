from __future__ import annotations

import io
import json
from pathlib import Path
import shutil
import tempfile
import unittest
import zipfile

from documentos_empresa_app.onvio.api import OnvioApi, OnvioError, SessaoExpirada, nome_competencia
from documentos_empresa_app.onvio.robo import (
    BAIXADA,
    JA_BAIXADA,
    PASTA_VAZIA,
    RESUMO,
    SEM_CLIENTE,
    SEM_PASTA,
    baixar_competencia,
    extrair_zip,
    nome_seguro,
)

ESCRITORIO = "00000000000000000000000000000001"


def _zip(arquivos: dict[str, bytes], sem_utf8: tuple[str, ...] = ()) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as pacote:
        for nome in sem_utf8:
            # Como o Onvio grava as pastas: bytes UTF-8 sem a marca de UTF-8 no zip.
            info = zipfile.ZipInfo(nome.encode("utf-8").decode("cp437"))
            pacote.writestr(info, b"")
        for nome, conteudo in arquivos.items():
            pacote.writestr(nome, conteudo)
    return buffer.getvalue()


class OnvioFalso:
    """Transporte falso: clientes 170 (com a pasta 03-2026) e 180 (sem a pasta)."""

    def __init__(self, sessao_valida: bool = True) -> None:
        self.sessao_valida = sessao_valida
        self.exportados: list[dict] = []
        self.consultas_job = 0
        self.arvore = {
            "proj-cont-170": [_pasta("ano-2025", "2025"), _pasta("ano-2026", "2026"), _pasta("sped", "SPED ECD E ECF")],
            "ano-2026": [_pasta("comp-02", "02-2026"), _pasta("comp-03", "03-2026")],
            "comp-03": [_pasta("extrato", "Extrato Bancário"), _pasta("nf", "Nota Fiscal"), {"id": "arq-1", "name": "solto.pdf", "itemType": "Document"}],
            "extrato": [_arquivo("f-1", "03 Março.pdf"), _arquivo("f-2", "03.ofx")],
            "proj-cont-180": [_pasta("ano-2026-180", "2026")],
            "ano-2026-180": [_pasta("comp-02-180", "02-2026")],
        }

    def get_json(self, caminho: str) -> dict:
        if not self.sessao_valida:
            raise SessaoExpirada("expirou")
        if caminho.startswith("/api/security/v1/session-and-bindings"):
            return {"data": {"UdsSession": {"companyId": ESCRITORIO}}}
        if caminho.startswith("/api/storage/v1/projects?"):
            cliente = caminho.split("primaryAssociationId=")[1].split("&")[0]
            return {"data": [{"id": f"proj-cont-{cliente[-3:]}", "name": "Contabilidade"}, {"id": "fiscal", "name": "Fiscal"}]}
        if "/children?" in caminho:
            pasta = caminho.split("/children")[0].rsplit("/", 1)[1]
            return {"data": {"items": self.arvore.get(pasta, []), "hasMore": False}}
        if caminho.startswith("/api/storage/v1/jobs/"):
            self.consultas_job += 1
            return {"data": {"jobStatus": "SUCCESS" if self.consultas_job > 1 else "RUNNING"}}
        raise AssertionError(caminho)

    def post_json(self, caminho: str, corpo: dict) -> dict:
        if caminho == f"/api/core/v3/companies/{ESCRITORIO}/clients/search":
            assert corpo["pagingDataRequest"]["pageIndex"] == 1
            return {"data": {"items": [{"id": "cli-170", "code": "170", "name": "EMPRESA TESTE"}, {"id": "cli-180", "code": "180", "name": "Outra"}]}}
        if caminho == "/api/storage/v1/jobs/export":
            self.exportados.append(corpo)
            return {"data": "job-1"}
        raise AssertionError(caminho)

    def get_bytes(self, caminho: str) -> bytes:
        assert caminho == "/api/storage/v1/jobs/job-1/result"
        return _zip(
            {"Extrato Bancário/03 Março.pdf": b"%PDF", "Extrato Bancário/03.ofx": b"OFX", "solto.pdf": b"%PDF2"},
            sem_utf8=("Extrato Bancário/", "Nota Fiscal/"),
        )


def _arquivo(arquivo_id: str, nome: str) -> dict:
    return {"id": arquivo_id, "name": nome, "itemType": "Document"}


def _pasta(pasta_id: str, nome: str) -> dict:
    return {"id": pasta_id, "name": nome, "itemType": "Folder"}


class OnvioRoboTests(unittest.TestCase):
    def setUp(self) -> None:
        self.pasta = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.pasta, True)

    def test_downloads_the_competence_folder_of_each_company(self) -> None:
        falso = OnvioFalso()
        api = OnvioApi(falso, espera=lambda _s: None)
        progresso = []
        resumo = baixar_competencia(
            api, 2026, 3, [("170", "EMPRESA TESTE"), ("180", "Outra"), ("999", "Sem Onvio")], self.pasta,
            on_progress=lambda f, t, r, m: progresso.append((f, t)),
        )
        situacoes = {e.codigo: e.situacao for e in resumo.empresas}
        self.assertEqual(situacoes, {"170": BAIXADA, "180": SEM_PASTA, "999": SEM_CLIENTE})
        # Pediu o zip das subpastas e do arquivo solto, como o Gerenciar > Baixar.
        self.assertEqual(falso.exportados, [{"folderIDs": ["extrato"], "fileIDs": ["arq-1"]}])
        empresa = self.pasta / "03-2026" / "170 - EMPRESA TESTE"
        self.assertEqual((empresa / "Extrato Bancário" / "03 Março.pdf").read_bytes(), b"%PDF")
        self.assertTrue((empresa / "Extrato Bancário").is_dir())  # acento consertado
        self.assertEqual(resumo.empresas[0].arquivos, 3)
        self.assertEqual(progresso[-1], (3, 3))
        dados = json.loads((self.pasta / "03-2026" / RESUMO).read_text(encoding="utf-8"))
        self.assertEqual(dados["competencia"], "03/2026")
        self.assertEqual(dados["empresas"][0]["situacao_texto"], "Baixada")
        self.assertIn("3 arquivo(s)", resumo.texto())

        # Rodando de novo sem nada novo no Onvio: nao baixa nada.
        falso.exportados.clear()
        de_novo = baixar_competencia(api, 2026, 3, [("170", "EMPRESA TESTE")], self.pasta)
        self.assertEqual(de_novo.empresas[0].situacao, JA_BAIXADA)
        self.assertEqual(falso.exportados, [])
        # Com baixar_de_novo baixa tudo outra vez.
        baixar_competencia(api, 2026, 3, [("170", "EMPRESA TESTE")], self.pasta, baixar_de_novo=True)
        self.assertEqual(len(falso.exportados), 1)

    def test_second_pass_downloads_only_what_arrived_later(self) -> None:
        falso = OnvioFalso()
        api = OnvioApi(falso, espera=lambda _s: None)
        empresa = self.pasta / "03-2026" / "170 - A"
        baixar_competencia(api, 2026, 3, [("170", "A")], self.pasta)

        # O Claude arruma os arquivos: move um e renomeia outro. O robo nao pode baixar de novo.
        (empresa / "solto.pdf").unlink()
        (empresa / "Extrato Bancário" / "03 Março.pdf").rename(empresa / "Extrato Bancário" / "extrato-banestes.pdf")
        falso.exportados.clear()
        sem_novidade = baixar_competencia(api, 2026, 3, [("170", "A")], self.pasta)
        self.assertEqual(sem_novidade.empresas[0].situacao, JA_BAIXADA)
        self.assertEqual(falso.exportados, [])
        self.assertFalse((empresa / "solto.pdf").exists())

        # Chega um arquivo novo no Onvio: baixa so ele, e o resumo guarda o que foi novo.
        falso.arvore["extrato"].append(_arquivo("f-3", "03.pdf"))
        falso.get_bytes = lambda caminho: _zip({"Extrato Bancário/03 Março.pdf": b"antigo", "Extrato Bancário/03.pdf": b"novo"})
        nova = baixar_competencia(api, 2026, 3, [("170", "A")], self.pasta)
        self.assertEqual(nova.empresas[0].situacao, BAIXADA)
        self.assertEqual(nova.empresas[0].novos, ["Extrato Bancário/03.pdf"])
        self.assertEqual((empresa / "Extrato Bancário" / "03.pdf").read_bytes(), b"novo")
        self.assertFalse((empresa / "Extrato Bancário" / "03 Março.pdf").exists())  # nao voltou
        self.assertEqual(falso.exportados, [{"folderIDs": ["extrato"], "fileIDs": []}])

    def test_old_download_without_manifest_is_recognised_by_path(self) -> None:
        api = OnvioApi(OnvioFalso(), espera=lambda _s: None)
        empresa = self.pasta / "03-2026" / "170 - A"
        (empresa / "Extrato Bancário").mkdir(parents=True)
        for nome in ("Extrato Bancário/03 Março.pdf", "Extrato Bancário/03.ofx", "solto.pdf"):
            (empresa / nome).write_bytes(b"x")
        resumo = baixar_competencia(api, 2026, 3, [("170", "A")], self.pasta)
        self.assertEqual(resumo.empresas[0].situacao, JA_BAIXADA)

    def test_summary_keeps_companies_not_visited_in_this_pass(self) -> None:
        api = OnvioApi(OnvioFalso(), espera=lambda _s: None)
        baixar_competencia(api, 2026, 3, [("170", "A")], self.pasta)
        baixar_competencia(api, 2026, 3, [("180", "B")], self.pasta)
        dados = json.loads((self.pasta / "03-2026" / RESUMO).read_text(encoding="utf-8"))
        self.assertEqual({e["codigo"] for e in dados["empresas"]}, {"170", "180"})

    def test_competence_folder_directly_inside_contabilidade(self) -> None:
        falso = OnvioFalso()
        falso.arvore["proj-cont-170"] = [_pasta("comp-03", "3-2026")]
        api = OnvioApi(falso, espera=lambda _s: None)
        self.assertEqual(api.pasta_da_competencia("cli-170", 2026, 3)["id"], "comp-03")
        self.assertIsNone(api.pasta_da_competencia("cli-170", 2026, 4))

    def test_empty_folder_and_cancel(self) -> None:
        falso = OnvioFalso()
        falso.arvore["comp-03"] = []
        api = OnvioApi(falso, espera=lambda _s: None)
        resumo = baixar_competencia(api, 2026, 3, [("170", "A")], self.pasta)
        self.assertEqual(resumo.empresas[0].situacao, PASTA_VAZIA)
        cancelado = baixar_competencia(api, 2026, 3, [("170", "A")], self.pasta, cancelado=lambda: True)
        self.assertEqual((cancelado.empresas, cancelado.interrompido), ([], "cancelado"))

    def test_expired_session_stops_and_keeps_the_summary(self) -> None:
        api = OnvioApi(OnvioFalso(sessao_valida=False), espera=lambda _s: None)
        with self.assertRaises(SessaoExpirada):
            baixar_competencia(api, 2026, 3, [("170", "A")], self.pasta)

    def test_failed_job_is_reported(self) -> None:
        falso = OnvioFalso()
        falso.get_json = lambda c: {"data": {"jobStatus": "FAILED"}} if c.startswith("/api/storage/v1/jobs/") else OnvioFalso.get_json(falso, c)
        api = OnvioApi(falso, espera=lambda _s: None)
        with self.assertRaises(OnvioError):
            api.exportar_zip(["x"], [])

    def test_zip_cannot_write_outside_the_folder(self) -> None:
        conteudo = _zip({"../../fora.txt": b"x", "ok/dentro.txt": b"y", "a:b?.txt": b"z"})
        self.assertEqual(extrair_zip(conteudo, self.pasta / "destino"), 3)
        self.assertFalse((self.pasta / "fora.txt").exists())
        self.assertTrue((self.pasta / "destino" / "fora.txt").exists())  # o ".." e descartado
        self.assertTrue((self.pasta / "destino" / "a_b_.txt").exists())

    def test_names(self) -> None:
        self.assertEqual(nome_competencia(2026, 3), "03-2026")
        self.assertEqual(nome_seguro('170 - A/B: "C".'), "170 - A_B_ _C_")



class OnvioDialogTests(unittest.TestCase):
    def test_dialog_runs_the_robot_in_a_thread(self) -> None:
        import os
        from unittest import mock

        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication

        app = QApplication.instance() or QApplication([])
        from contextlib import contextmanager

        from documentos_empresa_app.qt_ui.dialogs import onvio_dialog

        pasta = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, pasta, True)

        class Empresas:
            def list_empresas(self, active_only=False):
                return [{"codigo_empresa": 170, "nome_empresa": "EMPRESA TESTE"}, {"codigo_empresa": 245, "nome_empresa": "Sem Onvio"}]

            def list_empresas_com_meio(self, meio, active_only=True, pendentes_em=None):
                assert meio == "onvio"
                return self.list_empresas()[:1]

        services = type("S", (), {"empresa_service": Empresas()})()

        @contextmanager
        def sessao_falsa(avisar=None, cancelado=None, **_):
            yield OnvioApi(OnvioFalso(), espera=lambda _s: None)

        with mock.patch("documentos_empresa_app.onvio.navegador.sessao_onvio", sessao_falsa),                 mock.patch.object(onvio_dialog, "save_ui_state"):
            dialogo = onvio_dialog.OnvioDownloadDialog(services, (2026, 3))
            self.assertEqual((dialogo.mes_combo.currentData(), dialogo.ano_spin.value()), (3, 2026))
            dialogo.destino_edit.setText(str(pasta))
            dialogo.so_onvio_check.setChecked(True)
            self.assertEqual([c for c, _ in dialogo.empresas()], ["170"])
            dialogo.so_onvio_check.setChecked(False)
            self.assertEqual(len(dialogo.empresas()), 2)
            dialogo.so_onvio_check.setChecked(True)
            dialogo.iniciar()
            for _ in range(500):
                app.processEvents()
                if dialogo.resumo:
                    break
                dialogo._thread and dialogo._thread.wait(10)
            self.assertIsNotNone(dialogo.resumo)
        self.assertEqual(dialogo.resumo.empresas[0].situacao, BAIXADA)
        self.assertTrue((pasta / "03-2026" / "170 - EMPRESA TESTE" / "solto.pdf").exists())
        self.assertIsNone(dialogo._thread)
        dialogo.close()


if __name__ == "__main__":
    unittest.main()
