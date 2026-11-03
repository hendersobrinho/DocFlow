from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QMimeData  # noqa: E402
from PySide6.QtGui import QImage, QTextCursor  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from documentos_empresa_app.qt_ui.widgets.email_editor import FormattedTextEdit, _png, preview_html  # noqa: E402
from documentos_empresa_app.services import email_sender_service  # noqa: E402
from documentos_empresa_app.services.email_sender_service import (  # noqa: E402
    SIGNATURE_CID,
    SIGNATURE_MAX_BYTES,
    EmailSenderService,
    load_email_signature,
    save_email_settings,
    save_email_signature,
    signature_html,
)
from documentos_empresa_app.utils.common import ValidationError  # noqa: E402
from documentos_empresa_app.utils.email_format import (  # noqa: E402
    de_trechos,
    imagens_usadas,
    para_html,
    para_texto,
    para_whatsapp,
    preencher,
    texto_com_assinatura,
    trechos,
)

APP = QApplication.instance() or QApplication([])


class EmailFormatTests(unittest.TestCase):
    def test_html_text_and_whatsapp_from_marked_text(self) -> None:
        texto = "Olá <b>{contato}</b>,\nentregue <u>até dia 10</u> &amp; <i>sem falta</i>."
        self.assertEqual(para_texto(texto), "Olá {contato},\nentregue até dia 10 & sem falta.")
        corpo = para_html(texto)
        self.assertIn("<b>{contato}</b>,<br>", corpo)
        self.assertIn("<u>até dia 10</u> &amp; <i>sem falta</i>", corpo)
        self.assertEqual(para_whatsapp(texto), "Olá *{contato}*,\nentregue até dia 10 & _sem falta_.")

    def test_old_plain_text_stays_the_same(self) -> None:
        antigo = "Valores < 100 & > 50\n- Extrato"
        self.assertEqual(para_texto(antigo), antigo)
        self.assertIn("Valores &lt; 100 &amp; &gt; 50<br>", para_html(antigo))
        self.assertEqual(para_whatsapp(antigo), antigo)

    def test_unbalanced_marks_do_not_break_the_html(self) -> None:
        self.assertEqual(trechos("<b>a</i>b"), [("ab", frozenset({"b"}))])
        self.assertTrue(para_html("<b>aberto").endswith("<b>aberto</b></div>"))

    def test_whatsapp_marks_stick_to_the_words(self) -> None:
        # O WhatsApp nao formata "* texto *" nem marcas que atravessam linhas.
        self.assertEqual(para_whatsapp("<b> Atenção \nhoje</b>"), " *Atenção* \n*hoje*")

    def test_signature_goes_at_the_end(self) -> None:
        assinatura = "<b>Maria</b>\nMétodos"
        self.assertIn("<br>\n<br>\n<b>Maria</b><br>\nMétodos", para_html("Olá", assinatura))
        self.assertEqual(texto_com_assinatura("Olá\n", assinatura), "Olá\n\nMaria\nMétodos")
        self.assertEqual(texto_com_assinatura("Olá", "  "), "Olá")

    def test_fields_enter_escaped(self) -> None:
        texto = preencher("<b>{empresa}</b> {desconhecido}", {"empresa": "A <b>& B"})
        self.assertEqual(para_texto(texto), "A <b>& B {desconhecido}")
        self.assertEqual(trechos(texto)[0], ("A <b>& B", frozenset({"b"})))


class _ImagensFalsas:
    """Faz o papel do EnvioProgramadoService (salvar_imagem / imagem) para o editor."""

    def __init__(self) -> None:
        self.guardadas: dict[int, dict] = {}

    def salvar_imagem(self, dados: bytes, tipo: str, nome=None) -> int:
        imagem_id = len(self.guardadas) + 1
        self.guardadas[imagem_id] = {"id": imagem_id, "tipo": tipo, "dados": dados}
        return imagem_id

    def imagem(self, imagem_id: int):
        return self.guardadas.get(int(imagem_id))


