from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from documentos_empresa_app.services.file_check_service import (
    DEFAULT_FILE_CHECK_OPTIONS,
    LAYOUT_AUTO,
    LAYOUT_DOCUMENT_FIRST,
    LAYOUT_MONTH_FIRST,
    LAYOUT_YEAR_DIRECT,
    MODE_CURRENT_ONLY,
    MODE_PENDING_HISTORY,
    PERIOD_SOURCE_FILENAME_ONLY,
    PERIOD_SOURCE_FILENAME_OR_FOLDER,
    RESULT_ALTA_CONFIANCA,
    RESULT_ERRO,
    RESULT_NAO_ENCONTRADO,
    RESULT_REVISAR,
    TEMPORAL_ATUAL,
    TEMPORAL_ANTERIOR_PENDENTE,
    TEMPORAL_ANTERIOR_RECEBIDA,
    TEMPORAL_FUTURA,
    FileCheckService,
)
from documentos_empresa_app.ui.styles import PALETTE
from documentos_empresa_app.utils.helpers import APP_NAME, load_config, save_config

_CONFIG_KEY = "file_check"

_LAYOUT_LABELS = {
    LAYOUT_AUTO: "Detectar automaticamente",
    LAYOUT_YEAR_DIRECT: "Arquivos dentro da pasta do ano",
    LAYOUT_MONTH_FIRST: "Pasta da competencia dentro do ano",
    LAYOUT_DOCUMENT_FIRST: "Pasta do documento, depois competencia",
}
_LAYOUT_BY_LABEL = {label: key for key, label in _LAYOUT_LABELS.items()}

_PERIOD_SOURCE_LABELS = {
    PERIOD_SOURCE_FILENAME_OR_FOLDER: "Nome do arquivo ou pasta da competencia",
    PERIOD_SOURCE_FILENAME_ONLY: "Somente mes/ano no nome do arquivo",
}
_PERIOD_SOURCE_BY_LABEL = {label: key for key, label in _PERIOD_SOURCE_LABELS.items()}

_RESULT_LABELS = {
    RESULT_ALTA_CONFIANCA: "Alta confianca",
    RESULT_REVISAR: "Revisar",
    RESULT_NAO_ENCONTRADO: "Nao encontrado",
    RESULT_ERRO: "Erro",
}

_RESULT_TAG_COLORS = {
    RESULT_ALTA_CONFIANCA: "#1A6B2A",
    RESULT_REVISAR: "#8A5200",
    RESULT_NAO_ENCONTRADO: PALETTE["disabled_fg"],
    RESULT_ERRO: PALETTE["danger"],
}

_TEMPORAL_LABELS = {
    TEMPORAL_ATUAL: "Atual",
    TEMPORAL_ANTERIOR_PENDENTE: "Anterior (pendente)",
    TEMPORAL_ANTERIOR_RECEBIDA: "Anterior (recebido)",
    TEMPORAL_FUTURA: "Futuro",
    "competencia_diferente": "Diferente",
    "competencia_nao_identificada": "Nao identificada",
}


def _load_settings() -> dict:
    raw = load_config().get(_CONFIG_KEY, {})
    defaults = DEFAULT_FILE_CHECK_OPTIONS
    return {
        "root_dir": raw.get("root_dir", "") or "",
        "mode": raw.get("mode", MODE_CURRENT_ONLY),
        "skip_received": bool(raw.get("skip_received", True)),
        "layout_mode": raw.get("layout_mode", defaults["layout_mode"]),
        "period_source": raw.get("period_source", defaults["period_source"]),
        "allow_generic_documents": bool(raw.get(
            "allow_generic_documents", defaults["allow_generic_documents"]
        )),
        "require_registered_terms": bool(raw.get(
            "require_registered_terms", defaults["require_registered_terms"]
        )),
        "bank_folder_aliases": raw.get(
            "bank_folder_aliases", defaults["bank_folder_aliases"]
        ),
        "cc_folder_aliases": raw.get(
            "cc_folder_aliases", defaults["cc_folder_aliases"]
        ),
        "aplicacao_folder_aliases": raw.get(
            "aplicacao_folder_aliases", defaults["aplicacao_folder_aliases"]
        ),
        "filename_templates": raw.get(
            "filename_templates", defaults["filename_templates"]
        ),
        "require_template_match": bool(raw.get(
            "require_template_match", defaults["require_template_match"]
        )),
        "required_filename_terms": raw.get(
            "required_filename_terms", defaults["required_filename_terms"]
        ),
        "forbidden_filename_terms": raw.get(
            "forbidden_filename_terms", defaults["forbidden_filename_terms"]
        ),
    }


