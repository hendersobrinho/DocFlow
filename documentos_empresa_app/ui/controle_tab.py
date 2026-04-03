from __future__ import annotations

from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from documentos_empresa_app.utils.helpers import (
    CompanySelector,
    MONTH_NAMES,
    STATUS_COLORS,
    STATUS_OPTIONS,
    ScrollableFrame,
    ValidationError,
)


class ControleTab(ttk.Frame):
    def __init__(self, master, services, on_data_changed) -> None:
        super().__init__(master, padding=12)
        self.services = services
        self.on_data_changed = on_data_changed
        self.period_map_by_year_month: dict[tuple[int, int], int] = {}
        self.periods_by_year: dict[int, list[dict]] = {}
        self.current_filters: dict | None = None
        self.collapsed_groups: dict[str, bool] = {}
        self.status_vars: list[tk.StringVar] = []
        self.default_message_text = "Selecione a empresa e o intervalo para consultar."

        self.start_year_var = tk.StringVar()
        self.start_month_var = tk.StringVar()
        self.end_year_var = tk.StringVar()
        self.end_month_var = tk.StringVar()
        self.message_var = tk.StringVar(value=self.default_message_text)

        self._build_layout()

    def _build_layout(self) -> None:
        top = ttk.Frame(self)
        top.pack(fill="x", pady=(0, 10))

        self.company_selector = CompanySelector(
            top,
            self.services.empresa_service,
            active_only=True,
            on_selected=self.on_company_selected,
            on_cleared=self._clear_company_directory_context,
        )
        self.company_selector.pack(fill="x", pady=(0, 10))

        period_frame = ttk.LabelFrame(top, text="Periodo da consulta", padding=12)
        period_frame.pack(fill="x")

        ttk.Label(period_frame, text="Ano inicial").grid(row=0, column=0, sticky="w")
        self.start_year_combo = ttk.Combobox(period_frame, textvariable=self.start_year_var, state="readonly", width=16)
        self.start_year_combo.grid(row=1, column=0, sticky="w", padx=(0, 10))
        self.start_year_combo.bind("<<ComboboxSelected>>", lambda _event: self._on_year_changed("start"))

        ttk.Label(period_frame, text="Mes inicial").grid(row=0, column=1, sticky="w")
        self.start_month_combo = ttk.Combobox(period_frame, textvariable=self.start_month_var, state="readonly", width=20)
        self.start_month_combo.grid(row=1, column=1, sticky="w", padx=(0, 10))

        ttk.Label(period_frame, text="Mes final").grid(row=0, column=2, sticky="w")
        self.end_month_combo = ttk.Combobox(period_frame, textvariable=self.end_month_var, state="readonly", width=20)
        self.end_month_combo.grid(row=1, column=2, sticky="w", padx=(0, 10))

        ttk.Label(period_frame, text="Ano final (opcional)").grid(row=0, column=3, sticky="w")
        self.end_year_combo = ttk.Combobox(period_frame, textvariable=self.end_year_var, state="readonly", width=16)
        self.end_year_combo.grid(row=1, column=3, sticky="w", padx=(0, 10))
        self.end_year_combo.bind("<<ComboboxSelected>>", lambda _event: self._on_year_changed("end"))

        ttk.Button(period_frame, text="Consultar", command=self.consult).grid(row=1, column=4, sticky="w", padx=(0, 8))
        ttk.Button(period_frame, text="Limpar filtros", command=self.clear_filters).grid(row=1, column=5, sticky="w")
        self.directory_button = ttk.Button(
            period_frame,
            text="Abrir pasta...",
            command=self.open_company_directory_browser,
        )
        self.directory_button.grid(row=1, column=6, sticky="w", padx=(8, 0))
        ttk.Label(period_frame, text="Limite maximo de 12 meses por consulta.").grid(
            row=2, column=0, columnspan=7, sticky="w", pady=(8, 0)
        )

        legend = ttk.Frame(self)
        legend.pack(fill="x", pady=(0, 10))
        ttk.Label(legend, text="Legenda:").pack(side="left")
        self._legend_chip(legend, "Recebido").pack(side="left", padx=(8, 4))
        self._legend_chip(legend, "Pendente").pack(side="left", padx=4)
        self._legend_chip(legend, "Encerrado").pack(side="left", padx=4)

        ttk.Label(self, textvariable=self.message_var).pack(fill="x", pady=(0, 8))

        result_frame = ttk.LabelFrame(self, text="Consulta e controle mensal", padding=10)
        result_frame.pack(fill="both", expand=True)
        self.scrollable = ScrollableFrame(result_frame)
        self.scrollable.pack(fill="both", expand=True)
        self._set_directory_actions_enabled(False)

    def _legend_chip(self, master, text: str):
        chip = tk.Label(master, text=f" {text} ", bg=STATUS_COLORS[text], relief="solid", bd=1)
        return chip

    def refresh_data(self) -> None:
        self.company_selector.refresh_companies()
        self._set_directory_actions_enabled(bool(self.company_selector.get_selected_company_id()))
        self._load_period_options()
        if self.current_filters:
            company_id = self.current_filters.get("company_id")
            start_period_id = self.current_filters.get("start_period_id")
            end_period_id = self.current_filters.get("end_period_id")
            if company_id and start_period_id and end_period_id:
                try:
                    self.company_selector.set_company(company_id)
                    self._set_period_filter_values(start_period_id, end_period_id)
                except ValidationError:
                    self.current_filters = None
                    self._set_default_message("Selecione a empresa e o intervalo para consultar.")
                    self._clear_result_area()
        else:
            self._clear_invalid_selections()

    def on_company_selected(self, company: dict) -> None:
        _ = company
        self._set_directory_actions_enabled(True)

    def _clear_company_directory_context(self) -> None:
        self._set_directory_actions_enabled(False)

    def _set_directory_actions_enabled(self, enabled: bool) -> None:
        self.directory_button.configure(state="normal" if enabled else "disabled")

    def _get_selected_company(self) -> dict | None:
        company_id = self.company_selector.get_selected_company_id()
        if not company_id:
            return None
        return self.services.empresa_service.get_empresa(company_id)

    def open_company_directory_browser(self) -> None:
        company = self._get_selected_company()
        if not company:
            messagebox.showwarning("Controle", "Selecione uma empresa antes de vincular uma pasta.", parent=self)
            return

        current_directory = str(company.get("diretorio_documentos") or "").strip()
        initial_directory = (
            current_directory if current_directory and Path(current_directory).is_dir() else str(Path.home())
        )
        selected_directory = filedialog.askdirectory(
            parent=self,
            title=f'Escolha a pasta para "{company["nome_empresa"]}"',
            initialdir=initial_directory,
            mustexist=True,
        )
        if not selected_directory:
            return

        self.services.empresa_service.set_empresa_directory(company["id"], selected_directory)

    def _load_period_options(self) -> None:
        periodos = self.services.periodo_service.list_periodos()
        self.periods_by_year = {}
        self.period_map_by_year_month = {}

        for periodo in periodos:
            self.periods_by_year.setdefault(periodo["ano"], []).append(periodo)
            self.period_map_by_year_month[(periodo["ano"], periodo["mes"])] = periodo["id"]

        for items in self.periods_by_year.values():
            items.sort(key=lambda item: item["mes"])

        year_values = [str(year) for year in sorted(self.periods_by_year)]
        self.start_year_combo["values"] = year_values
        self.end_year_combo["values"] = year_values

        self._sync_month_values("start")
        self._sync_month_values("end")

    def _set_period_filter_values(self, start_period_id: int, end_period_id: int) -> None:
        start_period = self.services.periodo_service.get_periodo(start_period_id)
        end_period = self.services.periodo_service.get_periodo(end_period_id)

        self.start_year_var.set(str(start_period["ano"]))
        self.end_year_var.set(str(end_period["ano"]))
        self._sync_month_values("start")
        self._sync_month_values("end")
        self.start_month_var.set(self._month_label(start_period["mes"]))
        self.end_month_var.set(self._month_label(end_period["mes"]))

    def _clear_invalid_selections(self) -> None:
        valid_years = set(self.start_year_combo["values"])
        if self.start_year_var.get() not in valid_years:
            self.start_year_var.set("")
        if self.end_year_var.get() not in valid_years:
            self.end_year_var.set("")
        self._sync_month_values("start")
        self._sync_month_values("end")

    def _on_year_changed(self, side: str) -> None:
        if side == "start" and self.start_year_var.get() and not self.end_year_var.get():
            self.end_year_var.set(self.start_year_var.get())
        if side == "end" and self.end_year_var.get() and not self.start_year_var.get():
            self.start_year_var.set(self.end_year_var.get())

        self._sync_month_values("start")
        self._sync_month_values("end")

    def _sync_month_values(self, side: str) -> None:
        year_var = self.start_year_var if side == "start" else self.end_year_var
        month_var = self.start_month_var if side == "start" else self.end_month_var
        month_combo = self.start_month_combo if side == "start" else self.end_month_combo

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

    def _label_for_period(self, period_id: int) -> str:
        periodo = self.services.periodo_service.get_periodo(period_id)
        return periodo["label"]

    def _month_label(self, month: int) -> str:
        return f"{month:02d} - {MONTH_NAMES[month]}"

    def _parse_selected_period_ids(self) -> tuple[int, int] | None:
        start_year = self.start_year_var.get().strip()
        end_year = self.end_year_var.get().strip()

        if start_year and not end_year:
            end_year = start_year
            self.end_year_var.set(end_year)
            self._sync_month_values("end")
        elif end_year and not start_year:
            start_year = end_year
            self.start_year_var.set(start_year)
            self._sync_month_values("start")

        if not start_year or not end_year:
            messagebox.showwarning("Controle", "Selecione pelo menos um ano para a consulta.", parent=self)
            return None
        if not self.start_month_var.get() or not self.end_month_var.get():
            messagebox.showwarning("Controle", "Selecione os meses inicial e final.", parent=self)
            return None

        start_year_int = int(start_year)
        end_year_int = int(end_year)
        start_month_int = int(self.start_month_var.get().split(" - ", 1)[0])
        end_month_int = int(self.end_month_var.get().split(" - ", 1)[0])

        start_period_id = self.period_map_by_year_month.get((start_year_int, start_month_int))
        end_period_id = self.period_map_by_year_month.get((end_year_int, end_month_int))
        if not start_period_id or not end_period_id:
            messagebox.showwarning(
                "Controle",
                "Nao foi possivel localizar os periodos escolhidos. Verifique os anos e meses selecionados.",
                parent=self,
            )
            return None
        return start_period_id, end_period_id

    def clear_filters(self) -> None:
        self.current_filters = None
        self.company_selector.clear_selection()
        self.start_year_var.set("")
        self.start_month_var.set("")
        self.end_year_var.set("")
        self.end_month_var.set("")
        self._sync_month_values("start")
        self._sync_month_values("end")
        self._set_default_message("Selecione a empresa e o intervalo para consultar.")
        self._clear_result_area()

    def consult(
        self,
        *,
        preserve_scroll: bool = False,
        scroll_position: float | None = None,
    ) -> None:
        company_id = self.company_selector.get_selected_company_id()
        if not company_id:
            messagebox.showwarning("Controle", "Selecione uma empresa ativa para consultar.", parent=self)
            return

        period_ids = self._parse_selected_period_ids()
        if not period_ids:
            return
        start_period_id, end_period_id = period_ids

        try:
            view = self.services.status_service.build_control_view(company_id, start_period_id, end_period_id)
        except ValidationError as exc:
            messagebox.showerror("Controle", str(exc), parent=self)
            return

        if preserve_scroll and scroll_position is None:
            scroll_position = self._get_scroll_position()

        self.current_filters = {
            "company_id": company_id,
            "start_period_id": start_period_id,
            "end_period_id": end_period_id,
        }
        self.render_result(view, scroll_position=scroll_position)

    def render_result(self, view: dict, scroll_position: float | None = None) -> None:
        self._clear_result_area()
        self.status_vars = []

        periodos = view["periodos"]
        groups = view["groups"]
        if not groups:
            self._set_default_message("Nenhum documento encontrado para a empresa e periodo informados.")
            ttk.Label(self.scrollable.inner, text="Nenhum documento encontrado para a consulta.").grid(
                row=0, column=0, sticky="w", padx=6, pady=6
            )
            self._restore_scroll_position(scroll_position)
            return

        self._set_default_message(
            f'Empresa consultada: {view["empresa"]["nome_empresa"]}. Clique nos grupos para expandir ou recolher.'
        )

        header_bg = "#1F4E79"
        doc_header = tk.Label(
            self.scrollable.inner,
            text="Documento",
            bg=header_bg,
            fg="white",
            relief="solid",
            bd=1,
            padx=8,
            pady=8,
        )
        doc_header.grid(row=0, column=0, sticky="nsew")

        for column_index, periodo in enumerate(periodos, start=1):
            header = tk.Label(
                self.scrollable.inner,
                text=f'{periodo["mes"]:02d}/{periodo["ano"]}\n{MONTH_NAMES[periodo["mes"]]}',
                bg=header_bg,
                fg="white",
                relief="solid",
                bd=1,
                padx=8,
                pady=8,
                justify="center",
            )
            header.grid(row=0, column=column_index, sticky="nsew", padx=1, pady=1)

        row_index = 1
        for group in groups:
            tipo_nome = group["tipo_nome"]
            is_collapsed = self.collapsed_groups.get(tipo_nome, False)

            header_frame = tk.Frame(self.scrollable.inner, bg="#DCE6F1", bd=1, relief="solid")
            header_frame.grid(row=row_index, column=0, columnspan=len(periodos) + 1, sticky="ew", pady=(6, 0))
            toggle = ttk.Button(
                header_frame,
                text="+" if is_collapsed else "-",
                width=3,
                command=lambda name=tipo_nome: self.toggle_group(name),
            )
            toggle.pack(side="left", padx=6, pady=6)
            tk.Label(
                header_frame,
                text=tipo_nome,
                bg="#DCE6F1",
                font=("TkDefaultFont", 10, "bold"),
            ).pack(side="left", padx=(0, 10))
            tk.Label(
                header_frame,
                text=f'{len(group["documentos"])} documento(s)',
                bg="#DCE6F1",
                fg="#404040",
            ).pack(side="left")
            row_index += 1

            if is_collapsed:
                continue

            for document in group["documentos"]:
                name_label = tk.Label(
                    self.scrollable.inner,
                    text=document["nome_documento"],
                    anchor="w",
                    relief="solid",
                    bd=1,
                    bg="#FFFFFF",
                    padx=8,
                    pady=6,
                )
                name_label.grid(row=row_index, column=0, sticky="nsew", padx=1, pady=1)

                for column_index, cell in enumerate(document["cells"], start=1):
                    if cell["available"]:
                        self._create_status_cell(
                            row_index,
                            column_index,
                            document["id"],
                            cell["periodo_id"],
                            document["nome_documento"],
                            f'{periodos[column_index - 1]["mes"]:02d}/{periodos[column_index - 1]["ano"]}',
                            cell["status"],
                            cell.get("updated_by_username"),
                            cell.get("updated_at"),
                        )
                    else:
                        inactive = tk.Label(
                            self.scrollable.inner,
                            text="",
                            relief="solid",
                            bd=1,
                            bg="#F3F3F3",
                            padx=8,
                            pady=10,
                        )
                        inactive.grid(row=row_index, column=column_index, sticky="nsew", padx=1, pady=1)
                row_index += 1

        for column_index in range(len(periodos) + 1):
            self.scrollable.inner.grid_columnconfigure(column_index, weight=1 if column_index else 2)

        self._restore_scroll_position(scroll_position)

    def _create_status_cell(
        self,
        row_index: int,
        column_index: int,
        document_id: int,
        period_id: int,
        document_name: str,
        period_label: str,
        current_status: str,
        updated_by_username: str | None,
        updated_at: str | None,
    ) -> None:
        color = STATUS_COLORS.get(current_status, STATUS_COLORS[""])
        cell_frame = tk.Frame(self.scrollable.inner, bg=color, relief="solid", bd=1)
        cell_frame.grid(row=row_index, column=column_index, sticky="nsew", padx=1, pady=1)

        variable = tk.StringVar(value=current_status)
        self.status_vars.append(variable)
        option = tk.OptionMenu(
            cell_frame,
            variable,
            *STATUS_OPTIONS,
            command=lambda value, doc_id=document_id, per_id=period_id: self.update_status(doc_id, per_id, value),
        )
        option.configure(
            width=11,
            bg=color,
            highlightthickness=0,
            relief="flat",
            activebackground=color,
        )
        option["menu"].configure(tearoff=0)
        option.pack(fill="both", expand=True)

        for widget in (cell_frame, option):
            widget.bind(
                "<Enter>",
                lambda _event, doc_name=document_name, per_label=period_label, cell_status=current_status,
                actor=updated_by_username, timestamp=updated_at: self._show_status_metadata(
                    doc_name,
                    per_label,
                    cell_status,
                    actor,
                    timestamp,
                ),
            )
            widget.bind("<Leave>", self._restore_default_message)

    def update_status(self, document_id: int, period_id: int, status: str) -> None:
        scroll_position = self._get_scroll_position()
        try:
            self.services.status_service.update_status(document_id, period_id, status)
        except ValidationError as exc:
            self.consult(scroll_position=scroll_position)
            messagebox.showerror("Controle", str(exc), parent=self)
            return
        self.on_data_changed()
        self.consult(scroll_position=scroll_position)

    def toggle_group(self, group_name: str) -> None:
        self.collapsed_groups[group_name] = not self.collapsed_groups.get(group_name, False)
        if self.current_filters:
            self.consult(preserve_scroll=True)

    def _clear_result_area(self) -> None:
        for child in self.scrollable.inner.winfo_children():
            child.destroy()

    def _get_scroll_position(self) -> float:
        yview = self.scrollable.canvas.yview()
        if not yview:
            return 0.0
        return yview[0]

    def _restore_scroll_position(self, scroll_position: float | None) -> None:
        if scroll_position is None:
            return

        clamped_position = min(max(scroll_position, 0.0), 1.0)

        def _apply() -> None:
            if self.winfo_exists():
                self.scrollable.canvas.yview_moveto(clamped_position)

        self.after_idle(_apply)

    def _show_status_metadata(
        self,
        document_name: str,
        period_label: str,
        status: str,
        updated_by_username: str | None,
        updated_at: str | None,
    ) -> None:
        if updated_at:
            actor = updated_by_username or "Sistema"
            self.message_var.set(
                (
                    f'Documento "{document_name}" em {period_label}: '
                    f'status "{status or "vazio"}", alterado por {actor} em {self._format_timestamp(updated_at)}.'
                )
            )
            return
        self.message_var.set(
            f'Documento "{document_name}" em {period_label}: nenhuma alteracao registrada ainda.'
        )

    def _restore_default_message(self, _event=None) -> None:
        self.message_var.set(self.default_message_text)

    def _set_default_message(self, text: str) -> None:
        self.default_message_text = text
        self.message_var.set(text)

    def _format_timestamp(self, raw_value: str) -> str:
        try:
            return datetime.strptime(raw_value, "%Y-%m-%d %H:%M:%S").strftime("%d/%m/%Y %H:%M")
        except ValueError:
            return raw_value