class ImageInTextTests(unittest.TestCase):
    def test_image_marks_roundtrip_and_render(self) -> None:
        texto = 'Veja:\n<img id="7" width="300">\n<b>fim</b>'
        self.assertEqual(de_trechos(trechos(texto)), texto)
        self.assertEqual(imagens_usadas(texto + '<img id="7"><img id="9">'), [7, 9])
        self.assertEqual(para_texto(texto), "Veja:\n\nfim")
        self.assertIn('<img src="cid:docflow_img7" width="300"', para_html(texto))
        self.assertIn('<img src="x-7"', para_html('<img id="7">', src_imagens=lambda i: f"x-{i}"))
        self.assertEqual(para_whatsapp(texto), "Veja:\n\n*fim*")

    def test_editor_inserts_pastes_and_keeps_images(self) -> None:
        imagens = _ImagensFalsas()
        editor = FormattedTextEdit(imagens=imagens)
        editor.setPlainText("Oi ")
        editor.moveCursor(QTextCursor.MoveOperation.End)
        imagem = QImage(800, 100, QImage.Format.Format_RGB32)
        imagem.fill(0x336699)
        editor.insert_image_data(_png(imagem), "png", "banner.png")
        self.assertEqual(editor.marked(), 'Oi <img id="1" width="600">')  # limitada a 600 px

        # Colar uma imagem (ex: copiada de outro email) vira imagem no texto.
        mime = QMimeData()
        mime.setImageData(QImage(50, 20, QImage.Format.Format_RGB32))
        self.assertTrue(editor.canInsertFromMimeData(mime))
        editor.insertFromMimeData(mime)
        self.assertEqual(editor.marked(), 'Oi <img id="1" width="600"><img id="2" width="50">')

        # Recarregar o texto traz as imagens de volta do banco.
        outro = FormattedTextEdit(imagens=imagens)
        outro.set_marked(editor.marked())
        self.assertEqual(outro.marked(), editor.marked())

    def test_editor_without_images_ignores_pasted_image(self) -> None:
        editor = FormattedTextEdit()
        mime = QMimeData()
        mime.setImageData(QImage(10, 10, QImage.Format.Format_RGB32))
        self.assertFalse(editor.canInsertFromMimeData(mime))

    def test_email_embeds_the_images_of_the_text(self) -> None:
        email = EmailSenderService._montar(
            {
                "para": ["a@x.com"], "assunto": "Mala direta", "corpo": "",
                "corpo_formatado": '<img id="5" width="500">',
                "imagens": {5: {"tipo": "png", "dados": PNG}, 6: {"tipo": "png", "dados": b"nao usada"}},
            },
            "Escritorio <envios@escritorio.com>",
            {"texto": "", "imagem": "", "largura": None},
        )
        pagina = email.get_body(preferencelist=("html",)).get_content()
        self.assertIn('<img src="cid:docflow_img5" width="500"', pagina)
        partes = [parte for parte in email.walk() if parte.get_content_maintype() == "image"]
        self.assertEqual([p["Content-ID"] for p in partes], ["<docflow_img5>"])
        self.assertEqual(partes[0].get_content(), PNG)


class FormattedTextEditTests(unittest.TestCase):
    def test_roundtrip_keeps_marks_and_lines(self) -> None:
        editor = FormattedTextEdit()
        texto = "Olá <b>{contato}</b>,\n\n<b><u>Atenção</u></b>: <i>prazo</i> &lt;10&gt;"
        editor.set_marked(texto)
        self.assertEqual(editor.toPlainText(), "Olá {contato},\n\nAtenção: prazo <10>")
        self.assertEqual(editor.marked(), texto)

    def test_bold_applies_to_the_selection(self) -> None:
        editor = FormattedTextEdit()
        editor.setPlainText("um dois")
        cursor = editor.textCursor()
        cursor.setPosition(3)
        cursor.setPosition(7, QTextCursor.MoveMode.KeepAnchor)
        editor.setTextCursor(cursor)
        editor.toggle("b")
        editor.toggle("u")
        self.assertEqual(editor.marked(), "um <b><u>dois</u></b>")
        editor.clear_formatting()
        self.assertEqual(editor.marked(), "um dois")

    def test_paste_brings_only_the_text(self) -> None:
        editor = FormattedTextEdit()
        self.assertFalse(editor.acceptRichText())

    def test_preview_shows_subject_and_signature(self) -> None:
        tela = preview_html("Cobrança <x>", "Olá <b>Ana</b>", {"texto": "Equipe", "imagem": "C:/x/a.png", "largura": 200}, para="a@x.com")
        self.assertIn("Cobrança &lt;x&gt;", tela)
        self.assertIn("<b>Ana</b>", tela)
        self.assertIn("Equipe", tela)
        self.assertIn('<img src="file:///C:/x/a.png" width="200"', tela)


# PNG 1x1 valido.
PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
    b"\x00\x00\x00\rIDATx\x9cc\xf8\xff\xff?\x00\x05\xfe\x02\xfe\xa7V\xbd\xfa\x00\x00\x00\x00IEND\xaeB`\x82"
)


class _ConfigIsolada:
    """Config e pasta de configuracao temporarias."""

    def __init__(self, caso: unittest.TestCase) -> None:
        self.config: dict = {}
        self.pasta = Path(tempfile.mkdtemp())
        caso.addCleanup(shutil.rmtree, self.pasta, True)
        for alvo, valor in (
            ("load_config", mock.Mock(side_effect=lambda: json.loads(json.dumps(self.config)))),
            ("save_config", mock.Mock(side_effect=self._salvar)),
            ("protect_secret", mock.Mock(side_effect=lambda s: s)),
            ("unprotect_secret", mock.Mock(side_effect=lambda s: s)),
            ("CONFIG_DIR", self.pasta),
        ):
            patcher = mock.patch.object(email_sender_service, alvo, valor)
            patcher.start()
            caso.addCleanup(patcher.stop)

    def _salvar(self, config: dict) -> None:
        self.config = json.loads(json.dumps(config))


