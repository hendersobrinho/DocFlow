from __future__ import annotations

from PySide6.QtCharts import (
    QBarCategoryAxis,
    QBarSeries,
    QBarSet,
    QChart,
    QChartView,
    QPieSeries,
    QValueAxis,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from documentos_empresa_app.qt_ui.theme import ThemeManager, situation_color, tokens
from documentos_empresa_app.qt_ui.viewmodels import (
    MONTH_STATUS_OVERDUE,
    PanoramaViewModel,
    UI_SITUATION_LABELS,
)
from documentos_empresa_app.qt_ui.widgets.common import Card, KpiCard, PageHeader, ToolbarRow, make_button
from documentos_empresa_app.services.panorama_service import PanoramaService

TREND_PERIODS = 6


class DashboardPage(QWidget):
    """Visao executiva: KPIs e graficos do periodo selecionado."""

    def __init__(self, services, on_data_changed, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.services = services
        self.on_data_changed = on_data_changed
        self.viewmodel = PanoramaViewModel(services)
        self.periods: list[dict] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        layout.addWidget(PageHeader("Dashboard", "Resumo executivo da competencia selecionada."))

        toolbar = ToolbarRow()
        toolbar.add(QLabel("Competencia"))
        self.period_combo = QComboBox()
        self.period_combo.setMinimumWidth(150)
        self.period_combo.currentIndexChanged.connect(lambda _i: self.reload())
        toolbar.add(self.period_combo)
        self.active_only_check = QCheckBox("Somente empresas ativas")
        self.active_only_check.setChecked(True)
        self.active_only_check.toggled.connect(lambda _c: self.reload())
        toolbar.add(self.active_only_check)
        refresh_button = make_button("Atualizar")
        refresh_button.clicked.connect(self.refresh_data)
        toolbar.add(refresh_button)
        toolbar.add_stretch()
        layout.addWidget(toolbar)

        kpi_row = QHBoxLayout()
        kpi_row.setSpacing(12)
        t = tokens()
        self.kpi_cards: dict[str, KpiCard] = {}
        for key, label, color in (
            ("total", "Empresas no periodo", None),
            ("concluida", "Concluidas", t["success"]),
            ("andamento", "Em andamento", t["accent"]),
            ("prazo", "Dentro do prazo", t["warning"]),
            ("pendencia", "Com pendencia", t["danger"]),
            ("atraso", "Em atraso", t["danger"]),
        ):
            card = KpiCard(label, color)
            self.kpi_cards[key] = card
            kpi_row.addWidget(card, 1)
        layout.addLayout(kpi_row)

        charts_row = QHBoxLayout()
        charts_row.setSpacing(14)
        layout.addLayout(charts_row, 1)

        donut_card = Card()
        donut_layout = QVBoxLayout(donut_card)
        donut_layout.setContentsMargins(14, 12, 14, 12)
        donut_title = QLabel("Distribuicao por situacao")
        donut_title.setStyleSheet("font-weight: 600;")
        donut_layout.addWidget(donut_title)
        self.donut_view = QChartView()
        self.donut_view.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.donut_view.setStyleSheet("background: transparent; border: none;")
        donut_layout.addWidget(self.donut_view, 1)
        charts_row.addWidget(donut_card, 1)

        trend_card = Card()
        trend_layout = QVBoxLayout(trend_card)
        trend_layout.setContentsMargins(14, 12, 14, 12)
        trend_title = QLabel(f"Conclusao das ultimas {TREND_PERIODS} competencias (%)")
        trend_title.setStyleSheet("font-weight: 600;")
        trend_layout.addWidget(trend_title)
        self.trend_view = QChartView()
        self.trend_view.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.trend_view.setStyleSheet("background: transparent; border: none;")
        trend_layout.addWidget(self.trend_view, 1)
        charts_row.addWidget(trend_card, 1)

        self.footer_label = QLabel("")
        self.footer_label.setObjectName("Muted")
        layout.addWidget(self.footer_label)

        self._trend_cache: dict[tuple, tuple[list[str], list[float]]] = {}

        # Conexao com metodo bound: o Qt desconecta automaticamente quando a
        # pagina e destruida (lambda ficaria conectada a um widget morto).
        ThemeManager.instance().theme_changed.connect(self._on_theme_changed)

    def _on_theme_changed(self, _mode: str) -> None:
        self.reload()

    def refresh_data(self) -> None:
        self._trend_cache.clear()
        self._refresh_periods()
        self.reload()

    def _refresh_periods(self) -> None:
        selected = self.period_combo.currentData()
        self.periods = self.services.periodo_service.list_periodos()
        self.period_combo.blockSignals(True)
        self.period_combo.clear()
        for periodo in sorted(self.periods, key=lambda p: (p["ano"], p["mes"])):
            self.period_combo.addItem(f'{periodo["mes"]:02d}/{periodo["ano"]}', periodo["id"])
        if selected is not None:
            index = self.period_combo.findData(selected)
            if index >= 0:
                self.period_combo.setCurrentIndex(index)
            else:
                self.period_combo.setCurrentIndex(self.period_combo.count() - 1)
        else:
            from datetime import datetime

            now = datetime.now()
            current = next((p for p in self.periods if p["ano"] == now.year and p["mes"] == now.month), None)
            if current:
                self.period_combo.setCurrentIndex(self.period_combo.findData(current["id"]))
            elif self.period_combo.count():
                self.period_combo.setCurrentIndex(self.period_combo.count() - 1)
        self.period_combo.blockSignals(False)

    def reload(self) -> None:
        period_id = self.period_combo.currentData()
        if period_id is None:
            for card in self.kpi_cards.values():
                card.set_value("-")
            self._swap_chart(self.donut_view, self._base_chart())
            self._swap_chart(self.trend_view, self._base_chart())
            self.footer_label.setText("Cadastre periodos para carregar o dashboard.")
            return

        active_only = self.active_only_check.isChecked()
        self.viewmodel.load(period_id, active_only)
        counts = self.viewmodel.count_month_statuses()
        total = len(self.viewmodel.rows)

        self.kpi_cards["total"].set_value(str(total))
        self.kpi_cards["concluida"].set_value(str(counts.get(PanoramaService.SITUATION_CONCLUIDA, 0)))
        self.kpi_cards["andamento"].set_value(str(counts.get(PanoramaService.SITUATION_EM_ANDAMENTO, 0)))
        self.kpi_cards["prazo"].set_value(str(counts.get(PanoramaService.SITUATION_NAO_INICIADA, 0)))
        self.kpi_cards["pendencia"].set_value(str(counts.get(PanoramaService.SITUATION_COM_PENDENCIA, 0)))
        self.kpi_cards["atraso"].set_value(str(counts.get(MONTH_STATUS_OVERDUE, 0)))

        self._render_donut(counts, total)
        self._render_trend(period_id, active_only)

        scope = "somente empresas ativas" if active_only else "empresas ativas e inativas"
        self.footer_label.setText(
            f"Resumo de {self.period_combo.currentText()} considerando {scope}."
        )

    def _base_chart(self) -> QChart:
        t = tokens()
        chart = QChart()
        chart.setBackgroundBrush(QColor(t["surface"]))
        chart.setBackgroundRoundness(0)
        chart.legend().setLabelColor(QColor(t["text"]))
        return chart

    @staticmethod
    def _swap_chart(view: QChartView, chart: QChart) -> None:
        old_chart = view.chart()
        view.setChart(chart)
        if old_chart is not None:
            old_chart.deleteLater()

    def _render_donut(self, counts: dict[str, int], total: int) -> None:
        t = tokens()
        chart = self._base_chart()

        series = QPieSeries()
        series.setHoleSize(0.45)
        for key, label in UI_SITUATION_LABELS.items():
            value = counts.get(key, 0)
            if value <= 0:
                continue
            pie_slice = series.append(f"{label} ({value})", value)
            pie_slice.setBrush(QColor(situation_color(key)))
            pie_slice.setLabelColor(QColor(t["text"]))
            pie_slice.setBorderColor(QColor(t["surface"]))

        if not series.slices():
            series.append("Sem dados", 1).setBrush(QColor(t["border"]))

        series.setLabelsVisible(False)
        chart.addSeries(series)
        chart.legend().setAlignment(Qt.AlignmentFlag.AlignRight)
        self._swap_chart(self.donut_view, chart)

    def _render_trend(self, selected_period_id: int, active_only: bool) -> None:
        t = tokens()
        ordered = sorted(self.periods, key=lambda p: (p["ano"], p["mes"]))
        selected_index = next(
            (i for i, p in enumerate(ordered) if p["id"] == selected_period_id), len(ordered) - 1
        )
        window = ordered[max(0, selected_index - TREND_PERIODS + 1): selected_index + 1]

        categories: list[str] = []
        values: list[float] = []
        for periodo in window:
            cache_key = (periodo["id"], active_only)
            cached = self._trend_cache.get(cache_key)
            if cached is None:
                view = self.services.panorama_service.build_monthly_view(periodo["id"], active_only=active_only)
                rows = view["rows"]
                chargeable = sum(row["total_cobravel"] for row in rows)
                marked = sum(row["marcados"] for row in rows)
                percent = round((marked / chargeable * 100) if chargeable else 0.0, 1)
                cached = (f'{periodo["mes"]:02d}/{periodo["ano"] % 100:02d}', percent)
                self._trend_cache[cache_key] = cached
            categories.append(cached[0])
            values.append(cached[1])

        chart = self._base_chart()
        bar_set = QBarSet("Conclusao %")
        bar_set.setColor(QColor(t["accent"]))
        for value in values:
            bar_set.append(value)
        series = QBarSeries()
        series.append(bar_set)
        series.setLabelsVisible(True)
        series.setLabelsFormat("@value%")
        chart.addSeries(series)

        axis_x = QBarCategoryAxis()
        axis_x.append(categories or ["-"])
        axis_x.setLabelsColor(QColor(t["muted"]))
        axis_x.setGridLineColor(QColor(t["chart_grid"]))
        chart.addAxis(axis_x, Qt.AlignmentFlag.AlignBottom)
        series.attachAxis(axis_x)

        axis_y = QValueAxis()
        axis_y.setRange(0, 100)
        axis_y.setLabelsColor(QColor(t["muted"]))
        axis_y.setGridLineColor(QColor(t["chart_grid"]))
        chart.addAxis(axis_y, Qt.AlignmentFlag.AlignLeft)
        series.attachAxis(axis_y)

        chart.legend().setVisible(False)
        label_font = QFont()
        label_font.setPointSize(8)
        series.setLabelsPosition(QBarSeries.LabelsPosition.LabelsOutsideEnd)
        bar_set.setLabelFont(label_font)
        bar_set.setLabelColor(QColor(t["text"]))
        self._swap_chart(self.trend_view, chart)