def _save_settings(settings: dict) -> None:
    config = load_config()
    config[_CONFIG_KEY] = {
        "root_dir": settings.get("root_dir", "") or "",
        "mode": settings.get("mode", MODE_CURRENT_ONLY),
        "skip_received": bool(settings.get("skip_received", True)),
        "layout_mode": settings.get("layout_mode", DEFAULT_FILE_CHECK_OPTIONS["layout_mode"]),
        "period_source": settings.get("period_source", DEFAULT_FILE_CHECK_OPTIONS["period_source"]),
        "allow_generic_documents": bool(settings.get("allow_generic_documents", True)),
        "require_registered_terms": bool(settings.get("require_registered_terms", True)),
        "bank_folder_aliases": settings.get(
            "bank_folder_aliases", DEFAULT_FILE_CHECK_OPTIONS["bank_folder_aliases"]
        ),
        "cc_folder_aliases": settings.get(
            "cc_folder_aliases", DEFAULT_FILE_CHECK_OPTIONS["cc_folder_aliases"]
        ),
        "aplicacao_folder_aliases": settings.get(
            "aplicacao_folder_aliases", DEFAULT_FILE_CHECK_OPTIONS["aplicacao_folder_aliases"]
        ),
        "filename_templates": settings.get(
            "filename_templates", DEFAULT_FILE_CHECK_OPTIONS["filename_templates"]
        ),
        "require_template_match": bool(settings.get("require_template_match", False)),
        "required_filename_terms": settings.get(
            "required_filename_terms", DEFAULT_FILE_CHECK_OPTIONS["required_filename_terms"]
        ),
        "forbidden_filename_terms": settings.get(
            "forbidden_filename_terms", DEFAULT_FILE_CHECK_OPTIONS["forbidden_filename_terms"]
        ),
    }
    save_config(config)


def _fmt_period(period: tuple[int, int] | None) -> str:
    if not period:
        return "—"
    return f"{period[0]:02d}/{period[1]}"