class EmailSenderFormatTests(unittest.TestCase):
    def test_email_goes_as_text_and_html_with_signature(self) -> None:
        email = EmailSenderService._montar(
            {"para": ["a@x.com"], "assunto": "Oi", "corpo": "Olá Ana", "corpo_formatado": "Olá <b>Ana</b>"},
            "Escritorio <envios@escritorio.com>",
            {"texto": "Att,\n<i>Maria</i>", "imagem": "", "largura": None},
        )
        self.assertTrue(email.is_multipart())
        texto = email.get_body(preferencelist=("plain",)).get_content()
        pagina = email.get_body(preferencelist=("html",)).get_content()
        self.assertIn("Olá Ana\n\nAtt,\nMaria", texto)
        self.assertIn("Olá <b>Ana</b>", pagina)
        self.assertIn("<i>Maria</i>", pagina)

    def test_signature_image_is_embedded_not_attached(self) -> None:
        pasta = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, pasta, True)
        imagem = pasta / "assinatura.png"
        imagem.write_bytes(PNG)
        email = EmailSenderService._montar(
            {"para": ["a@x.com"], "assunto": "Oi", "corpo": "Olá"},
            "Escritorio <envios@escritorio.com>",
            {"texto": "", "imagem": str(imagem), "largura": 300},
        )
        pagina = email.get_body(preferencelist=("html",)).get_content()
        self.assertIn(f'<img src="cid:{SIGNATURE_CID}" width="300"', pagina)
        partes = [parte for parte in email.walk() if parte.get_content_maintype() == "image"]
        self.assertEqual(len(partes), 1)
        self.assertEqual(partes[0]["Content-ID"], f"<{SIGNATURE_CID}>")
        self.assertEqual(partes[0].get_content_disposition(), "inline")
        self.assertEqual(partes[0].get_content(), PNG)
        self.assertEqual(list(email.iter_attachments()), [])

    def test_signature_saves_without_the_email_login(self) -> None:
        isolada = _ConfigIsolada(self)
        origem = isolada.pasta / "minha assinatura.PNG"
        origem.write_bytes(PNG)
        salva = save_email_signature("<b>Maria</b>", str(origem), 900)
        self.assertEqual(salva["texto"], "<b>Maria</b>")
        self.assertEqual(Path(salva["imagem"]).name, "assinatura_email.png")
        self.assertEqual(Path(salva["imagem"]).read_bytes(), PNG)
        self.assertEqual(salva["largura"], 600)  # limitada
        # Salvar o login depois nao mexe na assinatura; trocar so o texto mantem a imagem.
        save_email_settings({"host": "smtp.x.com", "porta": 587, "seguranca": "starttls", "remetente_email": "e@x.com"})
        self.assertEqual(load_email_signature()["texto"], "<b>Maria</b>")
        self.assertTrue(save_email_signature("Equipe", None, 300)["imagem"])
        semimagem = save_email_signature("Equipe", "", None)
        self.assertEqual((semimagem["imagem"], semimagem["largura"]), ("", None))
        self.assertEqual(list(isolada.pasta.glob("assinatura_email.*")), [])

    def test_rejects_wrong_signature_files(self) -> None:
        isolada = _ConfigIsolada(self)
        texto = isolada.pasta / "x.txt"
        texto.write_text("x")
        with self.assertRaises(ValidationError):
            save_email_signature("", str(texto))
        grande = isolada.pasta / "grande.png"
        grande.write_bytes(PNG + b"0" * SIGNATURE_MAX_BYTES)
        with self.assertRaises(ValidationError):
            save_email_signature("", str(grande))

    def test_old_signature_from_2_0_7_is_kept(self) -> None:
        isolada = _ConfigIsolada(self)
        isolada.config = {"email_envio": {"assinatura": "<b>Antiga</b>"}}
        self.assertEqual(load_email_signature()["texto"], "<b>Antiga</b>")

    def test_signature_html_for_claude(self) -> None:
        sig = {"texto": "Att,\n<b>Maria</b>", "imagem": "C:/x/assinatura_email.png", "largura": 250}
        pagina = signature_html(sig)
        self.assertTrue(pagina.startswith("<div"))
        self.assertIn("Att,<br>\n<b>Maria</b><br>\n<img src=\"cid:assinatura_docflow\" width=\"250\"", pagina)


if __name__ == "__main__":
    unittest.main()
