from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from documentos_empresa_app.utils.common import MONTH_NAMES
from documentos_empresa_app.utils.helpers import ValidationError


class LogTab(ttk.Frame):
    def __init__(self, master, services, on_data_changed) -> None:
        super().__init__(master, padding=12)
        self.services = services
        self.on_data_changed = on_data_changed
        self.company_var = tk.StringVar()
        self.year_var = tk.StringVar()
        self.month_var = tk.StringVar()
        self.company_map: dict[str, int] = {}
        self._build_layout()

    def _build_layout(self) -> None:
        filter_frame = ttk.LabelFrame(self, text="Filtros", padding=10)
        filter_frame.pack(fill="x", pady=(0, 8))

        ttk.Label(filter_frame, text="Empresa").grid(row=0, column=0, sticky="w")
        self.company_combo = ttk.Combobox(filter_frame, textvariable=self.company_var, state="readonly")
        self.company_combo.grid(row=1, column=0, sticky="ew", padx=(0, 10))

        ttk.Label(filter_frame, text="Ano").grid(row=0, column=1, sticky="w")
        self.year_combo = ttk.Combobox(filter_frame, textvariable=self.year_var, state="readonly", width=14)
        self.year_combo.grid(row=1, column=1, sticky="w", padx=(0, 10))
        self.year_combo.bind("<<ComboboxSelected>>", lambda _event: self._sync_month_values())

        ttk.Label(filter_frame, text="Mes").grid(row=0, column=2, sticky="w")
        self.month_combo = ttk.Combobox(filter_frame, textvariable=self.month_var, state="readonly", width=20)
        self.month_combo.grid(row=1, column=2, sticky="w", padx=(0, 10))

        ttk.Button(filter_frame, text="Aplicar filtros", command=self.refresh_data).grid(
            row=1, column=3, sticky="w", padx=(0, 8)
        )
        ttk.Button(filter_frame, text="Limpar filtros", command=self.clear_filters).grid(row=1, column=4, sticky="w")

        filter_frame.columnconfigure(0, weight=1)

        self.info_label = ttk.Label(
            self,
            text="Logs mais recentes do sistema, do mais novo para o mais antigo.",
            foreground="#4F4F4F",
        )
        self.info_label.pack(fill="x", pady=(0, 8))

        list_frame = ttk.LabelFrame(self, text="Logs", padding=10)
        list_frame.pack(fill="both", expand=True)

        self.tree = ttk.Treeview(
            list_frame,
            columns=("data_hora", "usuario", "acao", "empresa", "periodo", "descricao"),
            show="headings",
        )
        self.tree.heading("data_hora", text="Data/Hora")
        self.tree.heading("usuario", text="Usuario")
        self.tree.heading("acao", text="Acao")
        self.tree.heading("empresa", text="Empresa")
        self.tree.heading("periodo", text="Periodo")
        self.tree.heading("descricao", text="Descricao")
        self.tree.column("data_hora", width=160, anchor="center")
        self.tree.column("usuario", width=140, anchor="center")
        self.tree.column("acao", width=180, anchor="center")
        self.tree.column("empresa", width=220)
        self.tree.column("periodo", width=110, anchor="center")
        self.tree.column("descricao", width=620)
        self.tree.pack(side="left", fill="both", expand=True)

        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.tree.yview)
        scrollbar.pack(side="right", fill="y")
        self.tree.configure(yscrollcommand=scrollbar.set)

    def refresh_data(self) -> None:
        self._refresh_filter_options()
        self.tree.delete(*self.tree.get_children())
        try:
            logs = self.services.log_service.list_logs(
                limit=500,
                empresa_id=self.company_map.get(self.company_var.get()),
                periodo_ano=int(self.year_var.get()) if self.year_var.get() else None,
                periodo_mes=int(self.month_var.get().split(" - ", 1)[0]) if self.month_var.get() else None,
            )
        except ValidationError as exc:
            messagebox.showerror("Logs", str(exc), parent=self)
            return

        if not logs:
            self.info_label.configure(text="Nenhum log encontrado para os filtros informados.")
        else:
            self.info_label.configure(text=f"{len(logs)} log(s) encontrados.")

        for log in logs:
            empresa_nome = log["empresa_nome"] or "-"
            periodo = "-"
            if log["periodo_ano"] and log["periodo_mes"]:
                periodo = f'{int(log["periodo_mes"]):02d}/{int(log["periodo_ano"])}'
            self.tree.insert(
                "",
                "end",
                iid=str(log["id"]),
                values=(
                    log["data_hora"],
                    log["username"],
                    log["acao"],
                    empresa_nome,
                    periodo,
                    log["descricao"],
                ),
            )

    def clear_filters(self) -> None:
        self.company_var.set("")
        self.year_var.set("")
        self.month_var.set("")
        self._sync_month_values()
        self.refresh_data()

    def _refresh_filter_options(self) -> None:
        selected_company = self.company_var.get()
        selected_year = self.year_var.get()
        selected_month = self.month_var.get()

        companies = self.services.log_service.list_logged_companies()
        company_labels = [""]
        self.company_map = {}
        name_counts: dict[str, int] = {}
        for company in companies:
            base_name = company["nome_empresa"] or "Empresa removida"
            name_counts[base_name] = name_counts.get(base_name, 0) + 1
        for company in companies:
            base_name = company["nome_empresa"] or "Empresa removida"
            if company["id"] is None:
                continue
            label = base_name if name_counts[base_name] == 1 else f"{base_name} (ID {company['id']})"
            self.company_map[label] = company["id"]
            company_labels.append(label)
        self.company_combo["values"] = company_labels
        if selected_company in company_labels:
            self.company_var.set(selected_company)
        else:
            self.company_var.set("")

        years = [str(year) for year in self.services.log_service.list_log_years()]
        self.year_combo["values"] = ["", *years]
        if selected_year in self.year_combo["values"]:
            self.year_var.set(selected_year)
        else:
            self.year_var.set("")

        self._sync_month_values()
        if selected_month in self.month_combo["values"]:
            self.month_var.set(selected_month)

    def _sync_month_values(self) -> None:
        if not self.year_var.get():
            self.month_combo["values"] = [""]
            self.month_var.set("")
            return

        try:
            year_int = int(self.year_var.get())
        except ValueError:
            self.month_combo["values"] = [""]
            self.month_var.set("")
            return

        months = self.services.log_service.list_log_months_by_year(year_int)
        month_labels = ["", *[f"{month:02d} - {MONTH_NAMES[month]}" for month in months]]
        self.month_combo["values"] = month_labels
        if self.month_var.get() not in month_labels:
            self.month_var.set("")
