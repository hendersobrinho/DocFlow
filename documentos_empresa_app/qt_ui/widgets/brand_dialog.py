"""Base das telas de entrada (banco de dados, login, troca de senha, licenca): painel da
marca a esquerda e o formulario a direita, com mensagens dentro da propria tela."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

from documentos_empresa_app.qt_ui.brand import BrandPanel
from documentos_empresa_app.qt_ui.icons import app_icon
from documentos_empresa_app.qt_ui.theme import tokens
from documentos_empresa_app.utils.resources import get_icons_directory

FIELD_HEIGHT = 40


def add_password_toggle(line_edit: QLineEdit) -> None:
    """Olho no fim do campo para mostrar/esconder a senha."""
    icons = get_icons_directory()
    show_icon, hide_icon = QIcon(str(icons / "eye.svg")), QIcon(str(icons / "eye_off.svg"))
    action = line_edit.addAction(show_icon, QLineEdit.ActionPosition.TrailingPosition)
    action.setToolTip("Mostrar senha")

    def toggle() -> None:
        visible = line_edit.echoMode() == QLineEdit.EchoMode.Password
        line_edit.setEchoMode(QLineEdit.EchoMode.Normal if visible else QLineEdit.EchoMode.Password)
        action.setIcon(hide_icon if visible else show_icon)
        action.setToolTip("Esconder senha" if visible else "Mostrar senha")

    action.triggered.connect(toggle)


class BrandDialog(QDialog):
    """Janela com o painel da marca. Use add_heading, add_field, add_widget e, no fim,
    add_actions/add_footer. show_message mostra erro/sucesso na propria tela."""

    def __init__(
        self,
        panel_title: str,
        panel_subtitle: str,
        *,
        panel_width: int = 340,
        animated: bool = True,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowIcon(app_icon())
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.brand_panel = BrandPanel(panel_title, panel_subtitle, animated=animated)
        self.brand_panel.setFixedWidth(panel_width)
        root.addWidget(self.brand_panel)

        self.form_area = QWidget()
        self.form_area.setObjectName("BrandForm")
        root.addWidget(self.form_area, 1)
        self.form_layout = QVBoxLayout(self.form_area)
        self.form_layout.setContentsMargins(40, 36, 40, 24)
        self.form_layout.setSpacing(6)

        self.message_label = QLabel()
        self.message_label.setObjectName("FormMessage")
        self.message_label.setWordWrap(True)
        self.message_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.message_label.hide()
        self._apply_style()

    # Montagem ------------------------------------------------------------------------

    def add_heading(self, title: str, subtitle: str = "") -> None:
        heading = QLabel(title)
        heading.setObjectName("FormHeading")
        self.form_layout.addWidget(heading)
        if subtitle:
            sub = QLabel(subtitle)
            sub.setObjectName("FormSubtitle")
            sub.setWordWrap(True)
            self.form_layout.addWidget(sub)
        self.form_layout.addSpacing(18)

    def add_field(self, label: str, widget: QWidget, hint: str = "") -> QWidget:
        caption = QLabel(label)
        caption.setObjectName("FieldLabel")
        caption.setBuddy(widget)
        self.form_layout.addWidget(caption)
        if isinstance(widget, QLineEdit):
            widget.setMinimumHeight(FIELD_HEIGHT)
        else:
            widget.setMinimumHeight(FIELD_HEIGHT - 2)
        self.form_layout.addWidget(widget)
        if hint:
            hint_label = QLabel(hint)
            hint_label.setObjectName("FieldHint")
            hint_label.setWordWrap(True)
            self.form_layout.addWidget(hint_label)
        self.form_layout.addSpacing(8)
        return widget

    def add_widget(self, widget: QWidget, stretch: int = 0) -> QWidget:
        self.form_layout.addWidget(widget, stretch)
        return widget

    def add_message_area(self) -> None:
        self.form_layout.addWidget(self.message_label)

    def add_footer(self, text: str) -> QLabel:
        footer = QLabel(text)
        footer.setObjectName("FormFooter")
        footer.setWordWrap(True)
        self.form_layout.addSpacing(10)
        self.form_layout.addWidget(footer)
        return footer

    # Mensagens -----------------------------------------------------------------------

    def show_message(self, text: str, kind: str = "error") -> None:
        """kind: error, success ou info. A mensagem fica na tela ate a proxima acao."""
        self.message_label.setProperty("kind", kind)
        self.message_label.setText(text)
        self.message_label.style().unpolish(self.message_label)
        self.message_label.style().polish(self.message_label)
        self.message_label.show()

    def clear_message(self) -> None:
        self.message_label.hide()

    def _apply_style(self) -> None:
        t = tokens()
        self.setStyleSheet(
            f"""
            QWidget#BrandForm {{ background: {t["surface"]}; }}
            QLabel#FormHeading {{
                font-family: "Sora", "Inter", "Segoe UI";
                font-size: 19pt;
                font-weight: 600;
                color: {t["text"]};
            }}
            QLabel#FormSubtitle {{ color: {t["muted"]}; font-size: 10pt; }}
            QLabel#FieldLabel {{ color: {t["text"]}; font-weight: 600; font-size: 9.5pt; }}
            QLabel#FieldHint {{ color: {t["muted"]}; font-size: 8.5pt; }}
            QLabel#FormFooter {{ color: {t["muted"]}; font-size: 8.5pt; }}
            QLabel#FormMessage {{
                border-radius: 8px;
                padding: 9px 12px;
                font-size: 9.5pt;
            }}
            QLabel#FormMessage[kind="error"] {{
                background: {t["danger_soft"]};
                color: {t["danger"]};
                border-left: 3px solid {t["danger"]};
            }}
            QLabel#FormMessage[kind="success"] {{
                background: {t["success_soft"]};
                color: {t["success"]};
                border-left: 3px solid {t["success"]};
            }}
            QLabel#FormMessage[kind="info"] {{
                background: {t["accent_soft"]};
                color: {t["text"]};
                border-left: 3px solid {t["focus"]};
            }}
            QPushButton[variant="primary"] {{ min-height: 40px; font-size: 10.5pt; }}
            """
        )
