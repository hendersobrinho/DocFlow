from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from documentos_empresa_app.ui.delivery_methods_field import DeliveryMethodsField
from documentos_empresa_app.utils.helpers import CompanySelector, ValidationError


class EdicaoTab(ttk.Frame):
    def __init__(self, master, services, on_data_changed) -> None:
        super().__init__(master, padding=12)
        self.services = services
        self.on_data_changed = on_data_changed
        self.current_company_id: int | None = None
        self.tipo_map: dict[str, int] = {}

        self.codigo_var = tk.StringVar()
        self.nome_empresa_var = tk.StringVar()
        self.email_contato_var = tk.StringVar()
        self.nome_contato_var = tk.StringVar()
        self.situacao_var = tk.StringVar(value="Nenhuma empresa carregada.")
        self.nome_documento_var = tk.StringVar()
        self.tipo_var = tk.StringVar()

        self._build_layout()

    def _build_layout(self) -> None:
        self.company_selector = CompanySelector(
            self,
            self.services.empresa_service,
            active_only=False,
            on_selected=self.load_company,
            on_cleared=self._clear_company_context,
        )
        self.company_selector.pack(fill="x", pady=(0, 12))

        company_frame = ttk.LabelFrame(self, text="Edicao da empresa", padding=12)
        company_frame.pack(fill="x", pady=(0, 12))

        ttk.Label(company_frame, text="Codigo").grid(row=0, column=0, sticky="w")
        ttk.Entry(company_frame, textvariable=self.codigo_var, state="readonly", width=16).grid(
            row=1, column=0, sticky="w", padx=(0, 10)
        )

        ttk.Label(company_frame, text="Nome da empresa").grid(row=0, column=1, sticky="w")
        ttk.Entry(company_frame, textvariable=self.nome_empresa_var).grid(row=1, column=1, sticky="ew", padx=(0, 10))

        ttk.Label(company_frame, text="Email para contato (opcional)").grid(row=0, column=2, sticky="w")
        ttk.Entry(company_frame, textvariable=self.email_contato_var).grid(row=1, column=2, sticky="ew", padx=(0, 10))

        ttk.Label(company_frame, text="Nome de contato (opcional)").grid(row=0, column=3, sticky="w")
        ttk.Entry(company_frame, textvariable=self.nome_contato_var).grid(row=1, column=3, sticky="ew", padx=(0, 10))

        self.delivery_field = DeliveryMethodsField(
            company_frame,
            title="Meios de recebimento",
            dialog_title="Edicao",
            delivery_method_service=self.services.delivery_method_service,
        )
        self.delivery_field.grid(row=2, column=0, columnspan=6, sticky="ew", pady=(10, 8))

        ttk.Button(company_frame, text="Salvar dados", command=self.save_company_name).grid(
            row=4, column=0, sticky="ew", padx=(0, 8)
        )
        ttk.Button(company_frame, text="Inativar", command=lambda: self.set_company_active(False)).grid(
            row=4, column=1, sticky="ew", padx=(0, 8)
        )
        ttk.Button(company_frame, text="Reativar", command=lambda: self.set_company_active(True)).grid(
            row=4, column=2, sticky="ew", padx=(0, 8)
        )
        ttk.Button(company_frame, text="Excluir empresa", command=self.delete_company).grid(row=4, column=3, sticky="ew")
        ttk.Label(company_frame, textvariable=self.situacao_var).grid(row=5, column=0, columnspan=6, sticky="w", pady=(8, 0))

        company_frame.columnconfigure(1, weight=1)
        company_frame.columnconfigure(2, weight=1)
        company_frame.columnconfigure(3, weight=1)

        document_frame = ttk.LabelFrame(self, text="Documentos vinculados", padding=12)
        document_frame.pack(fill="both", expand=True)

        self.tree = ttk.Treeview(
            document_frame,
            columns=("nome", "tipo"),
            show="headings",
            selectmode="extended",
            height=14,
        )
        self.tree.heading("nome", text="Nome do documento")
        self.tree.heading("tipo", text="Tipo")
        self.tree.column("nome", width=520)
        self.tree.column("tipo", width=220)
        self.tree.grid(row=0, column=0, rowspan=4, sticky="nsew")
        self.tree.bind("<<TreeviewSelect>>", self.load_selected_document)

        scrollbar = ttk.Scrollbar(document_frame, orient="vertical", command=self.tree.yview)
        scrollbar.grid(row=0, column=1, rowspan=4, sticky="ns")
        self.tree.configure(yscrollcommand=scrollbar.set)

        ttk.Label(document_frame, text="Nome do documento").grid(row=0, column=2, sticky="w", padx=(12, 0))
        ttk.Entry(document_frame, textvariable=self.nome_documento_var).grid(
            row=1, column=2, sticky="ew", padx=(12, 0), pady=(0, 8)
        )

        ttk.Label(document_frame, text="Tipo do documento").grid(row=2, column=2, sticky="w", padx=(12, 0))
        self.tipo_combo = ttk.Combobox(document_frame, textvariable=self.tipo_var, state="readonly")
        self.tipo_combo.grid(row=3, column=2, sticky="ew", padx=(12, 0), pady=(0, 8))

        button_row = ttk.Frame(document_frame)
        button_row.grid(row=4, column=2, sticky="ew", padx=(12, 0))
        ttk.Button(button_row, text="Salvar documento", command=self.save_document).pack(side="left", padx=(0, 8))
        ttk.Button(button_row, text="Limpar campos", command=self.clear_document_fields).pack(side="left", padx=(0, 8))
        ttk.Button(button_row, text="Excluir selecionados", command=self.delete_selected_documents).pack(side="left")

        document_frame.columnconfigure(0, weight=1)
        document_frame.columnconfigure(2, weight=1)

    def refresh_data(self) -> None:
        self.refresh_type_options()
        self.company_selector.refresh_companies()
        if self.current_company_id:
            self.company_selector.set_company(self.current_company_id)

    def refresh_type_options(self) -> None:
        tipos = self.services.tipo_service.list_tipos()
        self.tipo_map = {tipo["nome_tipo"]: tipo["id"] for tipo in tipos}
        self.tipo_combo["values"] = list(self.tipo_map.keys())

    def load_company(self, company: dict) -> None:
        self.current_company_id = company["id"]
        self.codigo_var.set(str(company["codigo_empresa"]))
        self.nome_empresa_var.set(company["nome_empresa"])
        self.email_contato_var.set(company.get("email_contato") or "")
        self.nome_contato_var.set(company.get("nome_contato") or "")
        self.delivery_field.set_values(company.get("meios_recebimento"))
        self.situacao_var.set("Empresa ativa." if company["ativa"] else "Empresa inativa.")
        self.refresh_document_list()

    def _clear_company_context(self) -> None:
        self.current_company_id = None
        self.codigo_var.set("")
        self.nome_empresa_var.set("")
        self.email_contato_var.set("")
        self.nome_contato_var.set("")
        self.delivery_field.clear()
        self.situacao_var.set("Nenhuma empresa carregada.")
        self.tree.delete(*self.tree.get_children())
        self.clear_document_fields()

    def refresh_document_list(self) -> None:
        self.tree.delete(*self.tree.get_children())
        if not self.current_company_id:
            return
        for documento in self.services.documento_service.list_documentos_empresa(self.current_company_id):
            self.tree.insert(
                "",
                "end",
                iid=str(documento["id"]),
                values=(documento["nome_documento"], documento["nome_tipo"]),
            )

    def save_company_name(self) -> None:
        if not self.current_company_id:
            messagebox.showwarning("Edicao", "Selecione uma empresa primeiro.", parent=self)
            return
        try:
            self.services.empresa_service.update_empresa(
                self.current_company_id,
                self.nome_empresa_var.get(),
                self.delivery_field.get_values(),
                self.email_contato_var.get(),
                self.nome_contato_var.get(),
            )
        except ValidationError as exc:
            messagebox.showerror("Edicao", str(exc), parent=self)
            return
        self.on_data_changed()
        self.company_selector.set_company(self.current_company_id)
        messagebox.showinfo("Edicao", "Dados da empresa atualizados com sucesso.", parent=self)

    def set_company_active(self, active: bool) -> None:
        if not self.current_company_id:
            messagebox.showwarning("Edicao", "Selecione uma empresa primeiro.", parent=self)
            return
        self.services.empresa_service.set_empresa_ativa(self.current_company_id, active)
        self.on_data_changed()
        self.company_selector.set_company(self.current_company_id)
        messagebox.showinfo("Edicao", "Situacao da empresa atualizada com sucesso.", parent=self)

    def delete_company(self) -> None:
        if not self.current_company_id:
            messagebox.showwarning("Edicao", "Selecione uma empresa primeiro.", parent=self)
            return
        if not messagebox.askyesno(
            "Excluir empresa",
            "Ao excluir a empresa, os documentos vinculados e os status mensais tambem serao removidos. Deseja continuar?",
            parent=self,
        ):
            return
        self.services.empresa_service.delete_empresa(self.current_company_id)
        self.company_selector.clear_selection()
        self.on_data_changed()
        messagebox.showinfo("Edicao", "Empresa excluida com sucesso.", parent=self)

    def load_selected_document(self, _event=None) -> None:
        selection = self.tree.selection()
        if len(selection) != 1:
            return
        documento = self.services.documento_service.get_documento(int(selection[0]))
        tipo = self.services.tipo_service.get_tipo(documento["tipo_documento_id"])
        self.nome_documento_var.set(documento["nome_documento"])
        self.tipo_var.set(tipo["nome_tipo"])

    def clear_document_fields(self) -> None:
        self.nome_documento_var.set("")
        self.tipo_var.set("")
        selection = self.tree.selection()
        if selection:
            self.tree.selection_remove(*selection)

    def save_document(self) -> None:
        selection = self.tree.selection()
        if not self.current_company_id:
            messagebox.showwarning("Edicao", "Selecione uma empresa primeiro.", parent=self)
            return
        if len(selection) != 1:
            messagebox.showwarning("Edicao", "Selecione apenas um documento para editar.", parent=self)
            return
        tipo_id = self.tipo_map.get(self.tipo_var.get())
        if not tipo_id:
            messagebox.showwarning("Edicao", "Selecione um tipo valido.", parent=self)
            return
        documento_id = int(selection[0])
        try:
            self.services.documento_service.update_documento(documento_id, tipo_id, self.nome_documento_var.get())
        except ValidationError as exc:
            messagebox.showerror("Edicao", str(exc), parent=self)
            return
        self.on_data_changed()
        self.company_selector.set_company(self.current_company_id)
        messagebox.showinfo("Edicao", "Documento atualizado com sucesso.", parent=self)

    def delete_selected_documents(self) -> None:
        selection = self.tree.selection()
        if not selection:
            messagebox.showwarning("Edicao", "Selecione um ou mais documentos para excluir.", parent=self)
            return
        if not messagebox.askyesno(
            "Excluir documentos",
            "Os documentos selecionados e os respectivos status mensais serao excluidos. Deseja continuar?",
            parent=self,
        ):
            return
        self.services.documento_service.delete_documentos([int(item) for item in selection])
        self.clear_document_fields()
        self.on_data_changed()
        self.company_selector.set_company(self.current_company_id)
        messagebox.showinfo("Edicao", "Documentos excluidos com sucesso.", parent=self)
