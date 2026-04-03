from __future__ import annotations

from collections import Counter
import tkinter as tk
from tkinter import messagebox, ttk

from documentos_empresa_app.utils.helpers import ValidationError


class PeriodoTab(ttk.Frame):
    def __init__(self, master, services, on_data_changed) -> None:
        super().__init__(master, padding=12)
        self.services = services
        self.on_data_changed = on_data_changed

        self.ano_var = tk.StringVar()
        self.delete_year_var = tk.StringVar()

        self._build_layout()

    def _build_layout(self) -> None:
        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True)

        generate_frame = ttk.Frame(notebook, padding=12)
        delete_frame = ttk.Frame(notebook, padding=12)
        notebook.add(generate_frame, text="Gerar periodos")
        notebook.add(delete_frame, text="Excluir ano")

        generate_box = ttk.LabelFrame(generate_frame, text="Geracao de meses por ano", padding=12)
        generate_box.pack(fill="x", pady=(0, 12))
        ttk.Label(generate_box, text="Ano").grid(row=0, column=0, sticky="w")
        ttk.Entry(generate_box, textvariable=self.ano_var, width=18).grid(row=1, column=0, sticky="w", padx=(0, 10))
        ttk.Button(generate_box, text="Gerar 12 meses", command=self.generate_year).grid(row=1, column=1, sticky="w")

        list_box = ttk.LabelFrame(generate_frame, text="Anos existentes", padding=10)
        list_box.pack(fill="both", expand=True)
        self.year_tree = ttk.Treeview(list_box, columns=("ano", "meses"), show="headings", selectmode="browse")
        self.year_tree.heading("ano", text="Ano")
        self.year_tree.heading("meses", text="Meses cadastrados")
        self.year_tree.column("ano", width=150, anchor="center")
        self.year_tree.column("meses", width=180, anchor="center")
        self.year_tree.pack(side="left", fill="both", expand=True)
        scrollbar = ttk.Scrollbar(list_box, orient="vertical", command=self.year_tree.yview)
        scrollbar.pack(side="right", fill="y")
        self.year_tree.configure(yscrollcommand=scrollbar.set)

        delete_box = ttk.LabelFrame(delete_frame, text="Exclusao de um ano inteiro", padding=12)
        delete_box.pack(fill="x")
        ttk.Label(
            delete_box,
            text="Ao excluir um ano, apenas os periodos e status mensais daquele ano serao removidos.",
            wraplength=760,
        ).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 10))
        ttk.Label(delete_box, text="Ano existente").grid(row=1, column=0, sticky="w")
        self.delete_combo = ttk.Combobox(delete_box, textvariable=self.delete_year_var, state="readonly", width=20)
        self.delete_combo.grid(row=2, column=0, sticky="w", padx=(0, 10))
        ttk.Button(delete_box, text="Excluir ano selecionado", command=self.delete_year).grid(
            row=2, column=1, sticky="w"
        )

    def refresh_data(self) -> None:
        periodos = self.services.periodo_service.list_periodos()
        counts = Counter(periodo["ano"] for periodo in periodos)

        self.year_tree.delete(*self.year_tree.get_children())
        for ano in sorted(counts):
            self.year_tree.insert("", "end", iid=str(ano), values=(ano, counts[ano]))

        year_values = [str(year) for year in self.services.periodo_service.list_available_years()]
        self.delete_combo["values"] = year_values
        if self.delete_year_var.get() not in year_values:
            self.delete_year_var.set("")

    def generate_year(self) -> None:
        try:
            result = self.services.periodo_service.generate_year(self.ano_var.get())
        except ValidationError as exc:
            messagebox.showerror("Periodos", str(exc), parent=self)
            return
        self.on_data_changed()
        messagebox.showinfo(
            "Periodos",
            (
                f'Ano {result["ano"]} processado com sucesso.\n'
                f'Meses criados: {result["created"]}\n'
                f'Meses ja existentes: {result["existing"]}'
            ),
            parent=self,
        )

    def delete_year(self) -> None:
        year = self.delete_year_var.get().strip()
        if not year:
            messagebox.showwarning("Excluir ano", "Selecione um ano existente.", parent=self)
            return
        if not messagebox.askyesno(
            "Excluir ano",
            (
                "Todos os periodos e controles mensais desse ano serao apagados.\n"
                "Empresas, tipos e documentos base nao serao excluidos.\n\n"
                "Deseja continuar?"
            ),
            parent=self,
        ):
            return
        if not messagebox.askyesno(
            "Confirmacao final",
            f"Confirma a exclusao definitiva do ano {year}?",
            parent=self,
        ):
            return

        try:
            result = self.services.periodo_service.delete_year(year)
        except ValidationError as exc:
            messagebox.showerror("Excluir ano", str(exc), parent=self)
            return
        self.on_data_changed()
        messagebox.showinfo(
            "Excluir ano",
            f'{result["deleted"]} periodos do ano {result["ano"]} foram removidos.',
            parent=self,
        )

