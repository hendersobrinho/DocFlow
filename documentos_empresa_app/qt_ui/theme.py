from __future__ import annotations

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

from documentos_empresa_app.utils.helpers import load_config, save_config

DARK_TOKENS = {
    "window": "#0F1420",
    "surface": "#1B2333",
    "surface_alt": "#232D42",
    "surface_hover": "#2A3550",
    "border": "#2E3A52",
    "border_strong": "#3A4867",
    "text": "#E7ECF5",
    "muted": "#8D99AE",
    "accent": "#2F6FED",
    "accent_hover": "#4A82F0",
    "accent_pressed": "#1E4FAA",
    "accent_soft": "#1B2A4A",
    "on_accent": "#FFFFFF",
    "danger": "#C34747",
    "danger_hover": "#D45A5A",
    "danger_soft": "#3A2020",
    "success": "#3E9B5F",
    "success_soft": "#1C3327",
    "warning": "#C9A227",
    "warning_soft": "#38311A",
    "disabled_bg": "#20283A",
    "disabled_fg": "#5B6678",
    "selection": "#2F6FED",
    "status_recebido": "#1C3327",
    "status_recebido_fg": "#7ED6A0",
    "status_pendente": "#3A2020",
    "status_pendente_fg": "#F0A0A0",
    "status_nao_cobrar": "#38311A",
    "status_nao_cobrar_fg": "#E3C86A",
    "status_encerrado": "#2A2F3A",
    "status_encerrado_fg": "#9AA5B5",
    "status_vazio": "#1B2333",
    "chart_grid": "#2E3A52",
}

LIGHT_TOKENS = {
    "window": "#EEF3F8",
    "surface": "#FFFFFF",
    "surface_alt": "#F7FAFD",
    "surface_hover": "#EDF3FB",
    "border": "#D5DEE8",
    "border_strong": "#B8C7D8",
    "text": "#203040",
    "muted": "#617286",
    "accent": "#2F6FED",
    "accent_hover": "#255FD0",
    "accent_pressed": "#1E4FAA",
    "accent_soft": "#DCE9FF",
    "on_accent": "#FFFFFF",
    "danger": "#C34747",
    "danger_hover": "#AE3737",
    "danger_soft": "#F7DEDE",
    "success": "#2F7D4C",
    "success_soft": "#D9F2D9",
    "warning": "#9C7C14",
    "warning_soft": "#F6EFC7",
    "disabled_bg": "#E8EEF5",
    "disabled_fg": "#8A99AA",
    "selection": "#2F6FED",
    "status_recebido": "#D9F2D9",
    "status_recebido_fg": "#1F5B35",
    "status_pendente": "#FAD4D4",
    "status_pendente_fg": "#7C2020",
    "status_nao_cobrar": "#F6EFC7",
    "status_nao_cobrar_fg": "#6B5510",
    "status_encerrado": "#E2E2E2",
    "status_encerrado_fg": "#4F5560",
    "status_vazio": "#FFFFFF",
    "chart_grid": "#D5DEE8",
}

STATUS_TOKEN_KEYS = {
    "Recebido": ("status_recebido", "status_recebido_fg"),
    "Pendente": ("status_pendente", "status_pendente_fg"),
    "Nao cobrar": ("status_nao_cobrar", "status_nao_cobrar_fg"),
    "Encerrado": ("status_encerrado", "status_encerrado_fg"),
}

SITUATION_COLORS = {
    "concluida": "success",
    "em_andamento": "accent",
    "nao_iniciada": "warning",
    "com_pendencia": "danger",
    "mes_em_atraso": "danger",
    "sem_documentos": "muted",
    "sem_cobranca": "muted",
}


