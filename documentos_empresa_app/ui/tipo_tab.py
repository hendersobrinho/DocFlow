from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from documentos_empresa_app.utils.helpers import ValidationError


class TipoTab(ttk.Frame):
    def __init__(self, master, services, on_data_changed) -> None:
        super().__init__(master, padding=12)
        self.services = services
        self.on_data_changed = on_data_changed
        self.selected_tipo_id: int | None = None
        self.nome_var = tk.StringVar()
        self._build_layout()

    def _build_layout(self) -> None:
        form = ttk.LabelFrame(self, text="Cadastro de tipos de documento", padding=12)
        form.pack(fill="x", pady=(0, 12))

        ttk.Label(form, text="Nome do tipo").grid(row=0, column=0, sticky="w")
        ttk.Entry(form, textvariable=self.nome_var).grid(row=1, column=0, sticky="ew", padx=(0, 10))
        self.save_button = ttk.Button(form, text="Cadastrar tipo", command=self.save_tipo)
        self.save_button.grid(row=1, column=1, sticky="ew", padx=(0, 8))
        ttk.Button(form, text="Limpar", command=self.clear_form).grid(row=1, column=2, sticky="ew", padx=(0, 8))
        ttk.Button(form, text="Excluir selecionado", command=self.delete_tipo).grid(row=1, column=3, sticky="ew")
        form.columnconfigure(0, weight=1)

        list_frame = ttk.LabelFrame(self, text="Tipos cadastrados", padding=10)
        list_frame.pack(fill="both", expand=True)

        self.tree = ttk.Treeview(list_frame, columns=("nome",), show="headings", selectmode="browse")
        self.tree.heading("nome", text="Nome do tipo")
        self.tree.column("nome", width=600)
        self.tree.pack(side="left", fill="both", expand=True)
        self.tree.bind("<<TreeviewSelect>>", self.load_selected_tipo)

        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.tree.yview)
        scrollbar.pack(side="right", fill="y")
        self.tree.configure(yscrollcommand=scrollbar.set)

    def refresh_data(self) -> None:
        self.tree.delete(*self.tree.get_children())
        for tipo in self.services.tipo_service.list_tipos():
            self.tree.insert("", "end", iid=str(tipo["id"]), values=(tipo["nome_tipo"],))

    def load_selected_tipo(self, _event=None) -> None:
        selection = self.tree.selection()
        if not selection:
            return
        self.selected_tipo_id = int(selection[0])
        tipo = self.services.tipo_service.get_tipo(self.selected_tipo_id)
        self.nome_var.set(tipo["nome_tipo"])
        self.save_button.configure(text="Salvar alteracoes")

    def clear_form(self) -> None:
        self.selected_tipo_id = None
        self.nome_var.set("")
        self.save_button.configure(text="Cadastrar tipo")
        selection = self.tree.selection()
        if selection:
            self.tree.selection_remove(*selection)

    def save_tipo(self) -> None:
        try:
            if self.selected_tipo_id:
                self.services.tipo_service.update_tipo(self.selected_tipo_id, self.nome_var.get())
                messagebox.showinfo("Tipos", "Tipo atualizado com sucesso.", parent=self)
            else:
                self.services.tipo_service.create_tipo(self.nome_var.get())
                messagebox.showinfo("Tipos", "Tipo cadastrado com sucesso.", parent=self)
        except ValidationError as exc:
            messagebox.showerror("Tipos", str(exc), parent=self)
            return

        self.clear_form()
        self.on_data_changed()

    def delete_tipo(self) -> None:
        if not self.selected_tipo_id:
            messagebox.showwarning("Tipos", "Selecione um tipo na lista.", parent=self)
            return
        if not messagebox.askyesno("Excluir tipo", "Deseja excluir o tipo selecionado?", parent=self):
            return
        try:
            self.services.tipo_service.delete_tipo(self.selected_tipo_id)
        except ValidationError as exc:
            messagebox.showerror("Tipos", str(exc), parent=self)
            return

        self.clear_form()
        self.on_data_changed()
        messagebox.showinfo("Tipos", "Tipo excluido com sucesso.", parent=self)
