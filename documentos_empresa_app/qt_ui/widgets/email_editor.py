"""Editor do texto do email com negrito, italico e sublinhado, e a previa de como o email
chega (com a assinatura). O texto sai e entra no formato de utils/email_format."""

from __future__ import annotations

import html

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QTextBrowser,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from documentos_empresa_app.qt_ui.widgets.common import make_button
from documentos_empresa_app.utils.email_format import (
    ITALICO,
    NEGRITO,
    SUBLINHADO,
    de_trechos,
    para_html,
    trechos,
)

_SEPARADORES = {" ": "\n", " ": "\n", "￼": ""}


def _peso(formato: QTextCharFormat) -> int:
    peso = formato.fontWeight()
    return int(getattr(peso, "value", peso))


def _estilos(formato: QTextCharFormat) -> frozenset:
    estilos = set()
    if _peso(formato) > 500:
        estilos.add(NEGRITO)
    if formato.fontItalic():
        estilos.add(ITALICO)
    if formato.fontUnderline():
        estilos.add(SUBLINHADO)
    return frozenset(estilos)


class FormattedTextEdit(QTextEdit):
    """QTextEdit que guarda so negrito, italico e sublinhado. Colar traz so o texto (sem as
    cores e fontes de quem copiou); Ctrl+B, Ctrl+I e Ctrl+U formatam."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAcceptRichText(False)

    # Formato guardado <-> documento --------------------------------------------------------

    def marked(self) -> str:
        lista = []
        bloco = self.document().begin()
        primeiro = True
        while bloco.isValid():
            if not primeiro:
                lista.append(("\n", frozenset()))
            primeiro = False
            iterador = bloco.begin()
            while not iterador.atEnd():
                fragmento = iterador.fragment()
                if fragmento.isValid():
                    texto = fragmento.text()
                    for de, para in _SEPARADORES.items():
                        texto = texto.replace(de, para)
                    lista.append((texto, _estilos(fragmento.charFormat())))
                iterador += 1
            bloco = bloco.next()
        return de_trechos(lista)

    def set_marked(self, texto: str | None) -> None:
        self.clear()
        cursor = QTextCursor(self.document())
        cursor.beginEditBlock()
        for parte, estilos in trechos(texto):
            formato = QTextCharFormat()
            formato.setFontWeight(QFont.Weight.Bold if NEGRITO in estilos else QFont.Weight.Normal)
            formato.setFontItalic(ITALICO in estilos)
            formato.setFontUnderline(SUBLINHADO in estilos)
            cursor.insertText(parte, formato)
        cursor.endEditBlock()
        # O que vem depois do texto carregado comeca sem formatacao.
        self.setCurrentCharFormat(QTextCharFormat())
        self.document().clearUndoRedoStacks()
        self.moveCursor(QTextCursor.MoveOperation.Start)

    # Formatacao --------------------------------------------------------------------------

    def toggle(self, estilo: str) -> None:
        atual = _estilos(self.currentCharFormat())
        formato = QTextCharFormat()
        ligar = estilo not in atual
        if estilo == NEGRITO:
            formato.setFontWeight(QFont.Weight.Bold if ligar else QFont.Weight.Normal)
        elif estilo == ITALICO:
            formato.setFontItalic(ligar)
        else:
            formato.setFontUnderline(ligar)
        self.mergeCurrentCharFormat(formato)

    def clear_formatting(self) -> None:
        formato = QTextCharFormat()
        formato.setFontWeight(QFont.Weight.Normal)
        formato.setFontItalic(False)
        formato.setFontUnderline(False)
        self.mergeCurrentCharFormat(formato)

    def keyPressEvent(self, event) -> None:  # noqa: N802 - API do Qt
        atalhos = {Qt.Key.Key_B: NEGRITO, Qt.Key.Key_I: ITALICO, Qt.Key.Key_U: SUBLINHADO}
        if event.modifiers() == Qt.KeyboardModifier.ControlModifier and event.key() in atalhos:
            self.toggle(atalhos[event.key()])
            return
        super().keyPressEvent(event)


class FormatBar(QWidget):
    """Botoes N / I / S (e limpar) de um FormattedTextEdit. Nao pegam o foco: o cursor fica
    no texto."""

    def __init__(self, editor: FormattedTextEdit, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.editor = editor
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        self.botoes: dict[str, QToolButton] = {}
        for estilo, rotulo, dica, css in (
            (NEGRITO, "N", "Negrito (Ctrl+B)", "font-weight: 700;"),
            (ITALICO, "I", "Itálico (Ctrl+I)", "font-style: italic;"),
            (SUBLINHADO, "S", "Sublinhado (Ctrl+U)", "text-decoration: underline;"),
        ):
            botao = QToolButton()
            botao.setText(rotulo)
            botao.setToolTip(dica)
            botao.setCheckable(True)
            botao.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            botao.setStyleSheet(f"QToolButton {{ {css} min-width: 24px; }}")
            botao.clicked.connect(lambda _c=False, e=estilo: self._aplicar(e))
            layout.addWidget(botao)
            self.botoes[estilo] = botao
        limpar = QToolButton()
        limpar.setText("Limpar")
        limpar.setToolTip("Tira o negrito, itálico e sublinhado do texto selecionado")
        limpar.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        limpar.clicked.connect(self._limpar)
        layout.addWidget(limpar)
        layout.addStretch(1)
        editor.currentCharFormatChanged.connect(self._sincronizar)
        self._sincronizar(editor.currentCharFormat())

    def _aplicar(self, estilo: str) -> None:
        self.editor.toggle(estilo)
        self.editor.setFocus()
        self._sincronizar(self.editor.currentCharFormat())

    def _limpar(self) -> None:
        self.editor.clear_formatting()
        self.editor.setFocus()
        self._sincronizar(self.editor.currentCharFormat())

    def _sincronizar(self, formato: QTextCharFormat) -> None:
        estilos = _estilos(formato)
        for estilo, botao in self.botoes.items():
            botao.setChecked(estilo in estilos)


def formatted_editor(parent: QWidget | None = None) -> tuple[QWidget, FormattedTextEdit]:
    """Editor com a barra de formatacao em cima. Devolve (bloco para o layout, editor)."""
    bloco = QWidget(parent)
    layout = QVBoxLayout(bloco)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(4)
    editor = FormattedTextEdit()
    bloco.format_bar = FormatBar(editor)
    layout.addWidget(bloco.format_bar)
    layout.addWidget(editor, 1)
    return bloco, editor


def preview_html(assunto: str, corpo_marcado: str, assinatura: str | None, para: str = "") -> str:
    """Cabecalho (para / assunto) + o email como chega, para mostrar na tela."""
    cabecalho = ""
    if para:
        cabecalho += f"<b>Para:</b> {html.escape(para)}<br>"
    cabecalho += f"<b>Assunto:</b> {html.escape(assunto or '(sem assunto)')}"
    # Fundo branco (como no programa de email), tambem no tema escuro.
    return (
        '<table width="100%" cellpadding="12" cellspacing="0" bgcolor="#ffffff"><tr><td>'
        f'<div style="color:#555555;font-family:Arial,Helvetica,sans-serif;font-size:13px">{cabecalho}</div>'
        '<hr>'
        f"{para_html(corpo_marcado, assinatura)}"
        "</td></tr></table>"
    )


class EmailPreviewDialog(QDialog):
    """Mostra o email como ele chega: formatado e com a assinatura."""

    def __init__(
        self,
        parent: QWidget | None,
        assunto: str,
        corpo_marcado: str,
        assinatura: str | None,
        para: str = "",
        aviso: str = "",
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Prévia do email")
        self.resize(640, 560)
        layout = QVBoxLayout(self)
        if aviso:
            rotulo = QLabel(aviso)
            rotulo.setObjectName("Muted")
            rotulo.setWordWrap(True)
            layout.addWidget(rotulo)
        self.browser = QTextBrowser()
        self.browser.setOpenExternalLinks(False)
        # Fundo branco, como no programa de email, mesmo no tema escuro.
        self.browser.setStyleSheet("QTextBrowser { background: #ffffff; color: #222222; }")
        self.browser.setHtml(preview_html(assunto, corpo_marcado, assinatura, para))
        layout.addWidget(self.browser, 1)
        botoes = QHBoxLayout()
        botoes.addStretch(1)
        fechar = make_button("Fechar", "primary")
        fechar.clicked.connect(self.accept)
        botoes.addWidget(fechar)
        layout.addLayout(botoes)
