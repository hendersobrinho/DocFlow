from __future__ import annotations

from html import escape
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from documentos_empresa_app.qt_ui.theme import tokens
from documentos_empresa_app.qt_ui.widgets.common import make_button
from documentos_empresa_app.utils.helpers import open_directory_in_file_manager
from documentos_empresa_app.utils import mcp_setup


class McpPanel(QWidget):
    """Liga o DocFlow ao Claude Desktop: mostra em quais arquivos o Claude procura a
    configuracao, para onde cada um aponta (pasta antiga, outra instalacao...) e grava
    em todos com um clique. Nao pede usuario nem senha: o servidor age como o usuario
    "claude" do DocFlow."""

    def __init__(self, services, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.services = services
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(12)

        intro = QLabel(
            "O Claude Desktop usa o DocFlow pelo servidor MCP. Aqui você vê onde o Claude procura a "
            "configuração neste computador, para onde ela aponta, e conecta com um clique. Não precisa de "
            'usuário nem senha: no Histórico de ações, o que o Claude fizer aparece como "claude".'
        )
        intro.setObjectName("Muted")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        form = QFormLayout()
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self.programa_label = QLabel()
        self.programa_label.setWordWrap(True)
        self.programa_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        form.addRow("Programa do MCP", self.programa_label)
        layout.addLayout(form)

        titulo = QLabel("Onde o Claude Desktop lê a configuração")
        titulo.setStyleSheet("font-weight: 600;")
        layout.addWidget(titulo)
        self.locais_box = QVBoxLayout()
        self.locais_box.setSpacing(8)
        layout.addLayout(self.locais_box)

        acoes = QHBoxLayout()
        self.conectar_button = make_button("Conectar ao Claude Desktop", "primary")
        self.conectar_button.clicked.connect(self.connect_claude)
        acoes.addWidget(self.conectar_button)
        copiar = make_button("Copiar configuração")
        copiar.setToolTip(
            "Para colar à mão no Claude: Configurações > Desenvolvedor > Editar configuração."
        )
        copiar.clicked.connect(self.copy_snippet)
        acoes.addWidget(copiar)
        atualizar = make_button("Verificar de novo", "quiet")
        atualizar.clicked.connect(self.refresh)
        acoes.addWidget(atualizar)
        acoes.addStretch(1)
        layout.addLayout(acoes)

        self.resultado_label = QLabel()
        self.resultado_label.setWordWrap(True)
        self.resultado_label.setTextFormat(Qt.TextFormat.RichText)
        self.resultado_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.resultado_label)
        layout.addStretch(1)

    # Dados ---------------------------------------------------------------------------------

    def refresh(self) -> None:
        comando, args = mcp_setup.server_command()
        t = tokens()
        programa = escape(" ".join([comando, *args]))
        if Path(comando).exists():
            self.programa_label.setText(programa)
        else:
            self.programa_label.setText(
                f'{programa}<br><span style="color:{t["danger"]};">Programa não encontrado nesta instalação.</span>'
            )
        while self.locais_box.count():
            item = self.locais_box.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        for local in mcp_setup.claude_config_locations():
            self.locais_box.addWidget(self._local_card(local))

    def _local_card(self, local: dict) -> QWidget:
        info = mcp_setup.inspect_config(local["caminho"])
        t = tokens()
        if info["erro"]:
            cor, situacao = t["danger"], escape(info["erro"])
        elif not info["existe"]:
            cor, situacao = t["muted"], "Arquivo ainda não existe - o Conectar cria."
        elif not info["tem_docflow"]:
            cor, situacao = t["warning"], "O DocFlow não está configurado neste arquivo."
        elif info["desta_instalacao"]:
            cor, situacao = t["success"], "Conectado a esta instalação do DocFlow. ✓"
        else:
            antigo = escape(" ".join([info["comando"] or "", *info["args"]]))
            falta = "" if info["programa_existe"] else " (essa pasta não existe mais)"
            cor, situacao = t["warning"], f"Aponta para outro lugar{falta}:<br><code>{antigo}</code>"
        aviso = ""
        if info["senha_no_arquivo"]:
            aviso = (
                f'<br><span style="color:{t["warning"]};">Tem usuário e senha em texto no arquivo; não são mais '
                "necessários e o Conectar tira.</span>"
            )

        card = QFrame()
        card.setObjectName("CadastroInfo")
        linha = QHBoxLayout(card)
        linha.setContentsMargins(0, 0, 0, 0)
        texto = QLabel(
            f'<b>{escape(local["tipo"])}</b><br>'
            f'<span style="color:{t["muted"]};">{escape(str(local["caminho"]))}</span><br>'
            f'<span style="color:{cor};">{situacao}</span>{aviso}'
        )
        texto.setTextFormat(Qt.TextFormat.RichText)
        texto.setWordWrap(True)
        texto.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        linha.addWidget(texto, 1)
        abrir = make_button("Abrir pasta", "quiet")
        abrir.clicked.connect(lambda _c=False, p=local["caminho"]: self._open_folder(p))
        linha.addWidget(abrir, 0, Qt.AlignmentFlag.AlignTop)
        return card

    # Acoes ---------------------------------------------------------------------------------

    def connect_claude(self) -> None:
        gravados, erros = [], []
        for local in mcp_setup.claude_config_locations():
            try:
                copia = mcp_setup.write_config(local["caminho"])
            except (OSError, ValueError) as exc:
                erros.append(f'{escape(str(local["caminho"]))}: {escape(str(exc))}')
                continue
            extra = f' <span style="color:{tokens()["muted"]};">(cópia do anterior: {escape(copia.name)})</span>' if copia else ""
            gravados.append(f'{escape(local["tipo"])}: {escape(str(local["caminho"]))}{extra}')
        self.refresh()
        partes = []
        if gravados:
            partes.append("<b>Salvo em:</b><br>" + "<br>".join(gravados))
            partes.append(
                "Agora feche o Claude Desktop de vez (botão direito no ícone perto do relógio > Sair) e abra "
                "de novo. O DocFlow aparece em Configurações > Desenvolvedor do Claude."
            )
        if erros:
            partes.append(f'<span style="color:{tokens()["danger"]};"><b>Não deu para salvar:</b><br>' + "<br>".join(erros) + "</span>")
        self.resultado_label.setText("<br><br>".join(partes))

    def copy_snippet(self) -> None:
        QGuiApplication.clipboard().setText(mcp_setup.config_snippet())
        self.resultado_label.setText(
            "Configuração copiada. No Claude: Configurações > Desenvolvedor > Editar configuração, cole dentro "
            'de "mcpServers" e salve. Feche o Claude de vez e abra de novo.'
        )

    def _open_folder(self, caminho: Path) -> None:
        pasta = Path(caminho).parent
        if not pasta.exists():
            QMessageBox.information(self, "Claude (MCP)", f"A pasta ainda não existe:\n{pasta}")
            return
        open_directory_in_file_manager(str(pasta))
