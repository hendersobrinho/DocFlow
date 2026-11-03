"""Editor do texto do email com negrito, italico, sublinhado e imagens no meio do texto, e a
previa de como o email chega (com a assinatura). O texto sai e entra no formato de
utils/email_format; as imagens ficam no banco (EnvioProgramadoService.salvar_imagem)."""

from __future__ import annotations

import html
from pathlib import Path
import re

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, Qt, QUrl
from PySide6.QtGui import QFont, QImage, QTextCharFormat, QTextCursor, QTextDocument, QTextImageFormat
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMessageBox,
    QTextBrowser,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from documentos_empresa_app.qt_ui.widgets.common import make_button
from documentos_empresa_app.utils.common import ValidationError
from documentos_empresa_app.utils.email_format import (
    ITALICO,
    NEGRITO,
    SUBLINHADO,
    Imagem,
    de_trechos,
    imagem_do_trecho,
    para_html,
    trechos,
)

# Nome da imagem dentro do documento do Qt (o recurso e registrado com esse endereco).
_ESQUEMA = "docflow-img"
_NOME_IMAGEM = re.compile(rf"^{_ESQUEMA}:(\d+)$")
LARGURA_PADRAO = 600
_TIPOS_ARQUIVO = {".png": "png", ".jpg": "jpeg", ".jpeg": "jpeg", ".gif": "gif"}


def endereco_imagem(imagem_id: int) -> str:
    return f"{_ESQUEMA}:{int(imagem_id)}"


