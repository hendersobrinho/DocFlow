from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QLineEdit, QVBoxLayout, QWidget

from documentos_empresa_app.qt_ui.icons import app_icon
from documentos_empresa_app.qt_ui.widgets.common import make_button
from documentos_empresa_app.utils.common import APP_NAME


class OrganizeConfirmationDialog(QDialog):
    """Confirma a organizacao de um documento sempre oferecendo a opcao de editar o nome
    de qualquer pasta nova que sera criada e o nome final do arquivo, em vez de so aceitar
    ou recusar a sugestao da IA as cegas."""

    def __init__(
        self,
        *,
        documento_nome: str,
        new_folders: list[Path],
        new_filename: str,
        based_on_sibling: Path | None,
        filename_is_synthesized: bool,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"{APP_NAME} - Confirmar organizacao")
        self.setWindowIcon(app_icon())
        self._new_folders = new_folders
        self._folder_name_edits: list[QLineEdit] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(10)

        header = QLabel(f'Organizar o documento "{documento_nome}":')
        header.setWordWrap(True)
        layout.addWidget(header)

        if new_folders:
            folders_label = QLabel(
                "Esta acao vai CRIAR a(s) seguinte(s) pasta(s) - edite o nome se quiser:"
            )
            folders_label.setObjectName("Muted")
            folders_label.setWordWrap(True)
            layout.addWidget(folders_label)
            for folder in new_folders:
                row = QHBoxLayout()
                parent_label = QLabel(f"{folder.parent}/")
                parent_label.setObjectName("Muted")
                row.addWidget(parent_label)
                edit = QLineEdit(folder.name)
                self._folder_name_edits.append(edit)
                row.addWidget(edit, 1)
                layout.addLayout(row)

        if filename_is_synthesized:
            filename_hint = "Nao ha exemplo existente nessa pasta; edite o nome final do arquivo se quiser:"
        elif based_on_sibling:
            filename_hint = f'Baseado no arquivo "{based_on_sibling.name}" - edite o nome final se quiser:'
        else:
            filename_hint = "Nome final do arquivo - edite se quiser:"
        filename_label = QLabel(filename_hint)
        filename_label.setObjectName("Muted")
        filename_label.setWordWrap(True)
        layout.addWidget(filename_label)
        self.filename_edit = QLineEdit(new_filename)
        layout.addWidget(self.filename_edit)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel_button = make_button("Cancelar", "quiet")
        cancel_button.clicked.connect(self.reject)
        buttons.addWidget(cancel_button)
        confirm_button = make_button("Confirmar", "primary")
        confirm_button.clicked.connect(self.accept)
        buttons.addWidget(confirm_button)
        layout.addLayout(buttons)

    def resolved_new_folders(self) -> list[Path]:
        result: list[Path] = []
        for index, original in enumerate(self._new_folders):
            parent = result[-1] if result else original.parent
            name = self._folder_name_edits[index].text().strip() or original.name
            result.append(parent / name)
        return result

    def resolved_filename(self) -> str:
        return self.filename_edit.text().strip()


def apply_confirmation_overrides(proposal, dialog: OrganizeConfirmationDialog) -> None:
    """Aplica no proposal (em memoria, antes do execute()) os nomes editados pelo usuario
    no dialogo de confirmacao. Renomear uma pasta ancestral atualiza em cascata o caminho
    das pastas descendentes e o destino final."""
    resolved_folders = dialog.resolved_new_folders()
    if resolved_folders:
        if proposal.company_dir in proposal.new_folders:
            index = proposal.new_folders.index(proposal.company_dir)
            proposal.company_dir = resolved_folders[index]
        proposal.destination_dir = resolved_folders[-1]
        proposal.new_folders = resolved_folders

    new_filename = dialog.resolved_filename()
    proposal.new_filename = new_filename or proposal.new_filename