class FileCheckDialog(tk.Toplevel):
    def __init__(
        self,
        parent: tk.Misc,
        services,
        *,
        periodo_id: int,
        visible_empresa_ids: list[int],
        on_changes_applied: object = None,
    ) -> None:
        super().__init__(parent)
        self.services = services
        self.periodo_id = periodo_id
        self.visible_empresa_ids = visible_empresa_ids
        self.on_changes_applied = on_changes_applied
        self._results: list[dict] = []

        periodo = services.periodo_service.get_periodo(periodo_id)
        self._ano: int = periodo["ano"]
        self._mes: int = periodo["mes"]
        self._periodo_label = f"{self._mes:02d}/{self._ano}"

        settings = _load_settings()
        self._root_dir_var = tk.StringVar(value=settings["root_dir"])
        self._scope_var = tk.StringVar(value="visible")
        self._mode_var = tk.StringVar(value=settings["mode"])
        self._skip_received_var = tk.BooleanVar(value=settings["skip_received"])
        self._show_problems_only_var = tk.BooleanVar(value=False)
        layout_label = _LAYOUT_LABELS.get(settings["layout_mode"], _LAYOUT_LABELS[LAYOUT_AUTO])
        period_source_label = _PERIOD_SOURCE_LABELS.get(
            settings["period_source"],
            _PERIOD_SOURCE_LABELS[PERIOD_SOURCE_FILENAME_OR_FOLDER],
        )
        self._layout_label_var = tk.StringVar(value=layout_label)
        self._period_source_label_var = tk.StringVar(value=period_source_label)
        self._allow_generic_documents_var = tk.BooleanVar(
            value=settings["allow_generic_documents"]
        )
        self._require_registered_terms_var = tk.BooleanVar(
            value=settings["require_registered_terms"]
        )
        self._bank_folder_aliases_var = tk.StringVar(value=settings["bank_folder_aliases"])
        self._cc_folder_aliases_var = tk.StringVar(value=settings["cc_folder_aliases"])
        self._aplicacao_folder_aliases_var = tk.StringVar(value=settings["aplicacao_folder_aliases"])
        self._filename_templates_var = tk.StringVar(value=settings["filename_templates"])
        self._require_template_match_var = tk.BooleanVar(
            value=settings["require_template_match"]
        )
        self._required_filename_terms_var = tk.StringVar(value=settings["required_filename_terms"])
        self._forbidden_filename_terms_var = tk.StringVar(value=settings["forbidden_filename_terms"])
        self._status_var = tk.StringVar(value="")
        self._log_metadata: dict = {}

        self.title(f"Verificar servidor — {self._periodo_label}")
        self.resizable(True, True)
        self.minsize(1120, 700)
        self._center(parent)
        self._build_layout()

    def _center(self, parent: tk.Misc) -> None:
        self.update_idletasks()
        pw = parent.winfo_toplevel()
        x = pw.winfo_rootx() + (pw.winfo_width() - 1120) // 2
        y = pw.winfo_rooty() + (pw.winfo_height() - 700) // 2
        self.geometry(f"1120x700+{max(x, 0)}+{max(y, 0)}")

    def _build_layout(self) -> None:
        outer = ttk.Frame(self, padding=14)
        outer.pack(fill="both", expand=True)

        # ── Header ────────────────────────────────────────────────────────────
        ttk.Label(
            outer, text=f"Conferencia de arquivos — competencia {self._periodo_label}",
            style="Header.TLabel",
        ).pack(anchor="w", pady=(0, 10))

        # ── Configuration ──────────────────────────────────────────────────────
        cfg_frame = ttk.LabelFrame(outer, text="Configuracao", padding=10)
        cfg_frame.pack(fill="x", pady=(0, 8))
        cfg_frame.columnconfigure(1, weight=1)

        ttk.Label(cfg_frame, text="Pasta raiz das empresas:").grid(
            row=0, column=0, sticky="w", padx=(0, 8)
        )
        ttk.Entry(cfg_frame, textvariable=self._root_dir_var).grid(
            row=0, column=1, sticky="ew", padx=(0, 6)
        )
        ttk.Button(
            cfg_frame, text="Selecionar...", command=self._browse_root, style="Secondary.TButton"
        ).grid(row=0, column=2)

        scope_frame = ttk.Frame(cfg_frame)
        scope_frame.grid(row=1, column=0, columnspan=3, sticky="w", pady=(10, 0))
        ttk.Label(scope_frame, text="Escopo:").pack(side="left", padx=(0, 10))
        ttk.Radiobutton(
            scope_frame,
            text=f"Apenas empresas visiveis ({len(self.visible_empresa_ids)})",
            variable=self._scope_var, value="visible",
        ).pack(side="left", padx=(0, 16))
        ttk.Radiobutton(
            scope_frame, text="Todas as empresas ativas",
            variable=self._scope_var, value="all",
        ).pack(side="left")

        mode_frame = ttk.Frame(cfg_frame)
        mode_frame.grid(row=2, column=0, columnspan=3, sticky="w", pady=(8, 0))
        ttk.Label(mode_frame, text="Modo:").pack(side="left", padx=(0, 10))
        ttk.Radiobutton(
            mode_frame, text="Somente competencia atual",
            variable=self._mode_var, value=MODE_CURRENT_ONLY,
        ).pack(side="left", padx=(0, 16))
        ttk.Radiobutton(
            mode_frame, text="Pendentes ate a competencia",
            variable=self._mode_var, value=MODE_PENDING_HISTORY,
        ).pack(side="left", padx=(0, 20))
        ttk.Checkbutton(
            mode_frame, text="Ignorar ja recebidos",
            variable=self._skip_received_var,
        ).pack(side="left")
        ttk.Checkbutton(
            mode_frame, text="Somente problemas",
            variable=self._show_problems_only_var,
            command=self._refilter_results,
        ).pack(side="left", padx=(16, 0))

        # ── Custom rules ─────────────────────────────────────────────────────
        rules_frame = ttk.LabelFrame(outer, text="Regras personalizadas de procura", padding=10)
        rules_frame.pack(fill="x", pady=(0, 8))
        rules_frame.columnconfigure(1, weight=1)
        rules_frame.columnconfigure(3, weight=1)

        ttk.Label(rules_frame, text="Estrutura das pastas:").grid(
            row=0, column=0, sticky="w", padx=(0, 8)
        )
        ttk.Combobox(
            rules_frame,
            textvariable=self._layout_label_var,
            state="readonly",
            values=tuple(_LAYOUT_BY_LABEL.keys()),
        ).grid(row=0, column=1, sticky="ew", padx=(0, 14))

        ttk.Label(rules_frame, text="Competencia vem de:").grid(
            row=0, column=2, sticky="w", padx=(0, 8)
        )
        ttk.Combobox(
            rules_frame,
            textvariable=self._period_source_label_var,
            state="readonly",
            values=tuple(_PERIOD_SOURCE_BY_LABEL.keys()),
        ).grid(row=0, column=3, sticky="ew", padx=(0, 8))

        rule_buttons = ttk.Frame(rules_frame)
        rule_buttons.grid(row=0, column=4, sticky="ew")
        ttk.Button(
            rule_buttons,
            text="Nomenclatura...",
            style="Secondary.TButton",
            command=self._open_naming_rules_dialog,
        ).pack(side="left", padx=(0, 6))
        ttk.Button(
            rule_buttons,
            text="Aliases de pastas...",
            style="Secondary.TButton",
            command=self._open_alias_rules_dialog,
        ).pack(side="left")

        checks_frame = ttk.Frame(rules_frame)
        checks_frame.grid(row=1, column=0, columnspan=5, sticky="w", pady=(8, 0))
        ttk.Checkbutton(
            checks_frame,
            text="Conferir documentos nao bancarios pelo nome cadastrado",
            variable=self._allow_generic_documents_var,
        ).pack(side="left", padx=(0, 18))
        ttk.Checkbutton(
            checks_frame,
            text="Exigir termos do documento no nome do arquivo",
            variable=self._require_registered_terms_var,
        ).pack(side="left")

        # ── Actions ───────────────────────────────────────────────────────────
        action_bar = ttk.Frame(outer)
        action_bar.pack(fill="x", pady=(0, 8))

        self._verify_btn = ttk.Button(
            action_bar, text="Verificar agora", style="Primary.TButton", command=self._run_check
        )
        self._verify_btn.pack(side="left")
        self._status_label = ttk.Label(action_bar, textvariable=self._status_var, foreground=PALETTE["muted"])
        self._status_label.pack(side="left", padx=(12, 0))

        # ── Summary bar ───────────────────────────────────────────────────────
        self._summary_frame = ttk.Frame(outer)
        self._summary_frame.pack(fill="x", pady=(0, 6))
        self._summary_label = ttk.Label(self._summary_frame, text="", foreground=PALETTE["muted"])
        self._summary_label.pack(side="left")

        # ── Results treeview ──────────────────────────────────────────────────
        tree_frame = ttk.LabelFrame(outer, text="Resultado por documento", padding=6)
        tree_frame.pack(fill="both", expand=True, pady=(0, 8))

        columns = (
            "empresa", "documento", "competencia", "status_atual",
            "resultado", "arquivo", "arq_periodo", "score", "motivo",
        )
        self._tree = ttk.Treeview(tree_frame, columns=columns, show="headings", selectmode="browse")
        self._tree.heading("empresa", text="Empresa")
        self._tree.heading("documento", text="Documento")
        self._tree.heading("competencia", text="Competencia")
        self._tree.heading("status_atual", text="Status atual")
        self._tree.heading("resultado", text="Resultado")
        self._tree.heading("arquivo", text="Arquivo encontrado")
        self._tree.heading("arq_periodo", text="Comp. arquivo")
        self._tree.heading("score", text="Score")
        self._tree.heading("motivo", text="Motivo / Alertas")

        self._tree.column("empresa", width=175, minwidth=100)
        self._tree.column("documento", width=190, minwidth=100)
        self._tree.column("competencia", width=85, anchor="center", minwidth=70)
        self._tree.column("status_atual", width=100, anchor="center", minwidth=80)
        self._tree.column("resultado", width=110, anchor="center", minwidth=90)
        self._tree.column("arquivo", width=165, minwidth=100)
        self._tree.column("arq_periodo", width=90, anchor="center", minwidth=70)
        self._tree.column("score", width=55, anchor="center", minwidth=45)
        self._tree.column("motivo", width=280, minwidth=100)

        for tag, color in _RESULT_TAG_COLORS.items():
            self._tree.tag_configure(tag, foreground=color)

        scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=scrollbar.set)
        self._tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # ── Bottom buttons ────────────────────────────────────────────────────
        bottom = ttk.Frame(outer)
        bottom.pack(fill="x")
        ttk.Button(bottom, text="Fechar", command=self.destroy, style="Quiet.TButton").pack(side="right")
        self._apply_btn = ttk.Button(
            bottom, text="Aplicar marcacoes automaticas",
            style="Primary.TButton", command=self._apply_high_confidence,
            state="disabled",
        )
        self._apply_btn.pack(side="right", padx=(0, 8))
        self._copy_log_btn = ttk.Button(
            bottom, text="Copiar log", style="Secondary.TButton",
            command=self._copy_log, state="disabled",
        )
        self._copy_log_btn.pack(side="left")

    # ── Callbacks ─────────────────────────────────────────────────────────────

    def _current_rule_options(self) -> dict:
        layout_mode = _LAYOUT_BY_LABEL.get(self._layout_label_var.get(), LAYOUT_AUTO)
        period_source = _PERIOD_SOURCE_BY_LABEL.get(
            self._period_source_label_var.get(), PERIOD_SOURCE_FILENAME_OR_FOLDER
        )
        return {
            "layout_mode": layout_mode,
            "period_source": period_source,
            "allow_generic_documents": self._allow_generic_documents_var.get(),
            "require_registered_terms": self._require_registered_terms_var.get(),
            "bank_folder_aliases": self._bank_folder_aliases_var.get(),
            "cc_folder_aliases": self._cc_folder_aliases_var.get(),
            "aplicacao_folder_aliases": self._aplicacao_folder_aliases_var.get(),
            "filename_templates": self._filename_templates_var.get(),
            "require_template_match": self._require_template_match_var.get(),
            "required_filename_terms": self._required_filename_terms_var.get(),
            "forbidden_filename_terms": self._forbidden_filename_terms_var.get(),
        }

    def _open_naming_rules_dialog(self) -> None:
        dialog = tk.Toplevel(self)
        dialog.title("Regras de nomenclatura")
        dialog.transient(self)
        dialog.resizable(True, True)
        dialog.minsize(720, 460)
        dialog.grab_set()

        frame = ttk.Frame(dialog, padding=14)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(2, weight=1)

        help_text = (
            "Use um padrao por linha. Variaveis aceitas: {codigo}, {documento}, "
            "{competencia}, {banco}, {tipo}. Ex.: {codigo}. {banco} {tipo} {competencia}"
        )
        ttk.Label(frame, text=help_text, foreground=PALETTE["muted"], wraplength=680).grid(
            row=0, column=0, sticky="ew", pady=(0, 10)
        )

        ttk.Checkbutton(
            frame,
            text="Exigir que o arquivo siga pelo menos um dos padroes abaixo",
            variable=self._require_template_match_var,
        ).grid(row=1, column=0, sticky="w", pady=(0, 8))

        templates = tk.Text(frame, height=8, width=88, wrap="none")
        templates.grid(row=2, column=0, sticky="nsew")
        templates.insert("1.0", self._filename_templates_var.get())

        terms = ttk.LabelFrame(frame, text="Termos personalizados", padding=10)
        terms.grid(row=3, column=0, sticky="ew", pady=(12, 0))
        terms.columnconfigure(1, weight=1)

        ttk.Label(terms, text="Obrigatorios:").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=(0, 8))
        ttk.Entry(terms, textvariable=self._required_filename_terms_var).grid(
            row=0, column=1, sticky="ew", pady=(0, 8)
        )
        ttk.Label(terms, text="Proibidos:").grid(row=1, column=0, sticky="w", padx=(0, 8))
        ttk.Entry(terms, textvariable=self._forbidden_filename_terms_var).grid(
            row=1, column=1, sticky="ew"
        )
        ttk.Label(
            terms,
            text="Separe por ponto e virgula. Ex.: cancelado; rascunho; comprovante",
            foreground=PALETTE["muted"],
        ).grid(row=2, column=0, columnspan=2, sticky="w", pady=(8, 0))

        def save_and_close() -> None:
            self._filename_templates_var.set(templates.get("1.0", "end").strip())
            dialog.destroy()

        btns = ttk.Frame(frame)
        btns.grid(row=4, column=0, sticky="e", pady=(12, 0))
        ttk.Button(btns, text="Cancelar", style="Quiet.TButton", command=dialog.destroy).pack(
            side="right", padx=(8, 0)
        )
        ttk.Button(btns, text="Salvar regras", style="Primary.TButton", command=save_and_close).pack(
            side="right"
        )

        dialog.update_idletasks()
        x = self.winfo_rootx() + (self.winfo_width() - dialog.winfo_width()) // 2
        y = self.winfo_rooty() + (self.winfo_height() - dialog.winfo_height()) // 2
        dialog.geometry(f"+{max(x, 0)}+{max(y, 0)}")

    def _open_alias_rules_dialog(self) -> None:
        dialog = tk.Toplevel(self)
        dialog.title("Aliases de pastas")
        dialog.transient(self)
        dialog.resizable(False, False)
        dialog.grab_set()

        frame = ttk.Frame(dialog, padding=14)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(1, weight=1)

        ttk.Label(
            frame,
            text="Separe apelidos por ponto e virgula. Ex.: Extratos Bancarios; Bancos",
            foreground=PALETTE["muted"],
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 10))

        rows = (
            ("Pasta bancaria:", self._bank_folder_aliases_var),
            ("Conta corrente:", self._cc_folder_aliases_var),
            ("Aplicacao/investimento:", self._aplicacao_folder_aliases_var),
        )
        for row, (label, var) in enumerate(rows, start=1):
            ttk.Label(frame, text=label).grid(row=row, column=0, sticky="w", padx=(0, 8), pady=(0, 8))
            ttk.Entry(frame, textvariable=var, width=72).grid(
                row=row, column=1, sticky="ew", pady=(0, 8)
            )

        btns = ttk.Frame(frame)
        btns.grid(row=len(rows) + 1, column=0, columnspan=2, sticky="e", pady=(8, 0))
        ttk.Button(btns, text="Fechar", style="Primary.TButton", command=dialog.destroy).pack(side="right")

        dialog.update_idletasks()
        x = self.winfo_rootx() + (self.winfo_width() - dialog.winfo_width()) // 2
        y = self.winfo_rooty() + (self.winfo_height() - dialog.winfo_height()) // 2
        dialog.geometry(f"+{max(x, 0)}+{max(y, 0)}")

    def _browse_root(self) -> None:
        initial = self._root_dir_var.get().strip() or "/"
        chosen = filedialog.askdirectory(
            parent=self, title="Selecionar pasta raiz das empresas", initialdir=initial
        )
        if chosen:
            self._root_dir_var.set(chosen)

    def _run_check(self) -> None:
        root_dir_raw = self._root_dir_var.get().strip()
        if not root_dir_raw:
            messagebox.showwarning(APP_NAME, "Informe a pasta raiz das empresas antes de verificar.", parent=self)
            return

        root_dir = Path(root_dir_raw)
        if not root_dir.exists() or not root_dir.is_dir():
            messagebox.showerror(APP_NAME, f"Pasta raiz nao encontrada:\n{root_dir}", parent=self)
            return

        import datetime
        mode = self._mode_var.get()
        skip_received = self._skip_received_var.get()
        rule_options = self._current_rule_options()

        _save_settings({
            "root_dir": root_dir_raw,
            "mode": mode,
            "skip_received": skip_received,
            **rule_options,
        })

        scope = self._scope_var.get()
        empresa_ids: list[int] | None = (
            self.visible_empresa_ids if scope == "visible" else None
        )
        self._log_metadata = {
            "data": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
            "raiz": root_dir_raw,
            "competencia": self._periodo_label,
            "modo": "Somente competencia atual" if mode == MODE_CURRENT_ONLY else "Pendentes ate a competencia",
            "escopo": f"Empresas visiveis ({len(self.visible_empresa_ids)})" if scope == "visible" else "Todas as empresas ativas",
            "estrutura": self._layout_label_var.get(),
            "fonte_competencia": self._period_source_label_var.get(),
            "exige_nomenclatura": "sim" if rule_options.get("require_template_match") else "nao",
        }

        service = FileCheckService(
            self.services.empresa_service,
            self.services.documento_service,
            self.services.periodo_service,
            self.services.status_service,
        )

        self._verify_btn.configure(state="disabled")
        self._apply_btn.configure(state="disabled")
        self._status_var.set("Iniciando verificacao...")
        self.update_idletasks()

        def progress(msg: str) -> None:
            self._status_var.set(msg)
            self.update_idletasks()

        try:
            self._results = service.check_period(
                self.periodo_id, empresa_ids, root_dir, progress,
                mode=mode, skip_received=skip_received, options=rule_options,
            )
        except Exception as exc:
            messagebox.showerror(APP_NAME, f"Erro durante a verificacao:\n{exc}", parent=self)
            self._verify_btn.configure(state="normal")
            self._status_var.set("")
            return

        self._verify_btn.configure(state="normal")
        self._copy_log_btn.configure(state="normal" if self._results else "disabled")
        self._populate_results()

    def _refilter_results(self) -> None:
        if self._results:
            self._populate_results()

    def _populate_results(self) -> None:
        self._tree.delete(*self._tree.get_children())

        counts = {
            RESULT_ALTA_CONFIANCA: 0, RESULT_REVISAR: 0,
            RESULT_NAO_ENCONTRADO: 0, RESULT_ERRO: 0,
        }
        alta_atual = 0

        for r in self._results:
            counts[r["resultado"]] += 1
            if r["resultado"] == RESULT_ALTA_CONFIANCA and r.get("temporal_class") == TEMPORAL_ATUAL:
                alta_atual += 1

        total = len(self._results)
        if total == 0:
            self._status_var.set("Nenhum documento conferivel encontrado no escopo selecionado.")
            self._apply_btn.configure(state="disabled", text="Aplicar marcacoes automaticas")
            return

        summary_parts = []
        if counts[RESULT_ALTA_CONFIANCA]:
            summary_parts.append(f"Alta confianca: {counts[RESULT_ALTA_CONFIANCA]}")
        if counts[RESULT_REVISAR]:
            summary_parts.append(f"Revisar: {counts[RESULT_REVISAR]}")
        if counts[RESULT_NAO_ENCONTRADO]:
            summary_parts.append(f"Nao encontrado: {counts[RESULT_NAO_ENCONTRADO]}")
        if counts[RESULT_ERRO]:
            summary_parts.append(f"Erro: {counts[RESULT_ERRO]}")

        self._status_var.set(f"{total} linha(s)  —  " + "  |  ".join(summary_parts))

        problems_only = self._show_problems_only_var.get()

        for r in self._results:
            if problems_only and r["resultado"] == RESULT_ALTA_CONFIANCA:
                continue

            arquivo_name = Path(r["arquivo"]).name if r["arquivo"] else "—"
            arq_periods = r.get("arquivo_periodo") or []
            arq_periodo_label = _fmt_period(arq_periods[0]) if arq_periods else "—"
            alertas = r.get("alertas") or []
            related = r.get("related_period_files") or []
            motivo_text = r["motivo"]
            if alertas:
                motivo_text = motivo_text + "  |  " + " | ".join(alertas) if motivo_text else " | ".join(alertas)
            if related and r["arquivo"] is None:
                rel_parts = list(dict.fromkeys(rf["period_label"] for rf in related))
                rel_str = "Rel: " + ", ".join(rel_parts)
                motivo_text = motivo_text + "  |  " + rel_str if motivo_text else rel_str
            duplicates = r.get("duplicate_files") or []
            if duplicates:
                dup_names = [dup["filename"] for dup in duplicates[:3]]
                dup_text = "Duplicados: " + ", ".join(dup_names)
                if len(duplicates) > 3:
                    dup_text += f" (+{len(duplicates) - 3})"
                motivo_text = motivo_text + "  |  " + dup_text if motivo_text else dup_text

            periodo_analisado = r.get("periodo_analisado")
            competencia_label = _fmt_period(periodo_analisado) if periodo_analisado else self._periodo_label
            status_atual = r.get("status_atual") or "—"

            self._tree.insert(
                "", "end",
                values=(
                    r["empresa_nome"],
                    r["documento_nome"],
                    competencia_label,
                    status_atual,
                    _RESULT_LABELS.get(r["resultado"], r["resultado"]),
                    arquivo_name,
                    arq_periodo_label,
                    str(r["score"]) if r["score"] else "—",
                    motivo_text,
                ),
                tags=(r["resultado"],),
            )

        if alta_atual > 0:
            self._apply_btn.configure(
                state="normal",
                text=f"Aplicar {alta_atual} marcacao(oes) da competencia atual",
            )
        else:
            self._apply_btn.configure(state="disabled", text="Aplicar marcacoes automaticas")

    def _generate_log(self) -> str:
        counts = {
            RESULT_ALTA_CONFIANCA: 0, RESULT_REVISAR: 0,
            RESULT_NAO_ENCONTRADO: 0, RESULT_ERRO: 0,
        }
        empresas_vistas: set[int] = set()
        for r in self._results:
            counts[r["resultado"]] += 1
            empresas_vistas.add(r["empresa_id"])

        meta = self._log_metadata
        lines = [
            "[DocFLow Verificar Servidor]",
            f"Data: {meta.get('data', '—')}",
            f"Raiz: {meta.get('raiz', '—')}",
            f"Competencia: {meta.get('competencia', '—')}",
            f"Modo: {meta.get('modo', '—')}",
            f"Escopo: {meta.get('escopo', '—')}",
            f"Estrutura de pastas: {meta.get('estrutura', '—')}",
            f"Fonte da competencia: {meta.get('fonte_competencia', '—')}",
            f"Exige nomenclatura: {meta.get('exige_nomenclatura', '—')}",
            "",
            "Resumo:",
            f"- Empresas analisadas: {len(empresas_vistas)}",
            f"- Documentos analisados: {len(self._results)}",
            f"- Alta confianca: {counts[RESULT_ALTA_CONFIANCA]}",
            f"- Revisar: {counts[RESULT_REVISAR]}",
            f"- Nao encontrado: {counts[RESULT_NAO_ENCONTRADO]}",
            f"- Erros: {counts[RESULT_ERRO]}",
        ]

        problems = [r for r in self._results if r["resultado"] != RESULT_ALTA_CONFIANCA]
        if problems:
            lines += ["", "Problemas:"]
            for r in problems:
                pa = r.get("periodo_analisado")
                comp = _fmt_period(pa) if pa else self._periodo_label
                arquivo = Path(r["arquivo"]).name if r["arquivo"] else "-"
                status = r.get("status_atual") or "vazio"
                resultado_label = _RESULT_LABELS.get(r["resultado"], r["resultado"])
                motivo = r.get("motivo") or "-"
                related = r.get("related_period_files") or []
                lines += [
                    f"Empresa: {r['empresa_nome']}",
                    f"Documento: {r['documento_nome']}",
                    f"Competencia analisada: {comp}",
                    f"Status atual: {status}",
                    f"Resultado: {resultado_label}",
                    f"Arquivo escolhido: {arquivo}",
                ]
                if related:
                    lines.append("Arquivos relacionados ignorados:")
                    seen_rel: set[str] = set()
                    for rf in related:
                        key = f"{rf['filename']} -> {rf['period_label']}"
                        if key not in seen_rel:
                            seen_rel.add(key)
                            lines.append(f"  - {key}")
                duplicates = r.get("duplicate_files") or []
                if duplicates:
                    lines.append("Possiveis duplicados:")
                    for dup in duplicates:
                        lines.append(f"  - {dup['filename']} (score {dup['score']})")
                alertas = r.get("alertas") or []
                motivo_full = motivo
                if alertas:
                    motivo_full += "  |  " + " | ".join(alertas)
                lines.append(f"Motivo: {motivo_full}")
                lines.append("")

        return "\n".join(lines)

    def _copy_log(self) -> None:
        if not self._results:
            return
        text = self._generate_log()
        self.clipboard_clear()
        self.clipboard_append(text)
        self._status_var.set("Log copiado para a area de transferencia.")

    def _apply_high_confidence(self) -> None:
        from documentos_empresa_app.services.file_check_service import TEMPORAL_ATUAL

        eligible = [
            r for r in self._results
            if r["resultado"] == RESULT_ALTA_CONFIANCA
            and r.get("temporal_class") == TEMPORAL_ATUAL
        ]
        if not eligible:
            return

        # Build a human-readable confirmation list (max 10 shown)
        lines = []
        for r in eligible[:10]:
            pa = r.get("periodo_analisado")
            period_str = _fmt_period(pa) if pa else self._periodo_label
            lines.append(f"  • {r['empresa_nome']} / {r['documento_nome']} ({period_str})")
        if len(eligible) > 10:
            lines.append(f"  ... e mais {len(eligible) - 10} documento(s)")

        msg = (
            f"Serao marcados como Recebido {len(eligible)} documento(s):\n\n"
            + "\n".join(lines)
            + "\n\nDeseja continuar?"
        )
        if not messagebox.askyesno(APP_NAME, msg, parent=self):
            return

        service = FileCheckService(
            self.services.empresa_service,
            self.services.documento_service,
            self.services.periodo_service,
            self.services.status_service,
        )

        try:
            result = service.apply_safe_matches(self._results)
        except Exception as exc:
            messagebox.showerror(APP_NAME, f"Erro ao aplicar marcacoes:\n{exc}", parent=self)
            return

        updated = result.get("updated", 0)
        messagebox.showinfo(
            APP_NAME,
            f"{updated} documento(s) marcado(s) como Recebido com sucesso.",
            parent=self,
        )

        self._apply_btn.configure(state="disabled")

        if callable(self.on_changes_applied):
            self.on_changes_applied()