def registrar_imagens(documento: QTextDocument, imagens: dict[int, dict]) -> None:
    """Deixa as imagens ({id: {"dados"}}) disponiveis para o HTML com src="docflow-img:<id>"."""
    for imagem_id, imagem in (imagens or {}).items():
        qimage = QImage.fromData(imagem["dados"])
        if not qimage.isNull():
            documento.addResource(QTextDocument.ResourceType.ImageResource, QUrl(endereco_imagem(imagem_id)), qimage)

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
    """QTextEdit que guarda so negrito, italico, sublinhado e imagens. Colar traz so o texto
    (sem as cores e fontes de quem copiou) ou a imagem copiada; Ctrl+B, Ctrl+I e Ctrl+U
    formatam. imagens: quem guarda e devolve as imagens (o EnvioProgramadoService, com
    salvar_imagem e imagem); sem ele o editor nao aceita imagens."""

    def __init__(self, parent: QWidget | None = None, imagens=None) -> None:
        super().__init__(parent)
        self.setAcceptRichText(False)
        self.imagens = imagens

    def aceita_imagens(self) -> bool:
        return self.imagens is not None

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
                if fragmento.isValid() and fragmento.charFormat().isImageFormat():
                    formato = fragmento.charFormat().toImageFormat()
                    achado = _NOME_IMAGEM.match(formato.name())
                    if achado:
                        largura = int(formato.width()) or None
                        for _ in range(fragmento.text().count("\ufffc") or 1):
                            lista.append(("", frozenset({Imagem(int(achado.group(1)), largura)})))
                elif fragmento.isValid():
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
            imagem = imagem_do_trecho(estilos)
            if imagem:
                self._inserir_imagem(cursor, imagem.id, imagem.largura)
                continue
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

    # Imagens -----------------------------------------------------------------------------

    def _inserir_imagem(self, cursor: QTextCursor, imagem_id: int, largura: int | None) -> None:
        endereco = endereco_imagem(imagem_id)
        if self.document().resource(QTextDocument.ResourceType.ImageResource, QUrl(endereco)) is None and self.imagens:
            dados = self.imagens.imagem(imagem_id)
            if dados:
                registrar_imagens(self.document(), {imagem_id: dados})
        formato = QTextImageFormat()
        formato.setName(endereco)
        if largura:
            qimage = self.document().resource(QTextDocument.ResourceType.ImageResource, QUrl(endereco))
            formato.setWidth(largura)
            if isinstance(qimage, QImage) and qimage.width():
                formato.setHeight(largura * qimage.height() / qimage.width())
        cursor.insertImage(formato)

    def insert_image_data(self, dados: bytes, tipo: str, nome: str | None = None) -> int | None:
        """Guarda a imagem no banco e poe no cursor (largura de ate 600 px). Devolve o id."""
        if not self.imagens:
            return None
        qimage = QImage.fromData(dados)
        if qimage.isNull():
            raise ValidationError("Nao foi possivel abrir essa imagem.")
        imagem_id = self.imagens.salvar_imagem(dados, tipo, nome)
        registrar_imagens(self.document(), {imagem_id: {"dados": dados}})
        self._inserir_imagem(self.textCursor(), imagem_id, min(qimage.width(), LARGURA_PADRAO))
        return imagem_id

    def insert_image_file(self, caminho: str) -> int | None:
        arquivo = Path(caminho)
        tipo = _TIPOS_ARQUIVO.get(arquivo.suffix.lower())
        if not tipo:
            raise ValidationError("A imagem precisa ser PNG, JPG ou GIF.")
        return self.insert_image_data(arquivo.read_bytes(), tipo, arquivo.name)

    def choose_image(self) -> None:
        caminho, _filtro = QFileDialog.getOpenFileName(self, "Inserir imagem", "", "Imagens (*.png *.jpg *.jpeg *.gif)")
        if caminho:
            self._tentar(lambda: self.insert_image_file(caminho))

    def _tentar(self, acao) -> None:
        try:
            acao()
        except (ValidationError, OSError) as exc:
            QMessageBox.warning(self, "Imagem", str(exc))

    def canInsertFromMimeData(self, source) -> bool:  # noqa: N802 - API do Qt
        if self.aceita_imagens() and (source.hasImage() or self._arquivos_de_imagem(source)):
            return True
        return super().canInsertFromMimeData(source)

    @staticmethod
    def _arquivos_de_imagem(source) -> list[str]:
        if not source.hasUrls():
            return []
        return [
            url.toLocalFile() for url in source.urls()
            if url.isLocalFile() and Path(url.toLocalFile()).suffix.lower() in _TIPOS_ARQUIVO
        ]

    def insertFromMimeData(self, source) -> None:  # noqa: N802 - API do Qt
        """Colar/arrastar imagem (print, imagem copiada de outro email ou arquivo) poe a imagem
        no texto; o resto entra como texto puro."""
        if self.aceita_imagens():
            arquivos = self._arquivos_de_imagem(source)
            if arquivos:
                for caminho in arquivos:
                    self._tentar(lambda c=caminho: self.insert_image_file(c))
                return
            if source.hasImage():
                qimage = source.imageData()
                if isinstance(qimage, QImage) and not qimage.isNull():
                    self._tentar(lambda: self.insert_image_data(_png(qimage), "png", "imagem colada.png"))
                    if source.hasText() and not source.hasHtml():
                        super().insertFromMimeData(source)
                    return
        super().insertFromMimeData(source)

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802 - API do Qt
        """Duplo clique numa imagem muda o tamanho dela."""
        cursor = self.cursorForPosition(event.position().toPoint())
        for deslocamento in (0, 1):
            teste = QTextCursor(cursor)
            if deslocamento:
                teste.movePosition(QTextCursor.MoveOperation.NextCharacter)
            formato = teste.charFormat()
            if formato.isImageFormat() and _NOME_IMAGEM.match(formato.toImageFormat().name()):
                self._redimensionar(teste)
                return
        super().mouseDoubleClickEvent(event)

    def _redimensionar(self, cursor: QTextCursor) -> None:
        formato = cursor.charFormat().toImageFormat()
        qimage = self.document().resource(QTextDocument.ResourceType.ImageResource, QUrl(formato.name()))
        natural = qimage.width() if isinstance(qimage, QImage) else 0
        atual = int(formato.width()) or natural or LARGURA_PADRAO
        largura, ok = QInputDialog.getInt(self, "Tamanho da imagem", "Largura no email (px):", atual, 40, 1200)
        if not ok:
            return
        cursor.movePosition(QTextCursor.MoveOperation.PreviousCharacter)
        cursor.movePosition(QTextCursor.MoveOperation.NextCharacter, QTextCursor.MoveMode.KeepAnchor)
        novo = QTextImageFormat(formato)
        novo.setWidth(largura)
        if natural and isinstance(qimage, QImage):
            novo.setHeight(largura * qimage.height() / natural)
        cursor.setCharFormat(novo)

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
        if editor.aceita_imagens():
            imagem = QToolButton()
            imagem.setText("Imagem...")
            imagem.setToolTip("Põe uma imagem no texto. Também dá para colar (Ctrl+V) uma imagem copiada. "
                              "Duplo clique na imagem muda o tamanho.")
            imagem.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            imagem.clicked.connect(editor.choose_image)
            layout.addWidget(imagem)
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


