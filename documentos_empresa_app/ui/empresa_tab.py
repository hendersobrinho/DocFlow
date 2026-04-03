from __future__ import annotations

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from documentos_empresa_app.ui.delivery_methods_field import DeliveryMethodsField
from documentos_empresa_app.utils.helpers import ValidationError


class EmpresaTab(ttk.Frame):
    def __init__(self, master, services, on_data_changed) -> None:
        super().__init__(master, padding=12)
        self.services = services
        self.on_data_changed = on_data_changed
        self.selected_company_id: int | None = None

        self.codigo_var = tk.StringVar()
        self.nome_var = tk.StringVar()
        self.email_var = tk.StringVar()
        self.contato_var = tk.StringVar()

        self._build_layout()

    def _build_layout(self) -> None:
        form = ttk.LabelFrame(self, text="Cadastro de empresas", padding=12)
        form.pack(fill="x", pady=(0, 12))

        ttk.Label(form, text="Codigo da empresa").grid(row=0, column=0, sticky="w")
        self.codigo_entry = ttk.Entry(form, textvariable=self.codigo_var, width=18)
        self.codigo_entry.grid(row=1, column=0, sticky="w", padx=(0, 10))

        ttk.Label(form, text="Nome da empresa").grid(row=0, column=1, sticky="w")
        ttk.Entry(form, textvariable=self.nome_var).grid(row=1, column=1, sticky="ew", padx=(0, 10))

        self.delivery_field = DeliveryMethodsField(
            form,
            title="Meios de recebimento da documentacao",
            dialog_title="Empresas",
        )
        self.delivery_field.grid(row=2, column=0, columnspan=5, sticky="ew", pady=(10, 8))

        ttk.Label(form, text="Email para contato (opcional)").grid(row=4, column=0, sticky="w")
        ttk.Entry(form, textvariable=self.email_var).grid(row=5, column=0, sticky="ew", padx=(0, 10))

        ttk.Label(form, text="Nome de contato (opcional)").grid(row=4, column=1, sticky="w")
        ttk.Entry(form, textvariable=self.contato_var).grid(row=5, column=1, sticky="ew", padx=(0, 10))

        self.save_button = ttk.Button(form, text="Cadastrar empresa", command=self.save_company)
        self.save_button.grid(row=5, column=2, sticky="ew", padx=(0, 8))

        ttk.Button(form, text="Limpar", command=self.clear_form).grid(row=5, column=3, sticky="ew", padx=(0, 8))
        ttk.Button(form, text="Importar Excel", command=self.import_companies).grid(row=5, column=4, sticky="ew")

        form.columnconfigure(0, weight=1)
        form.columnconfigure(1, weight=1)

        actions = ttk.Frame(self)
        actions.pack(fill="x", pady=(0, 8))
        ttk.Button(actions, text="Inativar selecionada", command=lambda: self.set_selected_active(False)).pack(
            side="left", padx=(0, 8)
        )
        ttk.Button(actions, text="Reativar selecionada", command=lambda: self.set_selected_active(True)).pack(
            side="left", padx=(0, 8)
        )
        ttk.Button(actions, text="Excluir selecionada", command=self.delete_company).pack(side="left")

        list_frame = ttk.LabelFrame(self, text="Empresas cadastradas", padding=10)
        list_frame.pack(fill="both", expand=True)

        self.tree = ttk.Treeview(
            list_frame,
            columns=("codigo", "nome", "situacao"),
            show="headings",
            selectmode="browse",
        )
        self.tree.heading("codigo", text="Codigo")
        self.tree.heading("nome", text="Nome")
        self.tree.heading("situacao", text="Situacao")
        self.tree.column("codigo", width=120, anchor="center")
        self.tree.column("nome", width=520)
        self.tree.column("situacao", width=120, anchor="center")
        self.tree.pack(side="left", fill="both", expand=True)
        self.tree.bind("<<TreeviewSelect>>", self.load_selected_company)

        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.tree.yview)
        scrollbar.pack(side="right", fill="y")
        self.tree.configure(yscrollcommand=scrollbar.set)

    def refresh_data(self) -> None:
        self.tree.delete(*self.tree.get_children())
        for company in self.services.empresa_service.list_empresas(active_only=False):
            situacao = "Ativa" if company["ativa"] else "Inativa"
            self.tree.insert(
                "",
                "end",
                iid=str(company["id"]),
                values=(company["codigo_empresa"], company["nome_empresa"], situacao),
            )

    def load_selected_company(self, _event=None) -> None:
        selection = self.tree.selection()
        if not selection:
            return
        self.selected_company_id = int(selection[0])
        empresa = self.services.empresa_service.get_empresa(self.selected_company_id)
        self.codigo_var.set(str(empresa["codigo_empresa"]))
        self.nome_var.set(empresa["nome_empresa"])
        self.email_var.set(empresa.get("email_contato") or "")
        self.contato_var.set(empresa.get("nome_contato") or "")
        self.delivery_field.set_values(empresa.get("meios_recebimento"))
        self.codigo_entry.configure(state="disabled")
        self.save_button.configure(text="Salvar alteracoes")

    def clear_form(self) -> None:
        self.selected_company_id = None
        self.codigo_var.set("")
        self.nome_var.set("")
        self.email_var.set("")
        self.contato_var.set("")
        self.delivery_field.clear()
        self.codigo_entry.configure(state="normal")
        self.save_button.configure(text="Cadastrar empresa")
        selection = self.tree.selection()
        if selection:
            self.tree.selection_remove(*selection)

    def save_company(self) -> None:
        try:
            if self.selected_company_id:
                self.services.empresa_service.update_empresa(
                    self.selected_company_id,
                    self.nome_var.get(),
                    self.delivery_field.get_values(),
                    self.email_var.get(),
                    self.contato_var.get(),
                )
                messagebox.showinfo("Empresas", "Empresa atualizada com sucesso.", parent=self)
            else:
                self.services.empresa_service.create_empresa(
                    self.codigo_var.get(),
                    self.nome_var.get(),
                    self.delivery_field.get_values(),
                    self.email_var.get(),
                    self.contato_var.get(),
                )
                messagebox.showinfo("Empresas", "Empresa cadastrada com sucesso.", parent=self)
        except ValidationError as exc:
            messagebox.showerror("Empresas", str(exc), parent=self)
            return

        self.clear_form()
        self.on_data_changed()

    def set_selected_active(self, active: bool) -> None:
        if not self.selected_company_id:
            messagebox.showwarning("Empresas", "Selecione uma empresa na lista.", parent=self)
            return
        self.services.empresa_service.set_empresa_ativa(self.selected_company_id, active)
        estado = "reativada" if active else "inativada"
        messagebox.showinfo("Empresas", f"Empresa {estado} com sucesso.", parent=self)
        self.on_data_changed()

    def delete_company(self) -> None:
        if not self.selected_company_id:
            messagebox.showwarning("Empresas", "Selecione uma empresa na lista.", parent=self)
            return
        if not messagebox.askyesno(
            "Excluir empresa",
            "Deseja excluir a empresa selecionada? Os documentos e status mensais vinculados tambem serao apagados.",
            parent=self,
        ):
            return

        self.services.empresa_service.delete_empresa(self.selected_company_id)
        self.clear_form()
        self.on_data_changed()
        messagebox.showinfo("Empresas", "Empresa excluida com sucesso.", parent=self)

    def import_companies(self) -> None:
        file_path = filedialog.askopenfilename(
            parent=self,
            title="Selecione o arquivo Excel",
            filetypes=[("Arquivos Excel", "*.xlsx *.xlsm"), ("Todos os arquivos", "*.*")],
        )
        if not file_path:
            return

        try:
            result = self.services.import_service.import_empresas(file_path)
        except ValidationError as exc:
            messagebox.showerror("Importacao de empresas", str(exc), parent=self)
            return

        self.on_data_changed()
        summary = [
            f'Registros importados: {result["imported"]}',
            f'Registros com falha: {result["failed"]}',
        ]
        if result["errors"]:
            summary.append("")
            summary.append("Erros encontrados:")
            summary.extend(result["errors"][:10])
        messagebox.showinfo("Importacao de empresas", "\n".join(summary), parent=self)
