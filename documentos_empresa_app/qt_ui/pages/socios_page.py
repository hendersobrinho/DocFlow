from __future__ import annotations

from datetime import date

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from documentos_empresa_app.qt_ui.theme import tokens
from documentos_empresa_app.qt_ui.widgets.acompanhamento import open_document, open_folder
from documentos_empresa_app.qt_ui.widgets.common import Card, PageHeader, ToolbarRow, make_button
from documentos_empresa_app.qt_ui.widgets.tables import fill_table, make_readonly_table, selected_key
from documentos_empresa_app.utils.common import ValidationError, format_utc_timestamp

TODAS = None


def _competencia_combo(services, com_todas: bool) -> QComboBox:
    combo = QComboBox()
    if com_todas:
        combo.addItem("Todas as competências", TODAS)
    periodos = sorted(services.periodo_service.list_periodos(), key=lambda p: (p["ano"], p["mes"]), reverse=True)
    for periodo in periodos:
        combo.addItem(f'{periodo["mes"]:02d}/{periodo["ano"]}', periodo["id"])
    return combo


class SociosPage(QWidget):
    """Lei 15.270/2025: a mesma empresa pagando mais de R$ 50 mil no mes ao mesmo socio pessoa
    fisica retem 10% de IR. O Claude le os extratos e anota os pagamentos; aqui as pessoas
    conferem os alertas, veem o que foi revisado e cadastram os socios."""

    def __init__(self, services, on_data_changed, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.services = services
        self.on_data_changed = on_data_changed
        self.alertas: dict[int, dict] = {}
        self.revisoes: dict[int, dict] = {}
        self.editing_socio_id: int | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        layout.addWidget(
            PageHeader(
                "Sócios (R$ 50 mil)",
                "Quando a mesma empresa paga mais de R$ 50.000,00 no mês ao mesmo sócio, retém 10% de IR "
                "sobre o total. O Claude revisa os extratos que chegaram e os casos aparecem aqui para conferir.",
            )
        )
        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_alertas_tab(), "Retiradas acima de R$ 50 mil")
        self.tabs.addTab(self._build_revisoes_tab(), "Extratos revisados")
        self.tabs.addTab(self._build_socios_tab(), "Sócios cadastrados")
        layout.addWidget(self.tabs, 1)

    # Aba 1: alertas ----------------------------------------------------------------------

    def _build_alertas_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(0, 8, 0, 0)
        toolbar = ToolbarRow()
        toolbar.add(QLabel("Competência"))
        self.alerta_periodo = toolbar.add(_competencia_combo(self.services, com_todas=True))
        toolbar.add(QLabel("Situação"))
        self.alerta_status = QComboBox()
        self.alerta_status.addItem("A resolver", "aberto")
        self.alerta_status.addItem("Resolvidos", "resolvido")
        self.alerta_status.addItem("Descartados", "descartado")
        self.alerta_status.addItem("Todas", None)
        toolbar.add(self.alerta_status)
        toolbar.add_stretch()
        for combo in (self.alerta_periodo, self.alerta_status):
            combo.currentIndexChanged.connect(self._refresh_alertas)
        layout.addWidget(toolbar)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.alerta_table = make_readonly_table(
            ["Mês", "Empresa", "Sócio", "Total no mês", "Retenção 10%", "Situação"], stretch_column=1
        )
        self.alerta_table.itemSelectionChanged.connect(self._show_alerta)
        splitter.addWidget(self.alerta_table)

        card = Card()
        detail = QVBoxLayout(card)
        detail.setContentsMargins(16, 14, 16, 12)
        self.alerta_info = QLabel("Clique num caso para ver os pagamentos.")
        self.alerta_info.setObjectName("Muted")
        self.alerta_info.setWordWrap(True)
        self.alerta_info.setTextFormat(Qt.TextFormat.RichText)
        detail.addWidget(self.alerta_info)
        self.pagamentos_table = make_readonly_table(["Data", "Valor", "Lançamento", "Extrato"], stretch_column=2)
        detail.addWidget(self.pagamentos_table, 1)
        arquivos = QHBoxLayout()
        abrir = make_button("Abrir extrato", "quiet")
        abrir.clicked.connect(self._abrir_extrato_pagamento)
        arquivos.addWidget(abrir)
        pasta = make_button("Abrir pasta", "quiet")
        pasta.clicked.connect(self._abrir_pasta_pagamento)
        arquivos.addWidget(pasta)
        arquivos.addStretch(1)
        detail.addLayout(arquivos)
        acoes = QHBoxLayout()
        acoes.addStretch(1)
        self.reabrir_button = make_button("Reabrir", "quiet")
        self.reabrir_button.clicked.connect(lambda: self._resolver("aberto"))
        acoes.addWidget(self.reabrir_button)
        self.descartar_button = make_button("Descartar", "quiet")
        self.descartar_button.setToolTip("Não é distribuição de lucro (ex: pró-labore, devolução de empréstimo).")
        self.descartar_button.clicked.connect(lambda: self._resolver("descartado"))
        acoes.addWidget(self.descartar_button)
        self.resolver_button = make_button("Marcar como resolvido", "primary")
        self.resolver_button.setToolTip("IR retido e recolhido, ou o caso já foi tratado.")
        self.resolver_button.clicked.connect(lambda: self._resolver("resolvido"))
        acoes.addWidget(self.resolver_button)
        detail.addLayout(acoes)
        splitter.addWidget(card)
        splitter.setSizes([720, 480])
        layout.addWidget(splitter, 1)
        self._set_alerta_buttons(None)
        return tab

    def _refresh_alertas(self) -> None:
        try:
            alertas = self.services.socios_service.listar_alertas(
                self.alerta_periodo.currentData(), self.alerta_status.currentData()
            )
        except ValidationError:
            return
        self.alertas = {a["id"]: a for a in alertas}
        t = tokens()
        cores = {"aberto": t["danger"], "resolvido": t["success"], "descartado": t["muted"]}
        rows, colors = [], {}
        for index, a in enumerate(alertas):
            rows.append(
                (
                    a["id"],
                    [
                        a["competencia"],
                        f'{a["codigo_empresa"]} - {a["nome_empresa"]}',
                        a["nome_socio"],
                        a["total"],
                        a["retencao_estimada"],
                        a["status_label"],
                    ],
                )
            )
            colors[(index, 5)] = cores.get(a["status"], t["muted"])
        self.alerta_table.blockSignals(True)
        fill_table(self.alerta_table, rows, colors)
        self.alerta_table.blockSignals(False)
        self._show_alerta()

    def _show_alerta(self) -> None:
        alerta_id = selected_key(self.alerta_table)
        if alerta_id is None:
            self.alerta_info.setText("Clique num caso para ver os pagamentos.")
            fill_table(self.pagamentos_table, [])
            self._set_alerta_buttons(None)
            return
        try:
            alerta = self.services.socios_service.obter_alerta(alerta_id)
        except ValidationError as exc:
            self.alerta_info.setText(str(exc))
            return
        self.alertas[alerta_id] = alerta
        linhas = [
            f'<b>{alerta["nome_socio"]}</b> ({alerta["cpf_formatado"]}) recebeu <b>{alerta["total"]}</b> de '
            f'{alerta["codigo_empresa"]} - {alerta["nome_empresa"]} em {alerta["competencia"]}.',
            f'Retenção estimada (10% sobre o total): <b>{alerta["retencao_estimada"]}</b>.',
        ]
        if alerta["status"] != "aberto":
            quem = alerta.get("resolvido_por_nome") or "-"
            quando = format_utc_timestamp(alerta.get("resolvido_em"))
            linhas.append(f'{alerta["status_label"]} por {quem} em {quando}.')
        if alerta.get("observacao"):
            linhas.append(f'Observação: {alerta["observacao"]}')
        self.alerta_info.setText("<br>".join(linhas))
        fill_table(
            self.pagamentos_table,
            [
                (index, [p.get("data") or "-", p["valor"], p.get("descricao") or "-", p.get("extrato") or "-"])
                for index, p in enumerate(alerta["pagamentos"])
            ],
        )
        self._set_alerta_buttons(alerta)

    def _set_alerta_buttons(self, alerta: dict | None) -> None:
        aberto = bool(alerta) and alerta["status"] == "aberto"
        self.resolver_button.setEnabled(aberto)
        self.descartar_button.setEnabled(aberto)
        self.reabrir_button.setEnabled(bool(alerta) and not aberto)

    def _pagamento_selecionado(self) -> tuple[dict | None, dict | None]:
        alerta = self.alertas.get(selected_key(self.alerta_table))
        if not alerta or not alerta.get("pagamentos"):
            return alerta, None
        index = selected_key(self.pagamentos_table)
        return alerta, alerta["pagamentos"][index if index is not None else 0]

    def _abrir_extrato_pagamento(self) -> None:
        _alerta, pagamento = self._pagamento_selecionado()
        open_document(self, (pagamento or {}).get("arquivo"))

    def _abrir_pasta_pagamento(self) -> None:
        alerta, pagamento = self._pagamento_selecionado()
        pasta = None
        if alerta:
            try:
                pasta = self.services.empresa_service.get_empresa(alerta["empresa_id"]).get("diretorio_documentos")
            except ValidationError:
                pasta = None
        open_folder(self, (pagamento or {}).get("arquivo"), pasta)

    def _resolver(self, status: str) -> None:
        alerta_id = selected_key(self.alerta_table)
        if alerta_id is None:
            return
        alerta = self.alertas.get(alerta_id, {})
        titulos = {"resolvido": "Marcar como resolvido", "descartado": "Descartar", "aberto": "Reabrir"}
        observacao, ok = QInputDialog.getMultiLineText(
            self,
            titulos[status],
            "Observação (ex: IR retido no DARF de abril; era pró-labore):",
            alerta.get("observacao") or "",
        )
        if not ok:
            return
        try:
            self.services.socios_service.resolver_alerta(alerta_id, status, observacao)
        except ValidationError as exc:
            QMessageBox.warning(self, "Sócios", str(exc))
            return
        self.on_data_changed()

    # Aba 2: extratos revisados -----------------------------------------------------------

    def _build_revisoes_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(0, 8, 0, 0)
        toolbar = ToolbarRow()
        toolbar.add(QLabel("Competência"))
        self.revisao_periodo = toolbar.add(_competencia_combo(self.services, com_todas=False))
        self.revisao_periodo.currentIndexChanged.connect(self._refresh_revisoes)
        toolbar.add_stretch()
        abrir = make_button("Abrir extrato", "quiet")
        abrir.clicked.connect(lambda: open_document(self, (self.revisoes.get(selected_key(self.revisao_table)) or {}).get("arquivo")))
        toolbar.add(abrir)
        layout.addWidget(toolbar)
        self.revisao_resumo = QLabel()
        self.revisao_resumo.setObjectName("Muted")
        self.revisao_resumo.setWordWrap(True)
        layout.addWidget(self.revisao_resumo)
        self.revisao_table = make_readonly_table(
            ["Empresa", "Extrato", "Resultado", "Pagamentos a sócios", "Total", "Revisado em", "Observação"],
            stretch_column=6,
        )
        layout.addWidget(self.revisao_table, 1)
        return tab

    def _refresh_revisoes(self) -> None:
        periodo_id = self.revisao_periodo.currentData()
        if periodo_id is None:
            self.revisao_resumo.setText("Nenhuma competência cadastrada.")
            fill_table(self.revisao_table, [])
            return
        try:
            fila = self.services.socios_service.extratos_para_revisar(periodo_id)
            revisoes = self.services.socios_service.listar_revisoes(periodo_id)
        except ValidationError:
            return
        partes = [
            f'{fila["extratos_revisados"]} extrato(s) revisado(s) e {fila["extratos_pendentes"]} esperando o Claude.'
        ]
        if fila["empresas_sem_socio_cadastrado"]:
            nomes = ", ".join(f'{e["codigo_empresa"]} - {e["nome_empresa"]}' for e in fila["empresas_sem_socio_cadastrado"][:8])
            extra = len(fila["empresas_sem_socio_cadastrado"]) - 8
            partes.append(
                "Sem sócio cadastrado (não dá para revisar): " + nomes + (f" e mais {extra}" if extra > 0 else "") + "."
            )
        self.revisao_resumo.setText(" ".join(partes))
        self.revisoes = {r["id"]: r for r in revisoes}
        t = tokens()
        rows, colors = [], {}
        for index, r in enumerate(revisoes):
            extrato = r.get("nome_documento") or (r.get("arquivo") or "-").replace("\\", "/").split("/")[-1]
            nao_deu = r["resultado"] == "nao_deu"
            rows.append(
                (
                    r["id"],
                    [
                        f'{r["codigo_empresa"]} - {r["nome_empresa"]}',
                        extrato,
                        "Não deu para ler" if nao_deu else "Revisado",
                        str(r["pagamentos"]),
                        r["total_formatado"] if r["pagamentos"] else "-",
                        format_utc_timestamp(r.get("revisado_em")),
                        r.get("resumo") or "",
                    ],
                )
            )
            if nao_deu:
                colors[(index, 2)] = t["warning"]
        fill_table(self.revisao_table, rows, colors)

    # Aba 3: cadastro dos socios ----------------------------------------------------------

    def _build_socios_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(0, 8, 0, 0)
        toolbar = ToolbarRow()
        self.socio_busca = QLineEdit()
        self.socio_busca.setPlaceholderText("Buscar por empresa, nome ou CPF")
        self.socio_busca.setClearButtonEnabled(True)
        self.socio_busca.textChanged.connect(self._refresh_socios)
        toolbar.add(self.socio_busca)
        toolbar.add_stretch()
        importar = make_button("Importar planilha", "quiet")
        importar.setToolTip("Planilha (.xlsx) ou CSV com as colunas Código da empresa, Nome e CPF.")
        importar.clicked.connect(self._importar)
        toolbar.add(importar)
        novo = make_button("Novo sócio", "primary")
        novo.clicked.connect(self._novo_socio)
        toolbar.add(novo)
        layout.addWidget(toolbar)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.socio_table = make_readonly_table(["Empresa", "Sócio", "CPF", "Situação"], stretch_column=0)
        self.socio_table.itemSelectionChanged.connect(self._editar_socio)
        splitter.addWidget(self.socio_table)

        card = Card()
        form_layout = QVBoxLayout(card)
        form_layout.setContentsMargins(20, 16, 20, 14)
        self.socio_form_title = QLabel("Novo sócio")
        self.socio_form_title.setStyleSheet("font-size: 13pt; font-weight: 600;")
        form_layout.addWidget(self.socio_form_title)
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self.socio_empresa = QComboBox()
        self.socio_empresa.setEditable(True)
        self.socio_empresa.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        form.addRow("Empresa", self.socio_empresa)
        self.socio_nome = QLineEdit()
        form.addRow("Nome", self.socio_nome)
        self.socio_cpf = QLineEdit()
        self.socio_cpf.setPlaceholderText("000.000.000-00")
        form.addRow("CPF", self.socio_cpf)
        self.socio_obs = QLineEdit()
        form.addRow("Observação", self.socio_obs)
        self.socio_ativo = QCheckBox("Ainda é sócio (ativo)")
        self.socio_ativo.setChecked(True)
        form.addRow("", self.socio_ativo)
        form_layout.addLayout(form)
        hint = QLabel("Só pessoas físicas. Quem saiu da sociedade: desmarque “ativo” para manter o histórico.")
        hint.setObjectName("Muted")
        hint.setWordWrap(True)
        form_layout.addWidget(hint)
        form_layout.addStretch(1)
        acoes = QHBoxLayout()
        self.socio_excluir = make_button("Excluir", "quiet")
        self.socio_excluir.clicked.connect(self._excluir_socio)
        acoes.addWidget(self.socio_excluir)
        acoes.addStretch(1)
        salvar = make_button("Salvar", "primary")
        salvar.clicked.connect(self._salvar_socio)
        acoes.addWidget(salvar)
        form_layout.addLayout(acoes)
        splitter.addWidget(card)
        splitter.setSizes([640, 460])
        layout.addWidget(splitter, 1)
        self._novo_socio()
        return tab

    def _refresh_empresas(self) -> None:
        atual = self.socio_empresa.currentData()
        self.socio_empresa.blockSignals(True)
        self.socio_empresa.clear()
        for empresa in self.services.empresa_service.list_empresas():
            self.socio_empresa.addItem(f'{empresa["codigo_empresa"]} - {empresa["nome_empresa"]}', empresa["id"])
        if atual is not None:
            self.socio_empresa.setCurrentIndex(max(0, self.socio_empresa.findData(atual)))
        self.socio_empresa.blockSignals(False)

    def _refresh_socios(self) -> None:
        try:
            socios = self.services.socios_service.listar_socios()
        except ValidationError:
            return
        busca = self.socio_busca.text().strip().lower()
        digitos = "".join(c for c in busca if c.isdigit())
        muted = tokens()["muted"]
        rows, colors = [], {}
        for s in socios:
            empresa = f'{s["codigo_empresa"]} - {s["nome_empresa"]}'
            if busca and busca not in f'{empresa} {s["nome"]}'.lower() and not (digitos and digitos in s["cpf"]):
                continue
            index = len(rows)
            rows.append((s["id"], [empresa, s["nome"], s["cpf_formatado"], "Ativo" if s["ativo"] else "Saiu"]))
            if not s["ativo"]:
                for column in range(4):
                    colors[(index, column)] = muted
        self.socio_table.blockSignals(True)
        fill_table(self.socio_table, rows, colors)
        self.socio_table.blockSignals(False)

    def _novo_socio(self) -> None:
        self.editing_socio_id = None
        self.socio_table.clearSelection()
        self.socio_form_title.setText("Novo sócio")
        self.socio_empresa.setEnabled(True)
        for campo in (self.socio_nome, self.socio_cpf, self.socio_obs):
            campo.clear()
        self.socio_ativo.setChecked(True)
        self.socio_excluir.setEnabled(False)

    def _editar_socio(self) -> None:
        socio_id = selected_key(self.socio_table)
        if socio_id is None:
            return
        try:
            socio = self.services.socios_service.obter_socio(socio_id)
        except ValidationError:
            return
        self.editing_socio_id = socio_id
        self.socio_form_title.setText(socio["nome"])
        self.socio_empresa.setCurrentIndex(max(0, self.socio_empresa.findData(socio["empresa_id"])))
        self.socio_empresa.setEnabled(False)  # para mudar de empresa, cadastre na outra
        self.socio_nome.setText(socio["nome"])
        self.socio_cpf.setText(socio["cpf_formatado"])
        self.socio_obs.setText(socio.get("observacao") or "")
        self.socio_ativo.setChecked(bool(socio["ativo"]))
        self.socio_excluir.setEnabled(True)

    def _salvar_socio(self) -> None:
        service = self.services.socios_service
        try:
            if self.editing_socio_id is None:
                indice = self.socio_empresa.findText(self.socio_empresa.currentText())
                if indice < 0:
                    raise ValidationError("Escolha a empresa na lista.")
                service.cadastrar_socio(
                    self.socio_empresa.itemData(indice), self.socio_nome.text(), self.socio_cpf.text(), self.socio_obs.text()
                )
            else:
                service.atualizar_socio(
                    self.editing_socio_id, self.socio_nome.text(), self.socio_cpf.text(),
                    self.socio_ativo.isChecked(), self.socio_obs.text(),
                )
        except ValidationError as exc:
            QMessageBox.warning(self, "Sócios", str(exc))
            return
        self._novo_socio()
        self.on_data_changed()

    def _excluir_socio(self) -> None:
        if self.editing_socio_id is None:
            return
        resposta = QMessageBox.question(
            self,
            "Excluir sócio",
            "Excluir o sócio e os pagamentos achados para ele nos extratos?\n\n"
            "Se ele só saiu da sociedade, prefira desmarcar “ativo” para manter o histórico.",
        )
        if resposta != QMessageBox.StandardButton.Yes:
            return
        try:
            self.services.socios_service.excluir_socio(self.editing_socio_id)
        except ValidationError as exc:
            QMessageBox.warning(self, "Sócios", str(exc))
            return
        self._novo_socio()
        self.on_data_changed()

    def _importar(self) -> None:
        caminho, _filtro = QFileDialog.getOpenFileName(
            self, "Importar sócios", "", "Planilha (*.xlsx *.csv);;Todos os arquivos (*.*)"
        )
        if not caminho:
            return
        try:
            resultado = self.services.socios_service.importar_planilha(caminho)
        except ValidationError as exc:
            QMessageBox.warning(self, "Importar sócios", str(exc))
            return
        texto = f'{resultado["criados"]} sócio(s) novo(s) e {resultado["atualizados"]} atualizado(s).'
        if resultado["erros"]:
            texto += f'\n\n{len(resultado["erros"])} linha(s) com problema:\n' + "\n".join(resultado["erros"][:15])
            if len(resultado["erros"]) > 15:
                texto += f'\n... e mais {len(resultado["erros"]) - 15}.'
        QMessageBox.information(self, "Importar sócios", texto)
        self.on_data_changed()

    # Atualizacao -------------------------------------------------------------------------

    def refresh_data(self) -> None:
        for combo, com_todas in ((self.alerta_periodo, True), (self.revisao_periodo, False)):
            atual = combo.currentData()
            combo.blockSignals(True)
            combo.clear()
            novo = _competencia_combo(self.services, com_todas)
            for i in range(novo.count()):
                combo.addItem(novo.itemText(i), novo.itemData(i))
            novo.deleteLater()
            if atual is None and not com_todas:
                hoje = date.today()  # comeca no mes de agora, nao na ultima competencia gerada
                atual = next((p["id"] for p in self.services.periodo_service.list_periodos()
                              if (p["ano"], p["mes"]) == (hoje.year, hoje.month)), None)
            if atual is not None:
                combo.setCurrentIndex(max(0, combo.findData(atual)))
            combo.blockSignals(False)
        self._refresh_empresas()
        self._refresh_alertas()
        self._refresh_revisoes()
        self._refresh_socios()