def _png(qimage: QImage) -> bytes:
    bruto = QByteArray()
    buffer = QBuffer(bruto)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    qimage.save(buffer, "PNG")
    buffer.close()
    return bytes(bruto)


def formatted_editor(parent: QWidget | None = None, imagens=None) -> tuple[QWidget, FormattedTextEdit]:
    """Editor com a barra de formatacao em cima. Devolve (bloco para o layout, editor).
    imagens: o EnvioProgramadoService, para aceitar imagens no texto."""
    bloco = QWidget(parent)
    layout = QVBoxLayout(bloco)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(4)
    editor = FormattedTextEdit(imagens=imagens)
    bloco.format_bar = FormatBar(editor)
    layout.addWidget(bloco.format_bar)
    layout.addWidget(editor, 1)
    return bloco, editor


def _com_alturas(pagina: str, imagens: dict[int, dict]) -> str:
    """O Qt nao calcula a altura de <img width=...> sozinho: poe a altura proporcional."""

    def ajustar(achado: re.Match) -> str:
        imagem = imagens.get(int(achado.group(1)))
        qimage = QImage.fromData(imagem["dados"]) if imagem else QImage()
        if qimage.isNull() or not qimage.width():
            return achado.group(0)
        altura = round(int(achado.group(2)) * qimage.height() / qimage.width())
        return f'{achado.group(0)} height="{altura}"'

    return re.sub(rf'<img src="{_ESQUEMA}:(\d+)" width="(\d+)"', ajustar, pagina)


def preview_html(
    assunto: str, corpo_marcado: str, assinatura: dict | None, para: str = "", imagens: dict[int, dict] | None = None
) -> str:
    # As imagens do meio do texto aparecem pelo endereco docflow-img:<id> (veja registrar_imagens).
    """Cabecalho (para / assunto) + o email como chega, para mostrar na tela. assinatura: o
    que load_email_signature() devolve (texto, imagem, largura)."""
    assinatura = assinatura or {}
    imagem = assinatura.get("imagem")
    src = QUrl.fromLocalFile(imagem).toString() if imagem else None
    cabecalho = ""
    if para:
        cabecalho += f"<b>Para:</b> {html.escape(para)}<br>"
    cabecalho += f"<b>Assunto:</b> {html.escape(assunto or '(sem assunto)')}"
    # Fundo branco (como no programa de email), tambem no tema escuro.
    pagina = (
        '<table width="100%" cellpadding="12" cellspacing="0" bgcolor="#ffffff"><tr><td>'
        f'<div style="color:#555555;font-family:Arial,Helvetica,sans-serif;font-size:13px">{cabecalho}</div>'
        '<hr>'
        f'{para_html(corpo_marcado, assinatura.get("texto"), src, assinatura.get("largura"), endereco_imagem)}'
        "</td></tr></table>"
    )
    if imagens:
        # No Qt o line-height tambem multiplica a linha da imagem (no programa de email nao).
        pagina = _com_alturas(pagina.replace("line-height:1.5;", ""), imagens)
    return pagina


class EmailPreviewDialog(QDialog):
    """Mostra o email como ele chega: formatado e com a assinatura."""

    def __init__(
        self,
        parent: QWidget | None,
        assunto: str,
        corpo_marcado: str,
        assinatura: dict | None,
        para: str = "",
        aviso: str = "",
        imagens: dict[int, dict] | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Prévia do email")
        self.resize(720, 600)
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
        self.browser.setHtml(preview_html(assunto, corpo_marcado, assinatura, para, imagens))
        # Depois do setHtml (ele limpa os recursos do documento).
        registrar_imagens(self.browser.document(), imagens or {})
        layout.addWidget(self.browser, 1)
        botoes = QHBoxLayout()
        botoes.addStretch(1)
        fechar = make_button("Fechar", "primary")
        fechar.clicked.connect(self.accept)
        botoes.addWidget(fechar)
        layout.addLayout(botoes)