def _build_stylesheet(t: dict[str, str]) -> str:
    return f"""
QWidget {{
    font-family: "Segoe UI";
    font-size: 10pt;
    color: {t["text"]};
}}
QMainWindow, QDialog {{
    background: {t["window"]};
}}
QFrame#Sidebar {{
    background: {t["surface"]};
    border: none;
    border-right: 1px solid {t["border"]};
}}
QLabel#SidebarTitle {{
    font-size: 15pt;
    font-weight: 700;
    color: {t["text"]};
    padding: 4px 8px;
}}
QPushButton#NavButton {{
    background: transparent;
    color: {t["muted"]};
    border: none;
    border-radius: 8px;
    padding: 10px 14px;
    text-align: left;
    font-size: 10.5pt;
}}
QPushButton#NavButton:hover {{
    background: {t["surface_hover"]};
    color: {t["text"]};
}}
QPushButton#NavButton[active="true"] {{
    background: {t["accent_soft"]};
    color: {t["text"]};
    font-weight: 600;
}}
QFrame#Card, QFrame#KpiCard {{
    background: {t["surface"]};
    border: 1px solid {t["border"]};
    border-radius: 12px;
}}
QLabel#PageTitle {{
    font-size: 16pt;
    font-weight: 700;
}}
QLabel#PageSubtitle, QLabel#Muted {{
    color: {t["muted"]};
}}
QLabel#KpiValue {{
    font-size: 22pt;
    font-weight: 700;
}}
QLabel#KpiLabel {{
    color: {t["muted"]};
    font-size: 9.5pt;
}}
QPushButton {{
    background: {t["surface_alt"]};
    color: {t["text"]};
    border: 1px solid {t["border_strong"]};
    border-radius: 8px;
    padding: 7px 16px;
}}
QPushButton:hover {{
    background: {t["surface_hover"]};
}}
QPushButton:disabled {{
    background: {t["disabled_bg"]};
    color: {t["disabled_fg"]};
    border-color: {t["border"]};
}}
QPushButton[variant="primary"] {{
    background: {t["accent"]};
    color: {t["on_accent"]};
    border: none;
    font-weight: 600;
}}
QPushButton[variant="primary"]:hover {{
    background: {t["accent_hover"]};
}}
QPushButton[variant="primary"]:pressed {{
    background: {t["accent_pressed"]};
}}
QPushButton[variant="primary"]:disabled {{
    background: {t["disabled_bg"]};
    color: {t["disabled_fg"]};
}}
QPushButton[variant="danger"] {{
    background: {t["danger_soft"]};
    color: {t["danger"]};
    border: 1px solid {t["danger"]};
}}
QPushButton[variant="danger"]:hover {{
    background: {t["danger"]};
    color: {t["on_accent"]};
}}
QPushButton[variant="quiet"] {{
    background: transparent;
    border: none;
    color: {t["muted"]};
}}
QPushButton[variant="quiet"]:hover {{
    background: {t["surface_hover"]};
    color: {t["text"]};
}}
QLineEdit, QComboBox, QSpinBox, QTextEdit, QPlainTextEdit {{
    background: {t["surface"]};
    color: {t["text"]};
    border: 1px solid {t["border_strong"]};
    border-radius: 8px;
    padding: 6px 10px;
    selection-background-color: {t["selection"]};
    selection-color: {t["on_accent"]};
}}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QTextEdit:focus, QPlainTextEdit:focus {{
    border-color: {t["accent"]};
}}
QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled, QTextEdit:disabled {{
    background: {t["disabled_bg"]};
    color: {t["disabled_fg"]};
}}
QComboBox::drop-down {{
    border: none;
    width: 26px;
}}
QComboBox QAbstractItemView {{
    background: {t["surface"]};
    color: {t["text"]};
    border: 1px solid {t["border"]};
    selection-background-color: {t["accent_soft"]};
    selection-color: {t["text"]};
}}
QTableView, QTreeView, QListWidget {{
    background: {t["surface"]};
    alternate-background-color: {t["surface_alt"]};
    color: {t["text"]};
    border: 1px solid {t["border"]};
    border-radius: 8px;
    gridline-color: {t["border"]};
    selection-background-color: {t["accent_soft"]};
    selection-color: {t["text"]};
}}
QHeaderView::section {{
    background: {t["surface_alt"]};
    color: {t["text"]};
    border: none;
    border-bottom: 1px solid {t["border_strong"]};
    border-right: 1px solid {t["border"]};
    padding: 8px 10px;
    font-weight: 600;
}}
QTableCornerButton::section {{
    background: {t["surface_alt"]};
    border: none;
}}
QScrollBar:vertical {{
    background: transparent;
    width: 12px;
    margin: 2px;
}}
QScrollBar::handle:vertical {{
    background: {t["border_strong"]};
    border-radius: 5px;
    min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{
    background: {t["muted"]};
}}
QScrollBar:horizontal {{
    background: transparent;
    height: 12px;
    margin: 2px;
}}
QScrollBar::handle:horizontal {{
    background: {t["border_strong"]};
    border-radius: 5px;
    min-width: 30px;
}}
QScrollBar::add-line, QScrollBar::sub-line {{
    width: 0; height: 0;
}}
QMenu {{
    background: {t["surface"]};
    color: {t["text"]};
    border: 1px solid {t["border"]};
    border-radius: 8px;
    padding: 6px;
}}
QMenu::item {{
    padding: 7px 22px;
    border-radius: 6px;
}}
QMenu::item:selected {{
    background: {t["accent_soft"]};
}}
QMenu::separator {{
    height: 1px;
    background: {t["border"]};
    margin: 5px 8px;
}}
QCheckBox, QRadioButton {{
    spacing: 8px;
}}
QCheckBox::indicator, QRadioButton::indicator {{
    width: 17px;
    height: 17px;
}}
QGroupBox {{
    border: 1px solid {t["border"]};
    border-radius: 10px;
    margin-top: 12px;
    padding-top: 8px;
    font-weight: 600;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 4px;
    color: {t["text"]};
}}
QSplitter::handle {{
    background: {t["border"]};
}}
QToolTip {{
    background: {t["surface_alt"]};
    color: {t["text"]};
    border: 1px solid {t["border_strong"]};
    padding: 6px;
    border-radius: 6px;
}}
QTabWidget::pane {{
    border: 1px solid {t["border"]};
    border-radius: 8px;
}}
QTabBar::tab {{
    background: {t["surface_alt"]};
    color: {t["muted"]};
    padding: 8px 18px;
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
}}
QTabBar::tab:selected {{
    background: {t["surface"]};
    color: {t["text"]};
}}
QStatusBar {{
    background: {t["surface"]};
    color: {t["muted"]};
    border-top: 1px solid {t["border"]};
}}
"""


