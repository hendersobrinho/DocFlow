from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from documentos_empresa_app.utils.common import DOCUMENT_DELIVERY_OPTIONS, ValidationError, parse_delivery_methods


class DeliveryMethodsManagerDialog(tk.Toplevel):
    def __init__(self, parent: tk.Misc, delivery_method_service, dialog_title: str) -> None:
        super().__init__(parent.winfo_toplevel())
        self.parent = parent
        self.delivery_method_service = delivery_method_service
        self.dialog_title = dialog_title
        self.selected_method_id: int | None = None
        self.nome_var = tk.StringVar()

        self.title(f"{dialog_title} - Meios do sistema")
        self.transient(parent.winfo_toplevel())
        self.resizable(True, True)
        self.minsize(420, 320)

        self._build_layout()
        self.refresh_methods()
        self.grab_set()
        self.after(10, self._center_on_parent)

    def _build_layout(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        ttk.Label(
            self,
            text=(
                "Gerencie os meios disponiveis no sistema. Renomear atualiza tambem as empresas que usam o meio. "
                "Excluir remove apenas da lista do sistema."
            ),
            justify="left",
            wraplength=440,
        ).grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 8))

        list_frame = ttk.LabelFrame(self, text="Meios cadastrados", padding=10)
        list_frame.grid(row=1, column=0, sticky="nsew", padx=12)
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)

        self.tree = ttk.Treeview(list_frame, columns=("nome",), show="headings", selectmode="browse", height=10)
        self.tree.heading("nome", text="Nome")
        self.tree.column("nome", width=260)
        self.tree.grid(row=0, column=0, sticky="nsew")
        self.tree.bind("<<TreeviewSelect>>", self.load_selected_method)

        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.tree.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=scrollbar.set)

        editor = ttk.LabelFrame(self, text="Editar lista", padding=10)
        editor.grid(row=2, column=0, sticky="ew", padx=12, pady=(12, 12))
        editor.columnconfigure(0, weight=1)
        editor.columnconfigure(1, weight=1)

        ttk.Label(editor, text="Nome do meio").grid(row=0, column=0, columnspan=2, sticky="w")
        entry = ttk.Entry(editor, textvariable=self.nome_var)
        entry.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        entry.bind("<Return>", self.save_method)

        self.save_button = ttk.Button(editor, text="Adicionar", command=self.save_method)
        self.save_button.grid(row=2, column=0, sticky="ew", padx=(0, 8))
        ttk.Button(editor, text="Limpar", command=self.clear_selection).grid(row=2, column=1, sticky="ew")
        ttk.Button(editor, text="Excluir do sistema", command=self.delete_selected_method).grid(
            row=3, column=0, columnspan=2, sticky="ew", pady=(8, 0)
        )

    def _center_on_parent(self) -> None:
        self.update_idletasks()
        parent = self.parent.winfo_toplevel()
        x = parent.winfo_rootx() + max((parent.winfo_width() - self.winfo_width()) // 2, 0)
        y = parent.winfo_rooty() + max((parent.winfo_height() - self.winfo_height()) // 2, 0)
        self.geometry(f"+{x}+{y}")

    def refresh_methods(self) -> None:
        self.tree.delete(*self.tree.get_children())
        for method in self.delivery_method_service.list_methods():
            self.tree.insert("", "end", iid=str(method["id"]), values=(method["nome_meio"],))

        if self.selected_method_id and self.tree.exists(str(self.selected_method_id)):
            self.tree.selection_set(str(self.selected_method_id))
            self.tree.focus(str(self.selected_method_id))
            self.tree.see(str(self.selected_method_id))
            return

        self.clear_selection()

    def load_selected_method(self, _event=None) -> None:
        selection = self.tree.selection()
        if not selection:
            return

        method = self.delivery_method_service.get_method(int(selection[0]))
        self.selected_method_id = method["id"]
        self.nome_var.set(method["nome_meio"])
        self.save_button.configure(text="Renomear")

    def clear_selection(self) -> None:
        self.selected_method_id = None
        self.nome_var.set("")
        self.save_button.configure(text="Adicionar")
        selection = self.tree.selection()
        if selection:
            self.tree.selection_remove(*selection)

    def save_method(self, _event=None) -> None:
        try:
            if self.selected_method_id:
                affected_companies = self.delivery_method_service.update_method(self.selected_method_id, self.nome_var.get())
                message = "Meio atualizado com sucesso."
                if affected_companies:
                    message += f" Empresas ajustadas: {affected_companies}."
                messagebox.showinfo(self.dialog_title, message, parent=self)
            else:
                self.delivery_method_service.create_method(self.nome_var.get())
                messagebox.showinfo(self.dialog_title, "Meio cadastrado com sucesso.", parent=self)
        except ValidationError as exc:
            messagebox.showerror(self.dialog_title, str(exc), parent=self)
            return

        self.refresh_methods()

    def delete_selected_method(self) -> None:
        if not self.selected_method_id:
            messagebox.showwarning(self.dialog_title, "Selecione um meio na lista.", parent=self)
            return

        method = self.delivery_method_service.get_method(self.selected_method_id)
        affected_companies = self.delivery_method_service.count_companies_using(method["nome_meio"])
        prompt = f'Deseja excluir "{method["nome_meio"]}" da lista do sistema?'
        if affected_companies:
            prompt += (
                f"\n\nEsse meio ainda aparece em {affected_companies} empresa(s). "
                "A exclusao remove apenas da lista do sistema."
            )

        if not messagebox.askyesno(self.dialog_title, prompt, parent=self):
            return

        self.delivery_method_service.delete_method(self.selected_method_id)
        self.refresh_methods()
        messagebox.showinfo(self.dialog_title, "Meio removido da lista do sistema.", parent=self)


class DeliveryMethodsField(ttk.LabelFrame):
    def __init__(
        self,
        master,
        title: str = "Meios de recebimento",
        dialog_title: str = "Empresas",
        delivery_method_service=None,
    ) -> None:
        super().__init__(master, text=title, padding=8)
        self.dialog_title = dialog_title
        self.delivery_method_service = delivery_method_service
        self.option_var = tk.StringVar()
        self.summary_var = tk.StringVar(value="Nenhum meio selecionado.")
        self.selected_values: list[str] = []
        self.available_values: list[str] = list(DOCUMENT_DELIVERY_OPTIONS)

        self.combo = ttk.Combobox(
            self,
            textvariable=self.option_var,
            values=self.available_values,
            state="normal",
            width=18,
        )
        self.combo.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self.combo.bind("<Return>", self.add_selected)

        ttk.Button(self, text="+", width=3, command=self.add_selected).grid(row=0, column=1, sticky="ew", padx=(0, 4))
        ttk.Button(self, text="-", width=3, command=self.remove_selected).grid(row=0, column=2, sticky="ew", padx=(0, 4))
        self.manage_button = ttk.Button(self, text="...", width=3, command=self.open_manager_dialog)
        self.manage_button.grid(row=0, column=3, sticky="ew")

        self.hint_label = ttk.Label(
            self,
            text="Use + para incluir, - para retirar e ... para gerenciar a lista do sistema.",
            justify="left",
        )
        self.hint_label.grid(row=1, column=0, columnspan=4, sticky="w", pady=(6, 2))

        self.summary_label = ttk.Label(
            self,
            textvariable=self.summary_var,
            justify="left",
            foreground="#4F4F4F",
            wraplength=520,
        )
        self.summary_label.grid(row=2, column=0, columnspan=4, sticky="w")

        self.columnconfigure(0, weight=1)
        self.bind("<Configure>", self._on_resize)
        self.refresh_available_values()

    def get_values(self) -> list[str]:
        return list(self.selected_values)

    def set_values(self, raw_value: str | list[str] | tuple[str, ...] | None) -> None:
        self.option_var.set("")
        self.selected_values = parse_delivery_methods(raw_value, known_options=self.available_values)
        self._merge_available_values(self.selected_values)
        self._update_combo_values()
        self._refresh_summary()

    def clear(self) -> None:
        self.set_values(None)

    def refresh_available_values(self) -> None:
        if self.delivery_method_service:
            self.available_values = [item["nome_meio"] for item in self.delivery_method_service.list_methods()]
        self._merge_available_values(self.selected_values)
        self._update_combo_values()
        self._refresh_summary()

    def add_selected(self, _event=None) -> None:
        selected = self._normalize_single_value(self.option_var.get())
        if not selected:
            messagebox.showwarning(self.dialog_title, "Selecione ou digite um meio de recebimento.", parent=self)
            return

        self._merge_available_values([selected])
        if not self._contains_value(self.selected_values, selected):
            self.selected_values.append(selected)

        self.option_var.set("")
        self._update_combo_values()
        self._refresh_summary()

    def remove_selected(self) -> None:
        selected = self._normalize_single_value(self.option_var.get())
        if not selected:
            messagebox.showwarning(
                self.dialog_title,
                "Selecione ou digite o meio que deseja remover da empresa.",
                parent=self,
            )
            return

        for index, item in enumerate(self.selected_values):
            if item.casefold() == selected.casefold():
                self.selected_values.pop(index)
                self.option_var.set("")
                self._refresh_summary()
                return

        messagebox.showwarning(
            self.dialog_title,
            "Esse meio nao esta marcado para a empresa atual.",
            parent=self,
        )

    def open_manager_dialog(self) -> None:
        if not self.delivery_method_service:
            messagebox.showwarning(
                self.dialog_title,
                "O gerenciamento global de meios nao esta disponivel nesta tela.",
                parent=self,
            )
            return

        dialog = DeliveryMethodsManagerDialog(self, self.delivery_method_service, self.dialog_title)
        self.wait_window(dialog)
        self.refresh_available_values()

    def _normalize_single_value(self, raw_value: str | None) -> str:
        values = parse_delivery_methods([raw_value or ""], known_options=self.available_values)
        return values[0] if values else ""

    def _merge_available_values(self, values: list[str]) -> None:
        for value in values:
            if not self._contains_value(self.available_values, value):
                self.available_values.append(value)

    def _contains_value(self, values: list[str], target: str) -> bool:
        return any(item.casefold() == target.casefold() for item in values)

    def _update_combo_values(self) -> None:
        self.combo["values"] = sorted(self.available_values, key=str.casefold)

    def _refresh_summary(self) -> None:
        if not self.selected_values:
            self.summary_var.set("Nenhum meio selecionado.")
            return
        self.summary_var.set(f'Selecionados: {", ".join(self.selected_values)}')

    def _on_resize(self, _event=None) -> None:
        wraplength = max(self.winfo_width() - 24, 180)
        self.hint_label.configure(wraplength=wraplength)
        self.summary_label.configure(wraplength=wraplength)
