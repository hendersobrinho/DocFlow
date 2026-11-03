from __future__ import annotations

import os
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QTextCursor  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from documentos_empresa_app.qt_ui.widgets.email_editor import FormattedTextEdit, preview_html  # noqa: E402
from documentos_empresa_app.services import email_sender_service  # noqa: E402
from documentos_empresa_app.services.email_sender_service import EmailSenderService, save_email_settings  # noqa: E402
from documentos_empresa_app.utils.email_format import (  # noqa: E402
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
        tela = preview_html("Cobrança <x>", "Olá <b>Ana</b>", "Equipe", para="a@x.com")
        self.assertIn("Cobrança &lt;x&gt;", tela)
        self.assertIn("<b>Ana</b>", tela)
        self.assertIn("Equipe", tela)


class EmailSenderFormatTests(unittest.TestCase):
    def test_email_goes_as_text_and_html_with_signature(self) -> None:
        email = EmailSenderService._montar(
            {"para": ["a@x.com"], "assunto": "Oi", "corpo": "Olá Ana", "corpo_formatado": "Olá <b>Ana</b>"},
            "Escritorio <envios@escritorio.com>",
            "Att,\n<i>Maria</i>",
        )
        self.assertTrue(email.is_multipart())
        texto = email.get_body(preferencelist=("plain",)).get_content()
        pagina = email.get_body(preferencelist=("html",)).get_content()
        self.assertIn("Olá Ana\n\nAtt,\nMaria", texto)
        self.assertIn("Olá <b>Ana</b>", pagina)
        self.assertIn("<i>Maria</i>", pagina)

    def test_saving_without_signature_keeps_the_saved_one(self) -> None:
        config: dict = {}
        with (
            mock.patch.object(email_sender_service, "load_config", side_effect=lambda: dict(config)),
            mock.patch.object(email_sender_service, "save_config", side_effect=config.update),
            mock.patch.object(email_sender_service, "protect_secret", side_effect=lambda s: s),
            mock.patch.object(email_sender_service, "unprotect_secret", side_effect=lambda s: s),
        ):
            base = {"host": "smtp.x.com", "porta": 587, "seguranca": "starttls", "remetente_email": "e@x.com"}
            save_email_settings({**base, "assinatura": "<b>Maria</b>"})
            save_email_settings(base)
            self.assertEqual(email_sender_service.load_email_settings()["assinatura"], "<b>Maria</b>")
            save_email_settings({**base, "assinatura": ""})
            self.assertEqual(email_sender_service.load_email_settings()["assinatura"], "")


if __name__ == "__main__":
    unittest.main()
