from __future__ import annotations

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

from documentos_empresa_app.qt_ui.brand import load_brand_fonts
from documentos_empresa_app.utils.helpers import load_config, save_config
from documentos_empresa_app.utils.resources import get_icons_directory

# Paleta da identidade visual (docflow-identidade/LEIA-ME.md): navy de base, ciano para
# ativo/foco, laranja para pendencia. Texto sobre ciano ou laranja e sempre navy (branco nao
# passa em contraste). Verde/vermelho ficam so para o que e semantico (recebido, erro).
DARK_TOKENS = {
    "window": "#0F1A33",          # Navy 900
    "surface": "#16254A",         # Navy 800
    "surface_alt": "#1B2C55",
    "surface_hover": "#22376A",
    "border": "#263A6B",
    "border_strong": "#2E4A85",   # Navy 600
    "text": "#E9EEF8",
    "muted": "#8C9BC0",           # Navy 300
    "accent": "#4BBDCD",          # Ciano Fluxo
    "accent_hover": "#66C9D7",
    "accent_pressed": "#38A6B6",
    "accent_soft": "#1B4060",
    "on_accent": "#203461",       # navy sobre ciano
    "focus": "#4BBDCD",
    "brand_orange": "#F9B259",
    "danger": "#E06666",
    "danger_hover": "#EB7D7D",
    "danger_soft": "#3D2230",
    "success": "#4CC38A",
    "success_soft": "#173B3A",
    "warning": "#F9B259",         # Laranja Dado
    "warning_soft": "#3B3326",
    "disabled_bg": "#1A2747",
    "disabled_fg": "#5B6C93",
    "selection": "#2E4A85",
    "selection_text": "#FFFFFF",
    "sidebar_bg": "#0B1428",
    "sidebar_border": "#1C2C52",
    "sidebar_text": "#C9D3EA",
    "sidebar_muted": "#6F80AA",
    "sidebar_hover": "#16254A",
    "sidebar_active": "#1B3A5A",
    "status_recebido": "#173B3A",
    "status_recebido_fg": "#7FE0B0",
    "status_pendente": "#3B3326",
    "status_pendente_fg": "#F9B259",
    "status_nao_cobrar": "#1F2C4D",
    "status_nao_cobrar_fg": "#9AA9CC",
    "status_encerrado": "#262F45",
    "status_encerrado_fg": "#A3AEC4",
    "status_vazio": "#16254A",
    "chart_grid": "#263A6B",
}

