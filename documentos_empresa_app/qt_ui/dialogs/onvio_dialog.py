"""Janela do robo do Onvio: escolhe a competencia e baixa os documentos de todas as empresas
(Contabilidade > AAAA > MM-AAAA) para uma pasta do computador. O robo roda numa thread
separada; a tela so mostra o andamento."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QThread, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QProgressBar,
    QRadioButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from documentos_empresa_app.onvio.api import OnvioError
from documentos_empresa_app.onvio.robo import BAIXADA, ERRO, ROTULOS, Resumo, competencias_entre, pasta_padrao
from documentos_empresa_app.qt_ui.dialogs.company_dialogs import CompanyMultiSelectDialog
from documentos_empresa_app.qt_ui.widgets.common import make_button
from documentos_empresa_app.utils.common import MONTH_NAMES
from documentos_empresa_app.utils.helpers import load_ui_state, save_ui_state


class _Robo(QObject):
    progresso = Signal(int, int, str)
    aviso = Signal(str)
    terminou = Signal(object)
    falhou = Signal(str)

    def __init__(self, trabalhos: list[tuple[int, int, list[tuple[str, str]]]], destino: Path, de_novo: bool) -> None:
        """trabalhos: [(ano, mes, empresas)] - uma competencia ou varias, uma depois da outra."""
        super().__init__()
        self.trabalhos, self.destino, self.de_novo = trabalhos, destino, de_novo
        self.parar = False

    def rodar(self) -> None:
        from documentos_empresa_app.onvio.navegador import sessao_onvio
        from documentos_empresa_app.onvio.robo import baixar_competencias

        try:
            with sessao_onvio(avisar=self.aviso.emit, cancelado=lambda: self.parar) as api:
                resumos = baixar_competencias(
                    api, self.trabalhos, self.destino, self.de_novo,
                    on_progress=lambda f, t, r, m: self.progresso.emit(f, t, m),
                    cancelado=lambda: self.parar,
                )
        except OnvioError as exc:
            self.falhou.emit(str(exc))
            return
        except Exception as exc:  # noqa: BLE001 - qualquer falha do navegador vira mensagem
            self.falhou.emit(f"Falha no robô: {exc}")
            return
        self.terminou.emit(resumos)


class OnvioDownloadDialog(QDialog):
    def __init__(self, services, competencia: tuple[int, int] | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.services = services
        self._thread: QThread | None = None
        self._robo: _Robo | None = None
        self.resumo: Resumo | None = None  # o da ultima competencia baixada
        self.resumos: list[Resumo] = []
        self.manual_ids: list[int] = []
        self.setWindowTitle("Baixar documentos do Onvio")
        self.setMinimumSize(620, 520)

        layout = QVBoxLayout(self)
        intro = QLabel(
            "O robô entra no Onvio e, de cada empresa, baixa tudo da pasta <b>Contabilidade › ano › "
            "MM-AAAA</b>, com as subpastas, para uma pasta deste computador. Na primeira vez abre uma "
            "janela para você entrar no Onvio; depois ele lembra o login."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        form = QFormLayout()
        hoje = date.today()
        ano, mes = competencia or ((hoje.year - 1, 12) if hoje.month == 1 else (hoje.year, hoje.month - 1))
        linha = QHBoxLayout()
        self.mes_combo = QComboBox()
        for numero in range(1, 13):
            self.mes_combo.addItem(f"{numero:02d} - {MONTH_NAMES[numero]}", numero)
        self.mes_combo.setCurrentIndex(mes - 1)
        linha.addWidget(self.mes_combo)
        self.ano_spin = QSpinBox()
        self.ano_spin.setRange(2000, 2100)
        self.ano_spin.setValue(ano)
        linha.addWidget(self.ano_spin)
        linha.addStretch(1)
        form.addRow("Competência", linha)
        ate = QHBoxLayout()
        self.varias_check = QCheckBox("Várias competências, até")
        self.varias_check.setToolTip(
            "Opcional: baixa também os meses seguintes até a competência escolhida (ex: 01 a 08), "
            "cada um na sua pasta MM-AAAA."
        )
        ate.addWidget(self.varias_check)
        self.ate_mes_combo = QComboBox()
        for numero in range(1, 13):
            self.ate_mes_combo.addItem(f"{numero:02d} - {MONTH_NAMES[numero]}", numero)
        self.ate_mes_combo.setCurrentIndex(mes - 1)
        ate.addWidget(self.ate_mes_combo)
        self.ate_ano_spin = QSpinBox()
        self.ate_ano_spin.setRange(2000, 2100)
        self.ate_ano_spin.setValue(ano)
        ate.addWidget(self.ate_ano_spin)
        ate.addStretch(1)
        form.addRow("", ate)
        self.varias_check.toggled.connect(self._atualizar_intervalo)
        self._atualizar_intervalo()

        pasta = QHBoxLayout()
        self.destino_edit = QLineEdit(str(load_ui_state("onvio:destino", "") or pasta_padrao()))
        pasta.addWidget(self.destino_edit, 1)
        escolher = make_button("Escolher...", "quiet")
        escolher.clicked.connect(self._escolher_pasta)
        pasta.addWidget(escolher)
        form.addRow("Salvar em", pasta)
        self.escopo_filtros = QRadioButton("Empresas pelos filtros abaixo")
        self.escopo_filtros.setChecked(True)
        form.addRow("Empresas", self.escopo_filtros)
        escolha = QHBoxLayout()
        self.escopo_manual = QRadioButton("Escolher empresas")
        escolha.addWidget(self.escopo_manual)
        self.escolher_empresas_button = make_button("Escolher...", "quiet")
        self.escolher_empresas_button.clicked.connect(self._escolher_empresas)
        escolha.addWidget(self.escolher_empresas_button)
        self.manual_label = QLabel("")
        self.manual_label.setObjectName("Muted")
        escolha.addWidget(self.manual_label)
        escolha.addStretch(1)
        form.addRow("", escolha)
        self.ativas_check = QCheckBox("Só empresas ativas no DocFlow")
        self.ativas_check.setChecked(True)
        form.addRow("", self.ativas_check)
        self.so_onvio_check = QCheckBox("Só empresas que recebem documentos pelo Onvio (marcado nos documentos)")
        self.so_onvio_check.setChecked(bool(load_ui_state("onvio:so_onvio", True)))
        form.addRow("", self.so_onvio_check)
        self.so_pendentes_check = QCheckBox("Só quem ainda tem documento pendente no DocFlow nessa competência")
        self.so_pendentes_check.setChecked(bool(load_ui_state("onvio:so_pendentes", True)))
        self.so_pendentes_check.setToolTip(
            "Quem já está com tudo recebido (ou encerrado) fica de fora. Vale para os documentos "
            "marcados com Onvio. Se a competência não existe no DocFlow, este filtro é ignorado."
        )
        form.addRow("", self.so_pendentes_check)
        self.de_novo_check = QCheckBox("Baixar tudo de novo (não só o que chegou depois)")
        form.addRow("", self.de_novo_check)
        layout.addLayout(form)

        self.situacao_label = QLabel("")
        self.situacao_label.setWordWrap(True)
        layout.addWidget(self.situacao_label)
        self.barra = QProgressBar()
        self.barra.setVisible(False)
        layout.addWidget(self.barra)
        self.lista = QListWidget()
        layout.addWidget(self.lista, 1)

        botoes = QHBoxLayout()
        self.abrir_button = make_button("Abrir pasta", "quiet")
        self.abrir_button.clicked.connect(self._abrir_pasta)
        botoes.addWidget(self.abrir_button)
        self.repetir_button = make_button("Repetir só as que deram erro", "quiet")
        self.repetir_button.setVisible(False)
        self.repetir_button.clicked.connect(self._repetir_com_erro)
        botoes.addWidget(self.repetir_button)
        botoes.addStretch(1)
        self.fechar_button = make_button("Fechar", "quiet")
        self.fechar_button.clicked.connect(self.close)
        botoes.addWidget(self.fechar_button)
        self.iniciar_button = make_button("Baixar", "primary")
        self.iniciar_button.clicked.connect(self.iniciar)
        botoes.addWidget(self.iniciar_button)
        layout.addLayout(botoes)

    # ----------------------------------------------------------------------------------

    def _escolher_pasta(self) -> None:
        pasta = QFileDialog.getExistingDirectory(self, "Salvar os documentos em", self.destino_edit.text())
        if pasta:
            self.destino_edit.setText(pasta)

    def _atualizar_intervalo(self) -> None:
        ligado = self.varias_check.isEnabled() and self.varias_check.isChecked()
        self.ate_mes_combo.setEnabled(ligado)
        self.ate_ano_spin.setEnabled(ligado)

    def competencias(self) -> list[tuple[int, int]]:
        """[(ano, mes)] a baixar: so a competencia escolhida ou, com Varias, ate a final."""
        inicio = (self.ano_spin.value(), self.mes_combo.currentData())
        if not self.varias_check.isChecked():
            return [inicio]
        return competencias_entre(inicio, (self.ate_ano_spin.value(), self.ate_mes_combo.currentData()))

    def _pasta_competencia(self) -> Path:
        return Path(self.destino_edit.text()) / f"{self.mes_combo.currentData():02d}-{self.ano_spin.value()}"

    def _abrir_pasta(self) -> None:
        pasta = Path(self.resumo.pasta) if self.resumo else self._pasta_competencia()
        if not pasta.exists():
            pasta = Path(self.destino_edit.text())
        pasta.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(pasta)))

    def _todas_empresas(self) -> list[dict]:
        return self.services.empresa_service.list_empresas(active_only=False)

    def _escolher_empresas(self) -> None:
        dialogo = CompanyMultiSelectDialog(self, self._todas_empresas(), self.manual_ids)
        if dialogo.exec():
            self.manual_ids = list(dialogo.selected_company_ids)
            self._atualizar_escolha()
            self.escopo_manual.setChecked(bool(self.manual_ids))

    def _atualizar_escolha(self) -> None:
        self.manual_label.setText(f"{len(self.manual_ids)} selecionada(s)" if self.manual_ids else "")

    def _repetir_com_erro(self) -> None:
        if not self.resumo:
            return
        codigos = {e.codigo for r in (self.resumos or [self.resumo]) for e in r.empresas if e.situacao == ERRO}
        self.manual_ids = [int(e["id"]) for e in self._todas_empresas() if str(e["codigo_empresa"]) in codigos]
        self._atualizar_escolha()
        self.escopo_manual.setChecked(True)
        self.iniciar()

    def empresas(self, competencia: tuple[int, int] | None = None) -> list[tuple[str, str]]:
        """Empresas a baixar na competencia (ano, mes); sem ela, a competencia escolhida. O filtro
        de pendentes muda de um mes para outro."""
        servico = self.services.empresa_service
        competencia = competencia or (self.ano_spin.value(), self.mes_combo.currentData())
        if self.escopo_manual.isChecked():
            escolhidas = set(self.manual_ids)
            lista = [e for e in self._todas_empresas() if int(e["id"]) in escolhidas]
        elif self.so_onvio_check.isChecked():
            pendentes_em = competencia if self.so_pendentes_check.isChecked() else None
            lista = servico.list_empresas_com_meio("onvio", active_only=self.ativas_check.isChecked(), pendentes_em=pendentes_em)
        else:
            lista = servico.list_empresas(active_only=self.ativas_check.isChecked())
        return [(str(e["codigo_empresa"]), e["nome_empresa"]) for e in lista]

    def iniciar(self) -> None:
        if self._thread:
            self._robo.parar = True
            self.iniciar_button.setEnabled(False)
            self.situacao_label.setText("Parando depois da empresa atual...")
            return
        destino = Path(self.destino_edit.text().strip() or pasta_padrao())
        try:
            destino.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            QMessageBox.critical(self, "Onvio", f"Não foi possível usar a pasta:\n{exc}")
            return
        save_ui_state("onvio:destino", str(destino))
        save_ui_state("onvio:so_onvio", self.so_onvio_check.isChecked())
        save_ui_state("onvio:so_pendentes", self.so_pendentes_check.isChecked())
        try:
            meses = self.competencias()
        except ValueError as exc:
            QMessageBox.information(self, "Onvio", str(exc))
            return
        trabalhos = [(ano, mes, self.empresas((ano, mes))) for ano, mes in meses]
        trabalhos = [t for t in trabalhos if t[2]]
        empresas = [e for t in trabalhos for e in t[2]]
        if not empresas:
            aviso = "Nenhuma empresa cadastrada."
            if self.escopo_manual.isChecked():
                aviso = "Escolha pelo menos uma empresa."
            elif self.so_onvio_check.isChecked():
                aviso = "Nenhuma empresa para baixar: todas com Onvio já estão sem documento pendente nessa competência (ou nenhuma tem Onvio marcado no cadastro)."
            QMessageBox.information(self, "Onvio", aviso)
            return
        self.lista.clear()
        self.resumo = None
        self.resumos = []
        self.barra.setVisible(True)
        self.barra.setRange(0, len(empresas))
        self.barra.setValue(0)
        self.repetir_button.setVisible(False)
        self.situacao_label.setText("Abrindo o Onvio...")
        self.iniciar_button.setText("Parar")
        for widget in (self.mes_combo, self.ano_spin, self.destino_edit, self.escopo_filtros, self.escopo_manual, self.escolher_empresas_button, self.ativas_check, self.so_onvio_check, self.so_pendentes_check, self.de_novo_check, self.varias_check, self.ate_mes_combo, self.ate_ano_spin):
            widget.setEnabled(False)

        self._thread = QThread(self)
        self._robo = _Robo(trabalhos, destino, self.de_novo_check.isChecked())
        self._robo.moveToThread(self._thread)
        self._thread.started.connect(self._robo.rodar)
        self._robo.progresso.connect(self._andamento, Qt.ConnectionType.QueuedConnection)
        self._robo.aviso.connect(self.situacao_label.setText, Qt.ConnectionType.QueuedConnection)
        self._robo.terminou.connect(self._terminou, Qt.ConnectionType.QueuedConnection)
        self._robo.falhou.connect(self._falhou, Qt.ConnectionType.QueuedConnection)
        self._thread.start()

    def _andamento(self, feitas: int, total: int, mensagem: str) -> None:
        self.barra.setMaximum(max(total, 1))
        self.barra.setValue(feitas)
        if ":" in mensagem:  # resultado de uma empresa
            self.lista.addItem(mensagem)
            self.lista.scrollToBottom()
        else:
            self.situacao_label.setText(f"{feitas + 1 if feitas < total else feitas} de {total}: {mensagem}")

    def _encerrar_thread(self) -> None:
        if self._thread:
            self._thread.quit()
            self._thread.wait(5000)
        self._thread = None
        self._robo = None
        self.iniciar_button.setText("Baixar")
        self.iniciar_button.setEnabled(True)
        for widget in (self.mes_combo, self.ano_spin, self.destino_edit, self.escopo_filtros, self.escopo_manual, self.escolher_empresas_button, self.ativas_check, self.so_onvio_check, self.so_pendentes_check, self.de_novo_check, self.varias_check, self.ate_mes_combo, self.ate_ano_spin):
            widget.setEnabled(True)
        self._atualizar_intervalo()

    def _terminou(self, resumos: list[Resumo]) -> None:
        self._encerrar_thread()
        self.resumos = list(resumos)
        self.resumo = self.resumos[-1] if self.resumos else None
        self.barra.setValue(self.barra.maximum())
        self.situacao_label.setText("\n".join(r.texto() for r in self.resumos) or "Nada foi baixado.")
        problemas = [(r, e) for r in self.resumos for e in r.empresas if e.situacao == ERRO]
        self.repetir_button.setVisible(bool(problemas))
        if problemas:
            self.lista.addItem("")
            self.lista.addItem("Com erro (tente de novo):")
            varias = len(self.resumos) > 1
            for resumo, empresa in problemas:
                quando = f"{resumo.competencia} · " if varias else ""
                self.lista.addItem(f"  {quando}{empresa.codigo} - {empresa.nome}: {empresa.detalhe}")
        pastas = [r.pasta for r in self.resumos if any(e.situacao == BAIXADA for e in r.empresas)]
        if pastas:
            self.lista.addItem("")
            for pasta in pastas:
                self.lista.addItem(f"Arquivos em {pasta} (a lista de tudo está em _resumo.json).")

    def _falhou(self, mensagem: str) -> None:
        self._encerrar_thread()
        self.situacao_label.setText(mensagem)
        QMessageBox.warning(self, "Onvio", mensagem)

    def closeEvent(self, event) -> None:  # noqa: N802 - API do Qt
        if self._thread:
            if QMessageBox.question(self, "Onvio", "O robô ainda está baixando. Parar e fechar?") != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            self._robo.parar = True
            self._thread.quit()
            self._thread.wait(15000)
        super().closeEvent(event)


__all__ = ["OnvioDownloadDialog", "ROTULOS"]
