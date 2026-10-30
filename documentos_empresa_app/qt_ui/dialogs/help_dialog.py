from __future__ import annotations

from PySide6.QtCore import QUrl, Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QSplitter,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from documentos_empresa_app.qt_ui.dialogs.help_content import (
    DEFAULT_HELP_TOPIC_ID,
    HELP_TOPICS,
    HELP_TOPICS_BY_ID,
)
from documentos_empresa_app.qt_ui.icons import app_icon
from documentos_empresa_app.utils.common import APP_NAME

_TOPIC_ID_ROLE = Qt.ItemDataRole.UserRole


class HelpDialog(QDialog):
    """Manual do programa, aberto com F1 - lista de topicos a esquerda, conteudo a
    direita. Nao-modal de proposito: e uma janela de referencia, o usuario deve
    poder consultar e continuar trabalhando no resto do app ao mesmo tempo."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"{APP_NAME} - Manual")
        self.setWindowIcon(app_icon())
        self.setModal(False)
        self.resize(920, 640)
        self.setMinimumSize(680, 420)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(splitter, 1)

        sidebar = QWidget()
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(14, 14, 8, 14)
        sidebar_layout.setSpacing(8)

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Buscar no manual...")
        self.search_edit.textChanged.connect(self._filter_topics)
        sidebar_layout.addWidget(self.search_edit)

        self.topic_list = QListWidget()
        self.topic_list.setMinimumWidth(220)
        for topic in HELP_TOPICS:
            item = QListWidgetItem(topic.title)
            item.setData(_TOPIC_ID_ROLE, topic.id)
            self.topic_list.addItem(item)
        self.topic_list.currentItemChanged.connect(self._on_topic_selected)
        sidebar_layout.addWidget(self.topic_list, 1)

        splitter.addWidget(sidebar)

        content_wrapper = QWidget()
        content_layout = QVBoxLayout(content_wrapper)
        content_layout.setContentsMargins(8, 14, 14, 14)
        content_layout.setSpacing(4)

        self.f1_hint_label = QLabel("Aperte F1 em qualquer tela do programa para abrir o manual nessa pagina.")
        self.f1_hint_label.setObjectName("Muted")
        self.f1_hint_label.setWordWrap(True)
        content_layout.addWidget(self.f1_hint_label)

        self.content_browser = QTextBrowser()
        self.content_browser.setOpenLinks(False)
        self.content_browser.anchorClicked.connect(self._on_anchor_clicked)
        content_layout.addWidget(self.content_browser, 1)

        splitter.addWidget(content_wrapper)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([240, 680])

        self.show_topic(DEFAULT_HELP_TOPIC_ID)

    def show_topic(self, topic_id: str) -> None:
        topic = HELP_TOPICS_BY_ID.get(topic_id) or HELP_TOPICS_BY_ID[DEFAULT_HELP_TOPIC_ID]
        self.content_browser.setHtml(topic.html)
        self.content_browser.verticalScrollBar().setValue(0)
        self._select_topic_in_list(topic.id)

    def _select_topic_in_list(self, topic_id: str) -> None:
        for row in range(self.topic_list.count()):
            item = self.topic_list.item(row)
            if item.data(_TOPIC_ID_ROLE) == topic_id:
                self.topic_list.blockSignals(True)
                self.topic_list.setCurrentItem(item)
                self.topic_list.blockSignals(False)
                return

    def _on_topic_selected(self, current: QListWidgetItem | None, _previous: QListWidgetItem | None) -> None:
        if current is None:
            return
        topic_id = current.data(_TOPIC_ID_ROLE)
        topic = HELP_TOPICS_BY_ID.get(topic_id)
        if topic is None:
            return
        self.content_browser.setHtml(topic.html)
        self.content_browser.verticalScrollBar().setValue(0)

    def _on_anchor_clicked(self, url: QUrl) -> None:
        if url.scheme() == "topic":
            # topic:revisao -> host() da URL vira "revisao"
            self.show_topic(url.host() or url.path().lstrip("/"))

    def _filter_topics(self, text: str) -> None:
        needle = text.strip().casefold()
        for row in range(self.topic_list.count()):
            item = self.topic_list.item(row)
            topic = HELP_TOPICS_BY_ID[item.data(_TOPIC_ID_ROLE)]
            matches = not needle or needle in topic.title.casefold() or needle in topic.html.casefold()
            item.setHidden(not matches)