def _build_palette(t: dict[str, str]) -> QPalette:
    palette = QPalette()
    roles = {
        QPalette.ColorRole.Window: t["window"],
        QPalette.ColorRole.WindowText: t["text"],
        QPalette.ColorRole.Base: t["surface"],
        QPalette.ColorRole.AlternateBase: t["surface_alt"],
        QPalette.ColorRole.Text: t["text"],
        QPalette.ColorRole.Button: t["surface_alt"],
        QPalette.ColorRole.ButtonText: t["text"],
        QPalette.ColorRole.Highlight: t["selection"],
        QPalette.ColorRole.HighlightedText: t["on_accent"],
        QPalette.ColorRole.ToolTipBase: t["surface_alt"],
        QPalette.ColorRole.ToolTipText: t["text"],
        QPalette.ColorRole.PlaceholderText: t["muted"],
        QPalette.ColorRole.Link: t["accent"],
    }
    for role, color in roles.items():
        palette.setColor(role, QColor(color))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor(t["disabled_fg"]))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor(t["disabled_fg"]))
    return palette


class ThemeManager(QObject):
    """Gerencia o tema dark/light do aplicativo com persistencia em config.json."""

    theme_changed = Signal(str)

    _instance: ThemeManager | None = None

    def __init__(self) -> None:
        super().__init__()
        stored = str(load_config().get("theme") or "").strip().lower()
        self._mode = stored if stored in {"dark", "light"} else "dark"

    @classmethod
    def instance(cls) -> ThemeManager:
        if cls._instance is None:
            cls._instance = ThemeManager()
        return cls._instance

    @property
    def mode(self) -> str:
        return self._mode

    @property
    def tokens(self) -> dict[str, str]:
        return DARK_TOKENS if self._mode == "dark" else LIGHT_TOKENS

    def apply(self, app: QApplication) -> None:
        app.setStyle("Fusion")
        app.setPalette(_build_palette(self.tokens))
        app.setStyleSheet(_build_stylesheet(self.tokens))

    def set_mode(self, mode: str) -> None:
        if mode not in {"dark", "light"} or mode == self._mode:
            return
        self._mode = mode
        config = load_config()
        config["theme"] = mode
        save_config(config)
        app = QApplication.instance()
        if app is not None:
            self.apply(app)
        self.theme_changed.emit(mode)

    def toggle(self) -> None:
        self.set_mode("light" if self._mode == "dark" else "dark")


def tokens() -> dict[str, str]:
    return ThemeManager.instance().tokens


def status_colors(status: str) -> tuple[str, str]:
    """(background, foreground) para um status de documento no tema atual."""
    t = tokens()
    keys = STATUS_TOKEN_KEYS.get(status)
    if not keys:
        return t["status_vazio"], t["text"]
    return t[keys[0]], t[keys[1]]


def situation_color(situacao_key: str) -> str:
    t = tokens()
    return t[SITUATION_COLORS.get(situacao_key, "muted")]
