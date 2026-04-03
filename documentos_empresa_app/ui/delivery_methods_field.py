from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from documentos_empresa_app.utils.common import DOCUMENT_DELIVERY_OPTIONS, parse_delivery_methods


class DeliveryMethodsField(ttk.LabelFrame):
    def __init__(
        self,
        master,
        title: str = "Meios de recebimento",
        dialog_title: str = "Empresas",
    ) -> None:
        super().__init__(master, text=title, padding=8)
        self.dialog_title = dialog_title
        self.option_var = tk.StringVar()

        self.combo = ttk.Combobox(
            self,
            textvariable=self.option_var,
            values=DOCUMENT_DELIVERY_OPTIONS,
            state="readonly",
            width=18,
        )
        self.combo.grid(row=0, column=0, sticky="w", padx=(0, 8))

        ttk.Button(self, text="Adicionar meio", command=self.add_selected).grid(
            row=0, column=1, sticky="w", padx=(0, 8)
        )
        ttk.Button(self, text="Remover selecionado", command=self.remove_selected).grid(row=0, column=2, sticky="w")

        self.listbox = tk.Listbox(self, height=3, exportselection=False)
        self.listbox.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(8, 0))
        self.columnconfigure(0, weight=1)

    def get_values(self) -> list[str]:
        return list(self.listbox.get(0, tk.END))

    def set_values(self, raw_value: str | list[str] | tuple[str, ...] | None) -> None:
        self.option_var.set("")
        self.listbox.delete(0, tk.END)
        for item in parse_delivery_methods(raw_value):
            self.listbox.insert(tk.END, item)

    def clear(self) -> None:
        self.set_values(None)

    def add_selected(self) -> None:
        selected = self.option_var.get().strip()
        if not selected:
            messagebox.showwarning(self.dialog_title, "Selecione um meio na lista suspensa.", parent=self)
            return
        if selected not in self.get_values():
            self.listbox.insert(tk.END, selected)
        self.option_var.set("")

    def remove_selected(self) -> None:
        selection = self.listbox.curselection()
        if not selection:
            messagebox.showwarning(self.dialog_title, "Selecione um meio na lista para remover.", parent=self)
            return
        for index in reversed(selection):
            self.listbox.delete(index)
