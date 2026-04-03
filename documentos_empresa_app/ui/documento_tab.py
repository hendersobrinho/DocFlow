from __future__ import annotations

import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

from documentos_empresa_app.utils.helpers import CompanySelector, ValidationError


class DocumentoTab(ttk.Frame):
    def __init__(self, master, services, on_data_changed) -> None:
        super().__init__(master, padding=12)
        self.services = services
        self.on_data_changed = on_data_changed
        self.current_company_id: int | None = None
        self.selected_documento_id: int | None = None

        self.nome_var = tk.StringVar()
        self.tipo_var = tk.StringVar()
        self.tipo_map: dict[str, int] = {}

        self._build_layout()

    def _build_layout(self) -> None:
        self.company_selector = CompanySelector(
            self,
            self.services.empresa_service,
            active_only=False,
            on_selected=self.on_company_selected,
            on_cleared=self._clear_company_context,
        )
        self.company_selector.pack(fill="x", pady=(0, 12))

        form = ttk.LabelFrame(self, text="Cadastro de documentos por empresa", padding=12)
        form.pack(fill="x", pady=(0, 12))

        ttk.Label(form, text="Nome do documento").grid(row=0, column=0, sticky="w")
        ttk.Entry(form, textvariable=self.nome_var).grid(row=1, column=0, sticky="ew", padx=(0, 10))

        ttk.Label(form, text="Tipo do documento").grid(row=0, column=1, sticky="w")
        self.tipo_combo = ttk.Combobox(form, textvariable=self.tipo_var, state="readonly")
        self.tipo_combo.grid(row=1, column=1, sticky="ew", padx=(0, 10))

        ttk.Button(form, text="Novo tipo", command=self.quick_add_type).grid(row=1, column=2, sticky="ew", padx=(0, 8))
        self.save_button = ttk.Button(form, text="Cadastrar documento", command=self.save_document)
        self.save_button.grid(row=1, column=3, sticky="ew", padx=(0, 8))
        ttk.Button(form, text="Limpar", command=self.clear_form).grid(row=1, column=4, sticky="ew", padx=(0, 8))
        ttk.Button(form, text="Importar Excel", command=self.import_documents).grid(row=1, column=5, sticky="ew")

        form.columnconfigure(0, weight=1)
        form.columnconfigure(1, weight=1)

        actions = ttk.Frame(self)
        actions.pack(fill="x", pady=(0, 8))
        ttk.Button(actions, text="Remover selecionado", command=self.delete_document).pack(side="left")

        list_frame = ttk.LabelFrame(self, text="Documentos cadastrados para a empresa", padding=10)
        list_frame.pack(fill="both", expand=True)

        self.tree = ttk.Treeview(list_frame, columns=("nome", "tipo"), show="headings", selectmode="browse")
        self.tree.heading("nome", text="Nome do documento")
        self.tree.heading("tipo", text="Tipo")
        self.tree.column("nome", width=520)
        self.tree.column("tipo", width=220)
        self.tree.pack(side="left", fill="both", expand=True)
        self.tree.bind("<<TreeviewSelect>>", self.load_selected_document)

        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.tree.yview)
        scrollbar.pack(side="right", fill="y")
        self.tree.configure(yscrollcommand=scrollbar.set)

    def refresh_data(self) -> None:
        self.company_selector.refresh_companies()
        self.refresh_type_options()
        self.refresh_document_list()

    def refresh_type_options(self) -> None:
        tipos = self.services.tipo_service.list_tipos()
        self.tipo_map = {tipo["nome_tipo"]: tipo["id"] for tipo in tipos}
        self.tipo_combo["values"] = list(self.tipo_map.keys())

    def refresh_document_list(self) -> None:
        self.tree.delete(*self.tree.get_children())
        company_id = self.company_selector.get_selected_company_id()
        if not company_id:
            self.current_company_id = None
            self.clear_form()
            return
        for documento in self.services.documento_service.list_documentos_empresa(company_id):
            self.tree.insert(
                "",
                "end",
                iid=str(documento["id"]),
                values=(documento["nome_documento"], documento["nome_tipo"]),
            )

    def on_company_selected(self, company: dict) -> None:
        company_changed = self.current_company_id != company["id"]
        self.current_company_id = company["id"]
        if company_changed:
            self.clear_form()
        self.refresh_document_list()

    def _clear_company_context(self) -> None:
        self.current_company_id = None
        self.tree.delete(*self.tree.get_children())
        self.clear_form()

    def clear_form(self) -> None:
        self.selected_documento_id = None
        self.nome_var.set("")
        self.tipo_var.set("")
        self.save_button.configure(text="Cadastrar documento")
        selection = self.tree.selection()
        if selection:
            self.tree.selection_remove(*selection)

    def quick_add_type(self) -> None:
        nome = simpledialog.askstring("Novo tipo", "Informe o nome do novo tipo:", parent=self)
        if not nome:
            return
        try:
            self.services.tipo_service.create_tipo(nome)
        except ValidationError as exc:
            messagebox.showerror("Tipos", str(exc), parent=self)
            return
        self.refresh_type_options()
        self.tipo_var.set(nome.strip())
        self.on_data_changed()

    def save_document(self) -> None:
        company_id = self.company_selector.get_selected_company_id()
        if not company_id:
            messagebox.showwarning("Documentos", "Selecione uma empresa primeiro.", parent=self)
            return
        tipo_id = self.tipo_map.get(self.tipo_var.get())
        if not tipo_id:
            messagebox.showwarning("Documentos", "Selecione um tipo valido.", parent=self)
            return

        try:
            if self.selected_documento_id:
                self.services.documento_service.update_documento(self.selected_documento_id, tipo_id, self.nome_var.get())
                messagebox.showinfo("Documentos", "Documento atualizado com sucesso.", parent=self)
            else:
                self.services.documento_service.create_documento(company_id, tipo_id, self.nome_var.get())
                messagebox.showinfo("Documentos", "Documento cadastrado com sucesso.", parent=self)
        except ValidationError as exc:
            messagebox.showerror("Documentos", str(exc), parent=self)
            return

        self.clear_form()
        self.on_data_changed()
        self.company_selector.set_company(company_id)

    def load_selected_document(self, _event=None) -> None:
        selection = self.tree.selection()
        if not selection:
            return
        self.selected_documento_id = int(selection[0])
        documento = self.services.documento_service.get_documento(self.selected_documento_id)
        tipo = self.services.tipo_service.get_tipo(documento["tipo_documento_id"])
        self.nome_var.set(documento["nome_documento"])
        self.tipo_var.set(tipo["nome_tipo"])
        self.save_button.configure(text="Salvar alteracoes")

    def delete_document(self) -> None:
        if not self.selected_documento_id:
            messagebox.showwarning("Documentos", "Selecione um documento na lista.", parent=self)
            return
        if not messagebox.askyesno(
            "Excluir documento",
            "Deseja excluir o documento selecionado? Os status mensais vinculados tambem serao apagados.",
            parent=self,
        ):
            return

        company_id = self.company_selector.get_selected_company_id()
        self.services.documento_service.delete_documento(self.selected_documento_id)
        self.clear_form()
        self.on_data_changed()
        self.company_selector.set_company(company_id)
        messagebox.showinfo("Documentos", "Documento excluido com sucesso.", parent=self)

    def import_documents(self) -> None:
        company_id = self.company_selector.get_selected_company_id()
        if not company_id:
            messagebox.showwarning("Documentos", "Selecione uma empresa antes de importar.", parent=self)
            return

        file_path = filedialog.askopenfilename(
            parent=self,
            title="Selecione o arquivo Excel",
            filetypes=[("Arquivos Excel", "*.xlsx *.xlsm"), ("Todos os arquivos", "*.*")],
        )
        if not file_path:
            return

        try:
            result = self.services.import_service.import_documentos(file_path, company_id)
        except ValidationError as exc:
            messagebox.showerror("Importacao de documentos", str(exc), parent=self)
            return

        self.on_data_changed()
        self.company_selector.set_company(company_id)
        summary = [
            f'Documentos importados: {result["imported"]}',
            f'Documentos com falha: {result["failed"]}',
        ]
        if result["errors"]:
            summary.append("")
            summary.append("Erros encontrados:")
            summary.extend(result["errors"][:10])
        messagebox.showinfo("Importacao de documentos", "\n".join(summary), parent=self)
