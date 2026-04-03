from __future__ import annotations

from collections import Counter
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from documentos_empresa_app.utils.helpers import CompanyMultiSelectDialog, MONTH_NAMES, ValidationError


class PeriodoTab(ttk.Frame):
    def __init__(self, master, services, on_data_changed) -> None:
        super().__init__(master, padding=12)
        self.services = services
        self.on_data_changed = on_data_changed

        self.ano_var = tk.StringVar()
        self.delete_year_var = tk.StringVar()
        self.report_start_year_var = tk.StringVar()
        self.report_start_month_var = tk.StringVar()
        self.report_end_year_var = tk.StringVar()
        self.report_end_month_var = tk.StringVar()
        self.report_company_summary_var = tk.StringVar(value="Todas as empresas")
        self.report_all_companies_var = tk.BooleanVar(value=True)
        self.selected_report_company_ids: list[int] = []
        self.periods_by_year: dict[int, list[dict]] = {}
        self.period_map_by_year_month: dict[tuple[int, int], int] = {}

        self._build_layout()

    def _build_layout(self) -> None:
        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True)

        generate_frame = ttk.Frame(notebook, padding=12)
        delete_frame = ttk.Frame(notebook, padding=12)
        report_frame = ttk.Frame(notebook, padding=12)
        notebook.add(generate_frame, text="Gerar periodos")
        notebook.add(delete_frame, text="Excluir ano")
        notebook.add(report_frame, text="Relatorio de pendencias")

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

        report_box = ttk.LabelFrame(report_frame, text="Exportacao de pendencias", padding=12)
        report_box.pack(fill="x")
        report_box.columnconfigure(1, weight=1)

        ttk.Checkbutton(
            report_box,
            text="Todas as empresas",
            variable=self.report_all_companies_var,
            command=self._toggle_report_company_mode,
        ).grid(row=0, column=0, sticky="w")
        self.report_company_button = ttk.Button(
            report_box,
            text="Selecionar empresas...",
            command=self.select_report_companies,
        )
        self.report_company_button.grid(row=0, column=1, sticky="w", padx=(12, 0))

        ttk.Label(report_box, textvariable=self.report_company_summary_var, wraplength=760).grid(
            row=1, column=0, columnspan=4, sticky="w", pady=(8, 12)
        )

        ttk.Label(report_box, text="Ano inicial").grid(row=2, column=0, sticky="w")
        self.report_start_year_combo = ttk.Combobox(
            report_box,
            textvariable=self.report_start_year_var,
            state="readonly",
            width=16,
        )
        self.report_start_year_combo.grid(row=3, column=0, sticky="w", padx=(0, 10))
        self.report_start_year_combo.bind("<<ComboboxSelected>>", lambda _event: self._on_report_year_changed("start"))

        ttk.Label(report_box, text="Mes inicial").grid(row=2, column=1, sticky="w")
        self.report_start_month_combo = ttk.Combobox(
            report_box,
            textvariable=self.report_start_month_var,
            state="readonly",
            width=20,
        )
        self.report_start_month_combo.grid(row=3, column=1, sticky="w", padx=(0, 10))

        ttk.Label(report_box, text="Mes final").grid(row=2, column=2, sticky="w")
        self.report_end_month_combo = ttk.Combobox(
            report_box,
            textvariable=self.report_end_month_var,
            state="readonly",
            width=20,
        )
        self.report_end_month_combo.grid(row=3, column=2, sticky="w", padx=(0, 10))

        ttk.Label(report_box, text="Ano final").grid(row=2, column=3, sticky="w")
        self.report_end_year_combo = ttk.Combobox(
            report_box,
            textvariable=self.report_end_year_var,
            state="readonly",
            width=16,
        )
        self.report_end_year_combo.grid(row=3, column=3, sticky="w")
        self.report_end_year_combo.bind("<<ComboboxSelected>>", lambda _event: self._on_report_year_changed("end"))

        ttk.Button(report_box, text="Exportar Excel", command=self.export_pending_report).grid(
            row=4,
            column=0,
            sticky="w",
            pady=(12, 0),
        )
        ttk.Label(
            report_box,
            text="O relatorio considera apenas os documentos com status Pendente no periodo selecionado.",
            wraplength=760,
        ).grid(row=5, column=0, columnspan=4, sticky="w", pady=(8, 0))

        self._toggle_report_company_mode()

    def refresh_data(self) -> None:
        periodos = self.services.periodo_service.list_periodos()
        self.periods_by_year = {}
        self.period_map_by_year_month = {}
        counts = Counter(periodo["ano"] for periodo in periodos)

        for periodo in periodos:
            self.periods_by_year.setdefault(periodo["ano"], []).append(periodo)
            self.period_map_by_year_month[(periodo["ano"], periodo["mes"])] = periodo["id"]

        for items in self.periods_by_year.values():
            items.sort(key=lambda item: item["mes"])

        self.year_tree.delete(*self.year_tree.get_children())
        for ano in sorted(counts):
            self.year_tree.insert("", "end", iid=str(ano), values=(ano, counts[ano]))

        year_values = [str(year) for year in self.services.periodo_service.list_available_years()]
        self.delete_combo["values"] = year_values
        if self.delete_year_var.get() not in year_values:
            self.delete_year_var.set("")

        self.report_start_year_combo["values"] = year_values
        self.report_end_year_combo["values"] = year_values
        self._sync_report_month_values("start")
        self._sync_report_month_values("end")
        self._refresh_report_company_summary()

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

    def _toggle_report_company_mode(self) -> None:
        use_all = self.report_all_companies_var.get()
        self.report_company_button.configure(state="disabled" if use_all else "normal")
        self._refresh_report_company_summary()

    def _refresh_report_company_summary(self) -> None:
        if self.report_all_companies_var.get():
            self.report_company_summary_var.set("Todas as empresas ativas e inativas serao consideradas.")
            return

        companies = self.services.empresa_service.list_empresas(active_only=False)
        available_by_id = {company["id"]: company for company in companies}
        self.selected_report_company_ids = [
            company_id for company_id in self.selected_report_company_ids if company_id in available_by_id
        ]
        if not self.selected_report_company_ids:
            self.report_company_summary_var.set("Nenhuma empresa selecionada.")
            return

        selected_companies = [available_by_id[company_id] for company_id in self.selected_report_company_ids]
        selected_companies.sort(key=lambda item: (item["codigo_empresa"], item["nome_empresa"].casefold()))
        if len(selected_companies) == 1:
            company = selected_companies[0]
            self.report_company_summary_var.set(f'Empresa selecionada: {company["codigo_empresa"]} - {company["nome_empresa"]}')
            return

        names = ", ".join(company["nome_empresa"] for company in selected_companies[:3])
        if len(selected_companies) > 3:
            names += f" e mais {len(selected_companies) - 3}"
        self.report_company_summary_var.set(f"{len(selected_companies)} empresas selecionadas: {names}.")

    def select_report_companies(self) -> None:
        companies = self.services.empresa_service.list_empresas(active_only=False)
        dialog = CompanyMultiSelectDialog(
            self,
            companies,
            selected_company_ids=self.selected_report_company_ids,
        )
        self.wait_window(dialog)
        self.selected_report_company_ids = dialog.selected_company_ids
        self._refresh_report_company_summary()

    def _on_report_year_changed(self, side: str) -> None:
        if side == "start" and self.report_start_year_var.get() and not self.report_end_year_var.get():
            self.report_end_year_var.set(self.report_start_year_var.get())
        if side == "end" and self.report_end_year_var.get() and not self.report_start_year_var.get():
            self.report_start_year_var.set(self.report_end_year_var.get())

        self._sync_report_month_values("start")
        self._sync_report_month_values("end")

    def _sync_report_month_values(self, side: str) -> None:
        year_var = self.report_start_year_var if side == "start" else self.report_end_year_var
        month_var = self.report_start_month_var if side == "start" else self.report_end_month_var
        month_combo = self.report_start_month_combo if side == "start" else self.report_end_month_combo

        year_value = year_var.get().strip()
        if not year_value:
            month_combo["values"] = []
            month_var.set("")
            return

        try:
            year_int = int(year_value)
        except ValueError:
            month_combo["values"] = []
            month_var.set("")
            return

        months = [self._month_label(periodo["mes"]) for periodo in self.periods_by_year.get(year_int, [])]
        month_combo["values"] = months
        if month_var.get() not in months:
            month_var.set("")

    def _month_label(self, month: int) -> str:
        return f"{month:02d} - {MONTH_NAMES[month]}"

    def _parse_report_period_ids(self) -> tuple[int, int] | None:
        start_year = self.report_start_year_var.get().strip()
        end_year = self.report_end_year_var.get().strip()

        if start_year and not end_year:
            end_year = start_year
            self.report_end_year_var.set(end_year)
            self._sync_report_month_values("end")
        elif end_year and not start_year:
            start_year = end_year
            self.report_start_year_var.set(start_year)
            self._sync_report_month_values("start")

        if not start_year or not end_year:
            messagebox.showwarning("Relatorio", "Selecione pelo menos um ano para o relatorio.", parent=self)
            return None
        if not self.report_start_month_var.get() or not self.report_end_month_var.get():
            messagebox.showwarning("Relatorio", "Selecione os meses inicial e final.", parent=self)
            return None

        start_year_int = int(start_year)
        end_year_int = int(end_year)
        start_month_int = int(self.report_start_month_var.get().split(" - ", 1)[0])
        end_month_int = int(self.report_end_month_var.get().split(" - ", 1)[0])

        start_period_id = self.period_map_by_year_month.get((start_year_int, start_month_int))
        end_period_id = self.period_map_by_year_month.get((end_year_int, end_month_int))
        if not start_period_id or not end_period_id:
            messagebox.showwarning(
                "Relatorio",
                "Nao foi possivel localizar os periodos escolhidos. Verifique os anos e meses selecionados.",
                parent=self,
            )
            return None
        return start_period_id, end_period_id

    def export_pending_report(self) -> None:
        period_ids = self._parse_report_period_ids()
        if not period_ids:
            return

        company_ids: list[int] | None
        if self.report_all_companies_var.get():
            company_ids = None
        else:
            if not self.selected_report_company_ids:
                messagebox.showwarning("Relatorio", "Selecione pelo menos uma empresa.", parent=self)
                return
            company_ids = self.selected_report_company_ids

        file_path = filedialog.asksaveasfilename(
            parent=self,
            title="Salvar relatorio de pendencias",
            defaultextension=".xlsx",
            filetypes=[("Arquivos Excel", "*.xlsx"), ("Todos os arquivos", "*.*")],
            initialfile="relatorio_pendencias.xlsx",
        )
        if not file_path:
            return

        start_period_id, end_period_id = period_ids
        try:
            result = self.services.pending_report_service.export_pending_report(
                file_path,
                company_ids,
                start_period_id,
                end_period_id,
            )
        except ValidationError as exc:
            messagebox.showwarning("Relatorio", str(exc), parent=self)
            return

        messagebox.showinfo(
            "Relatorio",
            (
                f'Relatorio exportado com sucesso.\n'
                f'Empresas consideradas: {result["company_count"]}\n'
                f'Empresas com pendencias: {result["pending_company_count"]}\n'
                f'Linhas exportadas: {result["rows"]}'
            ),
            parent=self,
        )