LIGHT_TOKENS = {
    "window": "#F2F5FA",          # Nevoa
    "surface": "#FFFFFF",
    "surface_alt": "#F7F9FC",
    "surface_hover": "#EAF0F8",
    "border": "#DCE3EE",          # Linha
    "border_strong": "#C2CCDC",
    "text": "#1B2335",            # Grafite
    "muted": "#5E6B82",           # Cinza
    "accent": "#203461",          # Navy Metodos
    "accent_hover": "#2E4A85",
    "accent_pressed": "#16254A",
    "accent_soft": "#E2F3F6",     # ciano bem claro: ativo/selecionado
    "on_accent": "#FFFFFF",
    "focus": "#4BBDCD",
    "brand_orange": "#F9B259",
    "danger": "#C0392B",
    "danger_hover": "#A93226",
    "danger_soft": "#FBE3E0",
    "success": "#1F8A5B",
    "success_soft": "#DDF3E8",
    "warning": "#B86E12",         # laranja escurecido para texto em fundo claro
    "warning_soft": "#FDEBD3",
    "disabled_bg": "#EDF1F7",
    "disabled_fg": "#98A3B6",
    "selection": "#203461",
    "selection_text": "#FFFFFF",
    "sidebar_bg": "#203461",
    "sidebar_border": "#203461",
    "sidebar_text": "#D5DDEF",
    "sidebar_muted": "#8C9BC0",
    "sidebar_hover": "#2A4174",
    "sidebar_active": "#2E4A85",
    "status_recebido": "#DDF3E8",
    "status_recebido_fg": "#17694A",
    "status_pendente": "#FDEBD3",
    "status_pendente_fg": "#8A4E0B",
    "status_nao_cobrar": "#E8ECF4",
    "status_nao_cobrar_fg": "#4D5A73",
    "status_encerrado": "#E3E6EC",
    "status_encerrado_fg": "#4F5868",
    "status_vazio": "#FFFFFF",
    "chart_grid": "#DCE3EE",
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
    # Setas das listas e campos numericos vem de SVGs em assets/icons (o tema substitui o
    # desenho padrao do Qt, que sumia com as bordas arredondadas).
    icons = get_icons_directory().as_posix()
    return f"""
QWidget {{
    font-family: "Inter", "Segoe UI";
    font-size: 10pt;
    color: {t["text"]};
}}
QMainWindow, QDialog {{
    background: {t["window"]};
}}
QFrame#Sidebar {{
    background: {t["sidebar_bg"]};
    border: none;
    border-right: 1px solid {t["sidebar_border"]};
}}
QFrame#Sidebar QLabel {{
    background: transparent;
}}
QLabel#NavSection {{
    color: {t["sidebar_muted"]};
    font-size: 8pt;
    font-weight: 600;
    letter-spacing: 1.2px;
    padding: 16px 14px 4px 14px;
}}
QLabel#SidebarFooter {{
    color: {t["sidebar_muted"]};
    font-size: 8.5pt;
    padding: 0px 8px;
}}
QPushButton#NavButton {{
    background: transparent;
    color: {t["sidebar_text"]};
    border: none;
    border-left: 3px solid transparent;
    border-radius: 8px;
    padding: 8px 14px 8px 11px;
    text-align: left;
    font-size: 10.5pt;
}}
QPushButton#NavButton:hover {{
    background: {t["sidebar_hover"]};
    color: #FFFFFF;
}}
QPushButton#NavButton[alert="true"] {{
    color: {t["brand_orange"]};
    font-weight: 600;
}}
QPushButton#NavButton[active="true"] {{
    background: {t["sidebar_active"]};
    border-left: 3px solid {t["focus"]};
    color: #FFFFFF;
    font-weight: 600;
}}
QFrame#Sidebar QPushButton[variant="quiet"] {{
    color: {t["sidebar_text"]};
}}
QFrame#Sidebar QPushButton[variant="quiet"]:hover {{
    background: {t["sidebar_hover"]};
    color: #FFFFFF;
}}
QFrame#Sidebar QPushButton[variant="sidebar"] {{
    background: transparent;
    color: {t["sidebar_text"]};
    border: 1px solid {t["sidebar_active"]};
}}
QFrame#Sidebar QPushButton[variant="sidebar"]:hover {{
    background: {t["sidebar_hover"]};
    color: #FFFFFF;
}}
QFrame#Sidebar QPushButton[variant="update"] {{
    background: #4BBDCD;
    color: #203461;
    border: none;
    font-weight: 700;
    padding: 8px 10px;
    margin-bottom: 6px;
}}
QFrame#Sidebar QPushButton[variant="update"]:hover {{
    background: #66C9D7;
}}
QFrame#Sidebar QPushButton[variant="danger"] {{
    background: transparent;
    color: #F4A3A3;
    border: 1px solid #7A3B4E;
}}
QFrame#Sidebar QPushButton[variant="danger"]:hover {{
    background: #7A3B4E;
    color: #FFFFFF;
}}
QFrame#Card, QFrame#KpiCard {{
    background: {t["surface"]};
    border: 1px solid {t["border"]};
    border-radius: 12px;
}}
QLabel#PageTitle {{
    font-family: "Sora", "Inter", "Segoe UI";
    font-size: 16pt;
    font-weight: 600;
}}
QLabel#PageSubtitle, QLabel#Muted {{
    color: {t["muted"]};
}}
QLabel#KpiValue {{
    font-family: "Sora", "Inter", "Segoe UI";
    font-size: 22pt;
    font-weight: 600;
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
QFrame#OptionCard {{
    background: {t["surface"]};
    border: 1px solid {t["border"]};
    border-radius: 10px;
}}
QFrame#OptionCard:hover {{
    border-color: {t["border_strong"]};
}}
QFrame#OptionCard QRadioButton::indicator {{
    width: 14px;
    height: 14px;
    border-radius: 9px;
    border: 2px solid {t["border_strong"]};
    background: {t["surface"]};
}}
QFrame#OptionCard QRadioButton::indicator:checked {{
    width: 10px;
    height: 10px;
    border: 4px solid {t["accent"]};
    background: {t["surface"]};
}}
QFrame#OptionCard[selected="true"] {{
    background: {t["accent_soft"]};
    border: 1.5px solid {t["accent"]};
}}
QPushButton[variant="filter"] {{
    background: transparent;
    border: 1px solid {t["border"]};
    border-radius: 14px;
    padding: 4px 12px;
    color: {t["muted"]};
}}
QPushButton[variant="filter"]:hover {{
    background: {t["surface_hover"]};
    color: {t["text"]};
}}
QPushButton[variant="filter"]:checked {{
    background: {t["accent_soft"]};
    border-color: {t["accent"]};
    color: {t["text"]};
    font-weight: 600;
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
    border-color: {t["focus"]};
}}
QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled, QTextEdit:disabled {{
    background: {t["disabled_bg"]};
    color: {t["disabled_fg"]};
}}
QComboBox::drop-down {{
    border: none;
    width: 26px;
}}
QComboBox::down-arrow {{
    image: url("{icons}/chevron_down.svg");
    width: 12px;
    height: 12px;
}}
QSpinBox {{
    padding-right: 26px;
}}
QSpinBox::up-button, QSpinBox::down-button {{
    subcontrol-origin: border;
    width: 22px;
    border: none;
    border-left: 1px solid {t["border"]};
    background: transparent;
}}
QSpinBox::up-button {{
    subcontrol-position: top right;
    border-top-right-radius: 8px;
}}
QSpinBox::down-button {{
    subcontrol-position: bottom right;
    border-bottom-right-radius: 8px;
}}
QSpinBox::up-button:hover, QSpinBox::down-button:hover {{
    background: {t["surface_hover"]};
}}
QSpinBox::up-arrow {{
    image: url("{icons}/chevron_up.svg");
    width: 10px;
    height: 10px;
}}
QSpinBox::down-arrow {{
    image: url("{icons}/chevron_down.svg");
    width: 10px;
    height: 10px;
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
QTreeView::item {{
    min-height: 26px;
}}
QTableView::item {{
    padding: 2px 6px;
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
QLabel#CadastroInfo, QFrame#CadastroInfo {{
    background: {t["surface_alt"]};
    border: 1px solid {t["border"]};
    border-radius: 8px;
    padding: 10px 12px;
}}
QTabWidget::pane {{
    border: none;
    border-top: 1px solid {t["border_strong"]};
    top: -1px;
}}
QTabBar {{
    qproperty-drawBase: 0;
}}
QTabBar::tab {{
    background: {t["surface_alt"]};
    color: {t["text"]};
    padding: 7px 16px 6px 16px;
    margin-right: 4px;
    border: 1px solid {t["border"]};
    border-bottom: 3px solid {t["border_strong"]};
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    font-weight: 500;
}}
QTabBar::tab:hover:!selected {{
    background: {t["surface"]};
    border-color: {t["border_strong"]};
    border-bottom: 3px solid {t["accent_hover"]};
}}
QTabBar::tab:selected {{
    background: {t["accent_soft"]};
    color: {t["accent"]};
    border-color: {t["accent"]};
    border-bottom: 3px solid {t["accent"]};
    font-weight: 700;
}}
QTabBar::tab:disabled {{
    color: {t["muted"]};
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
        QPalette.ColorRole.HighlightedText: t["selection_text"],
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
        load_brand_fonts()
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
