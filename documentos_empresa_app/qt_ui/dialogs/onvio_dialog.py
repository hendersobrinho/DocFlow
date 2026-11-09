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
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from documentos_empresa_app.onvio.api import OnvioError
from documentos_empresa_app.onvio.robo import BAIXADA, ERRO, ROTULOS, Resumo, pasta_padrao
from documentos_empresa_app.qt_ui.widgets.common import make_button
from documentos_empresa_app.utils.common import MONTH_NAMES
from documentos_empresa_app.utils.helpers import load_ui_state, save_ui_state


class _Robo(QObject):
    progresso = Signal(int, int, str)
    aviso = Signal(str)
    terminou = Signal(object)
    falhou = Signal(str)

    def __init__(self, ano: int, mes: int, empresas: list[tuple[str, str]], destino: Path, de_novo: bool) -> None:
        super().__init__()
        self.ano, self.mes, self.empresas, self.destino, self.de_novo = ano, mes, empresas, destino, de_novo
        self.parar = False

    def rodar(self) -> None:
        from documentos_empresa_app.onvio.navegador import sessao_onvio
        from documentos_empresa_app.onvio.robo import baixar_competencia

        try:
            with sessao_onvio(avisar=self.aviso.emit, cancelado=lambda: self.parar) as api:
                resumo = baixar_competencia(
                    api, self.ano, self.mes, self.empresas, self.destino, self.de_novo,
                    on_progress=lambda f, t, r, m: self.progresso.emit(f, t, m),
                    cancelado=lambda: self.parar,
                )
        except OnvioError as exc:
            self.falhou.emit(str(exc))
            return
        except Exception as exc:  # noqa: BLE001 - qualquer falha do navegador vira mensagem
            self.falhou.emit(f"Falha no robô: {exc}")
            return
        self.terminou.emit(resumo)


class OnvioDownloadDialog(QDialog):
    def __init__(self, services, competencia: tuple[int, int] | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.services = services
        self._thread: QThread | None = None
        self._robo: _Robo | None = None
        self.resumo: Resumo | None = None
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

        pasta = QHBoxLayout()
        self.destino_edit = QLineEdit(str(load_ui_state("onvio:destino", "") or pasta_padrao()))
        pasta.addWidget(self.destino_edit, 1)
        escolher = make_button("Escolher...", "quiet")
        escolher.clicked.connect(self._escolher_pasta)
        pasta.addWidget(escolher)
        form.addRow("Salvar em", pasta)
        self.ativas_check = QCheckBox("Só empresas ativas no DocFlow")
        self.ativas_check.setChecked(True)
        form.addRow("", self.ativas_check)
        self.so_onvio_check = QCheckBox("Só empresas com Onvio marcado no cadastro (meio de recebimento)")
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

    def _pasta_competencia(self) -> Path:
        return Path(self.destino_edit.text()) / f"{self.mes_combo.currentData():02d}-{self.ano_spin.value()}"

    def _abrir_pasta(self) -> None:
        pasta = Path(self.resumo.pasta) if self.resumo else self._pasta_competencia()
        if not pasta.exists():
            pasta = Path(self.destino_edit.text())
        pasta.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(pasta)))

    def empresas(self) -> list[tuple[str, str]]:
        servico = self.services.empresa_service
        if self.so_onvio_check.isChecked():
            pendentes_em = (self.ano_spin.value(), self.mes_combo.currentData()) if self.so_pendentes_check.isChecked() else None
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
        empresas = self.empresas()
        if not empresas:
            aviso = "Nenhuma empresa cadastrada."
            if self.so_onvio_check.isChecked():
                aviso = "Nenhuma empresa para baixar: todas com Onvio já estão sem documento pendente nessa competência (ou nenhuma tem Onvio marcado no cadastro)."
            QMessageBox.information(self, "Onvio", aviso)
            return
        self.lista.clear()
        self.resumo = None
        self.barra.setVisible(True)
        self.barra.setRange(0, len(empresas))
        self.barra.setValue(0)
        self.situacao_label.setText("Abrindo o Onvio...")
        self.iniciar_button.setText("Parar")
        for widget in (self.mes_combo, self.ano_spin, self.destino_edit, self.ativas_check, self.so_onvio_check, self.so_pendentes_check, self.de_novo_check):
            widget.setEnabled(False)

        self._thread = QThread(self)
        self._robo = _Robo(self.ano_spin.value(), self.mes_combo.currentData(), empresas, destino, self.de_novo_check.isChecked())
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
        for widget in (self.mes_combo, self.ano_spin, self.destino_edit, self.ativas_check, self.so_onvio_check, self.so_pendentes_check, self.de_novo_check):
            widget.setEnabled(True)

    def _terminou(self, resumo: Resumo) -> None:
        self._encerrar_thread()
        self.resumo = resumo
        self.barra.setValue(self.barra.maximum())
        self.situacao_label.setText(resumo.texto())
        problemas = [e for e in resumo.empresas if e.situacao == ERRO]
        if problemas:
            self.lista.addItem("")
            self.lista.addItem("Com erro (tente de novo):")
            for empresa in problemas:
                self.lista.addItem(f"  {empresa.codigo} - {empresa.nome}: {empresa.detalhe}")
        if any(e.situacao == BAIXADA for e in resumo.empresas):
            self.lista.addItem("")
            self.lista.addItem(f"Arquivos em {resumo.pasta} (a lista de tudo está em _resumo.json).")

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
