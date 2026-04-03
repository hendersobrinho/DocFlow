from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

from documentos_empresa_app.utils.common import (
    APP_NAME,
    CONFIG_DIR,
    CONFIG_FILE,
    DEFAULT_DB_NAME,
    LEGACY_CONFIG_DIR,
    MONTH_NAMES,
    STATUS_COLORS,
    STATUS_OPTIONS,
    ValidationError,
    count_months_between,
    format_period_label,
    month_key,
)
from documentos_empresa_app.utils.storage import (
    build_database_path,
    create_database_directory,
    is_path_within_directory,
)
from documentos_empresa_app.utils.resources import get_executable_directory


def ensure_config_dir() -> None:
    migrate_legacy_config_dir()
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)


def migrate_legacy_config_dir() -> None:
    if CONFIG_DIR == LEGACY_CONFIG_DIR or CONFIG_DIR.exists() or not LEGACY_CONFIG_DIR.exists():
        return

    CONFIG_DIR.parent.mkdir(parents=True, exist_ok=True)
    try:
        shutil.move(str(LEGACY_CONFIG_DIR), str(CONFIG_DIR))
    except OSError:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        legacy_config_file = LEGACY_CONFIG_DIR / "config.json"
        if legacy_config_file.exists() and not CONFIG_FILE.exists():
            shutil.copy2(legacy_config_file, CONFIG_FILE)
        return

    _rewrite_migrated_config_paths(CONFIG_FILE, LEGACY_CONFIG_DIR, CONFIG_DIR)


def _rewrite_migrated_config_paths(config_file: Path, old_root: Path, new_root: Path) -> None:
    if not config_file.exists():
        return
    try:
        config = json.loads(config_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return

    db_path = config.get("db_path")
    if not db_path:
        return

    try:
        resolved_path = Path(db_path).expanduser()
        if resolved_path.is_relative_to(old_root):
            config["db_path"] = str(new_root / resolved_path.relative_to(old_root))
            config_file.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        return


def load_config() -> dict:
    ensure_config_dir()
    if not CONFIG_FILE.exists():
        return {}
    try:
        return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def save_config(config: dict) -> None:
    ensure_config_dir()
    CONFIG_FILE.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")


def load_login_preferences() -> dict:
    config = load_config()
    stored = config.get("login_preferences")
    if not isinstance(stored, dict):
        return {
            "username": "",
            "remember_credential": False,
            "remembered_token": None,
        }

    username = str(stored.get("username") or "").strip()
    remembered_token = str(stored.get("remembered_token") or "").strip() or None
    remember_credential = bool(stored.get("remember_credential") and remembered_token)
    return {
        "username": username,
        "remember_credential": remember_credential,
        "remembered_token": remembered_token,
    }


def save_login_preferences(
    username: str | None,
    *,
    remember_credential: bool,
    remembered_token: str | None,
) -> None:
    config = load_config()
    normalized_username = str(username or "").strip()
    normalized_token = str(remembered_token or "").strip() or None

    if normalized_username or normalized_token or remember_credential:
        config["login_preferences"] = {
            "username": normalized_username,
            "remember_credential": bool(remember_credential and normalized_token),
            "remembered_token": normalized_token if remember_credential else None,
        }
    else:
        config.pop("login_preferences", None)
    save_config(config)


def open_directory_in_file_manager(directory: str | Path) -> None:
    path = Path(directory).expanduser()
    if not path.exists() or not path.is_dir():
        raise ValidationError("A pasta vinculada nao foi encontrada no computador.")

    try:
        if sys.platform.startswith("win") and hasattr(os, "startfile"):
            os.startfile(str(path))
            return
        if sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
            return
        subprocess.Popen(["xdg-open", str(path)])
    except OSError as exc:
        raise ValidationError("Nao foi possivel abrir a pasta vinculada.") from exc


def get_install_root_directory() -> Path:
    app_reference = Path(sys.executable if getattr(sys, "frozen", False) else __file__).resolve()
    anchor = app_reference.anchor or Path.cwd().anchor or os.sep
    return Path(anchor)


class DatabasePathDialog(tk.Toplevel):
    def __init__(self, parent: tk.Misc, initial_dir: Path, default_filename: str) -> None:
        super().__init__(parent)
        self.parent = parent
        self.result: Path | None = None
        self.folder_var = tk.StringVar(value=str(initial_dir))
        self.filename_var = tk.StringVar(value=default_filename)
        self.preview_var = tk.StringVar()

        self.title(f"{APP_NAME} - Banco de dados")
        self.resizable(False, False)
        self.transient(parent.winfo_toplevel())
        self.protocol("WM_DELETE_WINDOW", self.cancel)

        self._build_layout()
        self._update_preview()

        self.grab_set()
        self.after(10, self._center_on_parent)
        self.wait_visibility()

    def _build_layout(self) -> None:
        container = ttk.Frame(self, padding=14)
        container.pack(fill="both", expand=True)

        ttk.Label(
            container,
            text=(
                "Escolha a pasta onde o banco SQLite sera salvo.\n"
                "Se precisar, voce pode criar uma nova pasta antes de confirmar."
            ),
            justify="left",
        ).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 12))

        ttk.Label(container, text="Pasta de destino").grid(row=1, column=0, sticky="w")
        folder_entry = ttk.Entry(container, textvariable=self.folder_var, width=58)
        folder_entry.grid(row=2, column=0, sticky="ew", padx=(0, 8))
        folder_entry.bind("<KeyRelease>", lambda _event: self._update_preview())
        folder_entry.bind("<FocusOut>", lambda _event: self._update_preview())
        ttk.Button(container, text="Escolher pasta", command=self.choose_folder).grid(
            row=2, column=1, sticky="ew", padx=(0, 8)
        )
        ttk.Button(container, text="Criar pasta", command=self.create_folder).grid(row=2, column=2, sticky="ew")

        ttk.Label(container, text="Nome do arquivo do banco").grid(row=3, column=0, sticky="w", pady=(12, 0))
        filename_entry = ttk.Entry(container, textvariable=self.filename_var, width=32)
        filename_entry.grid(row=4, column=0, sticky="w", pady=(0, 8))
        filename_entry.bind("<KeyRelease>", lambda _event: self._update_preview())
        filename_entry.bind("<FocusOut>", lambda _event: self._update_preview())

        ttk.Label(container, text="Caminho final").grid(row=5, column=0, sticky="w")
        ttk.Label(container, textvariable=self.preview_var, foreground="#4F4F4F", wraplength=620).grid(
            row=6, column=0, columnspan=3, sticky="w", pady=(0, 12)
        )

        button_row = ttk.Frame(container)
        button_row.grid(row=7, column=0, columnspan=3, sticky="e")
        ttk.Button(button_row, text="Cancelar", command=self.cancel).pack(side="right")
        ttk.Button(button_row, text="Confirmar", command=self.confirm).pack(side="right", padx=(0, 8))

        container.columnconfigure(0, weight=1)

    def _center_on_parent(self) -> None:
        self.update_idletasks()
        parent = self.parent.winfo_toplevel()
        x = parent.winfo_rootx() + max((parent.winfo_width() - self.winfo_width()) // 2, 0)
        y = parent.winfo_rooty() + max((parent.winfo_height() - self.winfo_height()) // 2, 0)
        self.geometry(f"+{x}+{y}")

    def choose_folder(self) -> None:
        initial_dir = Path(self.folder_var.get()).expanduser()
        if not initial_dir.exists():
            initial_dir = get_install_root_directory()
        selected = filedialog.askdirectory(
            parent=self,
            title="Escolha a pasta onde o banco sera salvo",
            initialdir=str(initial_dir),
            mustexist=True,
        )
        if selected:
            self.folder_var.set(selected)
            self._update_preview()

    def create_folder(self) -> None:
        base_folder = self.folder_var.get().strip() or str(get_install_root_directory())
        folder_name = simpledialog.askstring(
            f"{APP_NAME} - Criar pasta",
            "Informe o nome da nova pasta:",
            parent=self,
        )
        if folder_name is None:
            return
        try:
            created_folder = create_database_directory(base_folder, folder_name)
        except ValidationError as exc:
            messagebox.showerror(APP_NAME, str(exc), parent=self)
            return
        except OSError:
            messagebox.showerror(
                APP_NAME,
                "Nao foi possivel criar a pasta no local informado.",
                parent=self,
            )
            return

        self.folder_var.set(str(created_folder))
        self._update_preview()
        messagebox.showinfo(APP_NAME, f"Pasta criada com sucesso em:\n{created_folder}", parent=self)

    def confirm(self) -> None:
        try:
            db_path = build_database_path(self.folder_var.get(), self.filename_var.get(), DEFAULT_DB_NAME)
        except ValidationError as exc:
            messagebox.showerror(APP_NAME, str(exc), parent=self)
            return

        if getattr(sys, "frozen", False) and is_path_within_directory(db_path, get_executable_directory()):
            messagebox.showerror(
                APP_NAME,
                (
                    "Escolha uma pasta fora da instalacao do programa para salvar o banco.\n\n"
                    "Isso protege os dados durante atualizacoes ou reinstalacoes."
                ),
                parent=self,
            )
            return

        if not is_database_path_usable(db_path):
            messagebox.showerror(
                APP_NAME,
                "O local informado para o banco nao pode ser usado.\n\nEscolha outra pasta ou crie uma nova pasta.",
                parent=self,
            )
            return

        self.result = db_path
        self.destroy()

    def cancel(self) -> None:
        should_cancel = messagebox.askyesno(
            APP_NAME,
            (
                "Nenhum local foi selecionado para o banco de dados.\n\n"
                "Deseja cancelar a abertura do programa?"
            ),
            parent=self,
        )
        if should_cancel:
            self.result = None
            self.destroy()

    def _update_preview(self) -> None:
        try:
            preview_path = build_database_path(self.folder_var.get(), self.filename_var.get(), DEFAULT_DB_NAME)
            self.preview_var.set(str(preview_path))
        except ValidationError:
            self.preview_var.set("")


def prompt_database_path(parent: tk.Misc | None = None) -> Path | None:
    ensure_config_dir()
    owner = parent.winfo_toplevel() if parent else tk._get_default_root()
    dialog = DatabasePathDialog(owner, get_install_root_directory(), DEFAULT_DB_NAME)
    owner.wait_window(dialog)

    if dialog.result is None:
        return None

    config = load_config()
    config["db_path"] = str(dialog.result)
    save_config(config)
    return dialog.result


def is_database_path_usable(db_path: str | Path) -> bool:
    path = Path(db_path)
    if path.exists():
        return path.is_file() and os.access(path, os.R_OK | os.W_OK)

    parent = path.parent
    return parent.exists() and parent.is_dir() and os.access(parent, os.W_OK)


def ensure_database_path(parent: tk.Misc | None = None) -> Path | None:
    config = load_config()
    db_path = config.get("db_path")
    if db_path and is_database_path_usable(db_path):
        return Path(db_path)
    if db_path and not is_database_path_usable(db_path):
        messagebox.showwarning(
            APP_NAME,
            (
                "O caminho salvo para o banco de dados nao esta acessivel.\n\n"
                "Escolha um novo local para continuar."
            ),
            parent=parent,
        )

    messagebox.showinfo(
        APP_NAME,
        (
            "Selecione onde o banco SQLite sera armazenado.\n\n"
            "A janela ja sera aberta na raiz do disco principal.\n"
            "Se voce fechar sem escolher, o sistema pedira confirmacao antes de sair."
        ),
        parent=parent,
    )
    return prompt_database_path(parent=parent)

class ScrollableFrame(ttk.Frame):
    """Frame com rolagem vertical para grids maiores."""

    def __init__(self, master: tk.Misc, **kwargs) -> None:
        super().__init__(master, **kwargs)
        self.canvas = tk.Canvas(self, highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.inner = ttk.Frame(self.canvas)
        self.window_id = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")

        self.inner.bind("<Configure>", self._on_frame_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")

        self.canvas.bind_all("<MouseWheel>", self._on_mouse_wheel, add="+")
        self.canvas.bind_all("<Button-4>", self._on_mouse_wheel, add="+")
        self.canvas.bind_all("<Button-5>", self._on_mouse_wheel, add="+")

    def _on_frame_configure(self, _event: tk.Event) -> None:
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas_configure(self, event: tk.Event) -> None:
        self.canvas.itemconfigure(self.window_id, width=event.width)

    def _on_mouse_wheel(self, event: tk.Event) -> None:
        if not self.winfo_exists() or not self._pointer_is_over_scroll_area():
            return

        delta = self._normalize_mouse_wheel_delta(event)
        if delta == 0:
            return

        self.canvas.yview_scroll(delta, "units")

    def _pointer_is_over_scroll_area(self) -> bool:
        widget_under_pointer = self.winfo_containing(*self.winfo_pointerxy())
        current = widget_under_pointer
        while current is not None:
            if current in {self, self.canvas, self.inner, self.scrollbar}:
                return True
            current = getattr(current, "master", None)
        return False

    def _normalize_mouse_wheel_delta(self, event: tk.Event) -> int:
        if getattr(event, "num", None) == 4:
            return -1
        if getattr(event, "num", None) == 5:
            return 1

        delta = int(getattr(event, "delta", 0))
        if delta == 0:
            return 0
        if abs(delta) >= 120:
            return int(-delta / 120)
        return -1 if delta > 0 else 1


class CompanyListDialog(tk.Toplevel):
    def __init__(
        self,
        parent: tk.Misc,
        companies: list[dict],
        initial_search: str = "",
        title: str = "Empresas cadastradas",
    ) -> None:
        super().__init__(parent.winfo_toplevel())
        self.parent = parent
        self.title(title)
        self.transient(parent.winfo_toplevel())
        self.resizable(True, True)
        self.minsize(640, 360)
        self.selected_company_id: int | None = None
        self.companies = companies
        self.search_var = tk.StringVar(value=initial_search)

        self._build_layout()
        self._populate_tree()
        self.grab_set()
        self.after(10, self._center_on_parent)

    def _build_layout(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        search_row = ttk.Frame(self, padding=(12, 12, 12, 8))
        search_row.grid(row=0, column=0, sticky="ew")
        search_row.columnconfigure(1, weight=1)

        ttk.Label(search_row, text="Buscar na lista").grid(row=0, column=0, sticky="w", padx=(0, 8))
        search_entry = ttk.Entry(search_row, textvariable=self.search_var)
        search_entry.grid(row=0, column=1, sticky="ew")
        search_entry.bind("<KeyRelease>", lambda _event: self._populate_tree())

        tree_frame = ttk.Frame(self, padding=(12, 0, 12, 0))
        tree_frame.grid(row=1, column=0, sticky="nsew")
        tree_frame.columnconfigure(0, weight=1)
        tree_frame.rowconfigure(0, weight=1)

        self.tree = ttk.Treeview(
            tree_frame,
            columns=("codigo", "nome", "situacao"),
            show="headings",
            selectmode="browse",
        )
        self.tree.heading("codigo", text="Codigo")
        self.tree.heading("nome", text="Nome")
        self.tree.heading("situacao", text="Situacao")
        self.tree.column("codigo", width=120, anchor="center")
        self.tree.column("nome", width=380)
        self.tree.column("situacao", width=110, anchor="center")
        self.tree.grid(row=0, column=0, sticky="nsew")
        self.tree.bind("<Double-1>", self._confirm_selection)
        self.tree.bind("<Return>", self._confirm_selection)

        scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=scrollbar.set)

        button_row = ttk.Frame(self, padding=12)
        button_row.grid(row=2, column=0, sticky="e")
        ttk.Button(button_row, text="Cancelar", command=self.destroy).pack(side="right")
        ttk.Button(button_row, text="Selecionar", command=self._confirm_selection).pack(side="right", padx=(0, 8))

        search_entry.focus_set()

    def _populate_tree(self) -> None:
        search = self.search_var.get().strip().casefold()
        self.tree.delete(*self.tree.get_children())

        ranked_companies: list[tuple[int, str, dict]] = []
        for company in self.companies:
            company_text = f'{company["codigo_empresa"]} {company["nome_empresa"]}'.casefold()
            company_name = company["nome_empresa"].casefold()
            company_code = str(company["codigo_empresa"]).casefold()
            if search:
                if company_name.startswith(search) or company_code.startswith(search):
                    rank = 0
                elif search in company_name:
                    rank = 1
                elif search in company_text:
                    rank = 2
                else:
                    continue
            else:
                rank = 3
            ranked_companies.append((rank, company_name, company))

        ranked_companies.sort(key=lambda item: (item[0], item[1], item[2]["codigo_empresa"]))

        for _rank, _company_name, company in ranked_companies:
            situacao = "Ativa" if company["ativa"] else "Inativa"
            self.tree.insert(
                "",
                "end",
                iid=str(company["id"]),
                values=(company["codigo_empresa"], company["nome_empresa"], situacao),
            )

        children = self.tree.get_children()
        if children:
            self.tree.selection_set(children[0])
            self.tree.focus(children[0])

    def _confirm_selection(self, _event=None) -> str | None:
        selection = self.tree.selection()
        if not selection:
            return None
        self.selected_company_id = int(selection[0])
        self.destroy()
        return "break"

    def _center_on_parent(self) -> None:
        self.update_idletasks()
        parent = self.parent.winfo_toplevel()
        x = parent.winfo_rootx() + max((parent.winfo_width() - self.winfo_width()) // 2, 0)
        y = parent.winfo_rooty() + max((parent.winfo_height() - self.winfo_height()) // 2, 0)
        self.geometry(f"+{x}+{y}")


class CompanyMultiSelectDialog(tk.Toplevel):
    def __init__(
        self,
        parent: tk.Misc,
        companies: list[dict],
        selected_company_ids: list[int] | None = None,
        title: str = "Selecionar empresas",
    ) -> None:
        super().__init__(parent.winfo_toplevel())
        self.parent = parent
        self.title(title)
        self.transient(parent.winfo_toplevel())
        self.resizable(True, True)
        self.minsize(680, 380)
        self.companies = companies
        self.selected_company_ids = [int(company_id) for company_id in (selected_company_ids or [])]
        self.search_var = tk.StringVar()

        self._build_layout()
        self._populate_tree()
        self.grab_set()
        self.after(10, self._center_on_parent)

    def _build_layout(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        search_row = ttk.Frame(self, padding=(12, 12, 12, 8))
        search_row.grid(row=0, column=0, sticky="ew")
        search_row.columnconfigure(1, weight=1)

        ttk.Label(search_row, text="Buscar empresas").grid(row=0, column=0, sticky="w", padx=(0, 8))
        search_entry = ttk.Entry(search_row, textvariable=self.search_var)
        search_entry.grid(row=0, column=1, sticky="ew")
        search_entry.bind("<KeyRelease>", lambda _event: self._populate_tree())

        tree_frame = ttk.Frame(self, padding=(12, 0, 12, 0))
        tree_frame.grid(row=1, column=0, sticky="nsew")
        tree_frame.columnconfigure(0, weight=1)
        tree_frame.rowconfigure(0, weight=1)

        self.tree = ttk.Treeview(
            tree_frame,
            columns=("codigo", "nome", "situacao"),
            show="headings",
            selectmode="extended",
        )
        self.tree.heading("codigo", text="Codigo")
        self.tree.heading("nome", text="Nome")
        self.tree.heading("situacao", text="Situacao")
        self.tree.column("codigo", width=120, anchor="center")
        self.tree.column("nome", width=420)
        self.tree.column("situacao", width=110, anchor="center")
        self.tree.grid(row=0, column=0, sticky="nsew")
        self.tree.bind("<Return>", self._confirm_selection)

        scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=scrollbar.set)

        button_row = ttk.Frame(self, padding=12)
        button_row.grid(row=2, column=0, sticky="ew")
        ttk.Button(button_row, text="Selecionar todas", command=self._select_all_visible).pack(side="left")
        ttk.Button(button_row, text="Limpar", command=self._clear_selection).pack(side="left", padx=(8, 0))
        ttk.Button(button_row, text="Cancelar", command=self.destroy).pack(side="right")
        ttk.Button(button_row, text="Confirmar", command=self._confirm_selection).pack(side="right", padx=(0, 8))

        search_entry.focus_set()

    def _populate_tree(self) -> None:
        selected_set = {int(company_id) for company_id in self.selected_company_ids}
        search = self.search_var.get().strip().casefold()
        self.tree.delete(*self.tree.get_children())

        for company in self.companies:
            company_text = f'{company["codigo_empresa"]} {company["nome_empresa"]}'.casefold()
            if search and search not in company_text:
                continue
            situacao = "Ativa" if company["ativa"] else "Inativa"
            company_id = str(company["id"])
            self.tree.insert(
                "",
                "end",
                iid=company_id,
                values=(company["codigo_empresa"], company["nome_empresa"], situacao),
            )
            if int(company["id"]) in selected_set:
                self.tree.selection_add(company_id)

        children = self.tree.get_children()
        if children:
            self.tree.focus(children[0])

    def _select_all_visible(self) -> None:
        children = self.tree.get_children()
        if children:
            self.tree.selection_set(children)

    def _clear_selection(self) -> None:
        selection = self.tree.selection()
        if selection:
            self.tree.selection_remove(selection)

    def _confirm_selection(self, _event=None) -> str | None:
        self.selected_company_ids = [int(item) for item in self.tree.selection()]
        self.destroy()
        return "break"

    def _center_on_parent(self) -> None:
        self.update_idletasks()
        parent = self.parent.winfo_toplevel()
        x = parent.winfo_rootx() + max((parent.winfo_width() - self.winfo_width()) // 2, 0)
        y = parent.winfo_rooty() + max((parent.winfo_height() - self.winfo_height()) // 2, 0)
        self.geometry(f"+{x}+{y}")


class CompanySelector(ttk.LabelFrame):
    """Seletor reutilizavel com busca por codigo e nome."""

    def __init__(
        self,
        master: tk.Misc,
        empresa_service,
        active_only: bool = True,
        on_selected=None,
        on_cleared=None,
        title: str = "Selecionar empresa",
    ) -> None:
        super().__init__(master, text=title, padding=10)
        self.empresa_service = empresa_service
        self.active_only = active_only
        self.on_selected = on_selected
        self.on_cleared = on_cleared
        self.selected_company_id: int | None = None
        self.companies: list[dict] = []
        self.filtered_labels: list[str] = []
        self._navigation_keys = {
            "Return",
            "Tab",
            "Shift_L",
            "Shift_R",
            "Control_L",
            "Control_R",
            "Alt_L",
            "Alt_R",
            "Escape",
            "Up",
            "Down",
            "Left",
            "Right",
            "Home",
            "End",
            "Prior",
            "Next",
        }

        self.code_var = tk.StringVar()
        self.name_var = tk.StringVar()
        self.status_var = tk.StringVar(value="Nenhuma empresa selecionada.")

        ttk.Label(self, text="Codigo").grid(row=0, column=0, sticky="w")
        self.code_entry = ttk.Entry(self, textvariable=self.code_var, width=18)
        self.code_entry.grid(row=1, column=0, sticky="ew", padx=(0, 8))
        self.code_entry.bind("<KeyRelease>", self._on_code_typed)
        self.code_entry.bind("<Return>", self._on_code_search)
        self.code_entry.bind("<FocusOut>", self._on_code_search)
        self.code_entry.bind("<F2>", self._open_company_list)

        ttk.Label(self, text="Buscar por nome").grid(row=0, column=1, sticky="w")
        self.name_combo = ttk.Combobox(self, textvariable=self.name_var)
        self.name_combo.grid(row=1, column=1, sticky="ew", padx=(0, 8))
        self.name_combo.bind("<KeyRelease>", self._on_name_typed)
        self.name_combo.bind("<<ComboboxSelected>>", self._on_name_selected)
        self.name_combo.bind("<Return>", self._on_name_selected)
        self.name_combo.bind("<FocusOut>", self._on_name_selected)
        self.name_combo.bind("<F2>", self._open_company_list)

        ttk.Button(self, text="...", width=3, command=self.open_company_list).grid(row=1, column=2, sticky="ew")
        ttk.Button(self, text="Atualizar lista", command=self.refresh_companies).grid(row=1, column=3, sticky="ew")
        ttk.Label(self, textvariable=self.status_var).grid(row=2, column=0, columnspan=4, sticky="w", pady=(8, 0))

        self.columnconfigure(1, weight=1)
        self.refresh_companies()

    def refresh_companies(self) -> None:
        self.companies = self.empresa_service.list_empresas(active_only=self.active_only)
        self.filtered_labels = [self._label(company) for company in self.companies]
        self.name_combo["values"] = self.filtered_labels

        if self.selected_company_id:
            company = next((item for item in self.companies if item["id"] == self.selected_company_id), None)
            if company:
                self._apply_selection(company)
                return

        self.clear_selection()

    def get_selected_company_id(self) -> int | None:
        return self.selected_company_id

    def clear_selection(self) -> None:
        had_selection = self.selected_company_id is not None
        self.selected_company_id = None
        self.code_var.set("")
        self.name_var.set("")
        self.status_var.set("Nenhuma empresa selecionada.")
        if had_selection and self.on_cleared:
            self.on_cleared()

    def set_company(self, company_id: int | None) -> None:
        if company_id is None:
            self.clear_selection()
            return
        company = next((item for item in self.companies if item["id"] == company_id), None)
        if company:
            self._apply_selection(company)
        else:
            self.clear_selection()

    def _label(self, company: dict) -> str:
        status = "" if company["ativa"] else " [Inativa]"
        return f'{company["codigo_empresa"]} - {company["nome_empresa"]}{status}'

    def _on_code_search(self, _event=None) -> None:
        raw_code = self.code_var.get().strip()
        if not raw_code:
            return
        company = self.empresa_service.get_empresa_by_code(raw_code, active_only=self.active_only)
        if not company:
            had_selection = self.selected_company_id is not None
            self.selected_company_id = None
            self.name_var.set("")
            self.status_var.set("Empresa nao encontrada para o codigo informado.")
            if had_selection and self.on_cleared:
                self.on_cleared()
            return
        self._apply_selection(company)

    def _on_code_typed(self, event=None) -> None:
        if event is not None and getattr(event, "keysym", "") in self._navigation_keys:
            return
        if self.selected_company_id is not None:
            self.selected_company_id = None
            self.name_var.set("")
            if self.on_cleared:
                self.on_cleared()

    def _on_name_typed(self, event=None) -> None:
        if event is not None and getattr(event, "keysym", "") in self._navigation_keys:
            return
        if self.selected_company_id is not None:
            self.selected_company_id = None
            self.code_var.set("")
            if self.on_cleared:
                self.on_cleared()
        search = self.name_var.get().strip().lower()
        if not search:
            self.name_combo["values"] = [self._label(company) for company in self.companies]
            return
        labels = [
            self._label(company)
            for company in self.companies
            if search in company["nome_empresa"].lower()
        ]
        self.name_combo["values"] = labels

    def _on_name_selected(self, _event=None) -> None:
        selected = self.name_var.get().strip()
        if not selected:
            return
        company = next((item for item in self.companies if self._label(item) == selected), None)
        if company:
            self._apply_selection(company)
            return

        search = selected.lower()
        matches = [item for item in self.companies if search in item["nome_empresa"].lower()]
        had_selection = self.selected_company_id is not None
        self.selected_company_id = None
        self.code_var.set("")
        if matches:
            self.status_var.set("Selecione uma empresa na lista de sugestoes para continuar.")
        else:
            self.status_var.set("Nenhuma sugestao encontrada para o nome informado.")
        if had_selection and self.on_cleared:
            self.on_cleared()

    def _apply_selection(self, company: dict) -> None:
        self.selected_company_id = company["id"]
        self.code_var.set(str(company["codigo_empresa"]))
        self.name_var.set(self._label(company))
        situacao = "ativa" if company["ativa"] else "inativa"
        self.status_var.set(f'Empresa selecionada: {company["nome_empresa"]} ({situacao}).')
        if self.on_selected:
            self.on_selected(company)

    def open_company_list(self) -> None:
        self.refresh_companies()
        initial_search = self.name_var.get().strip() or self.code_var.get().strip()
        dialog = CompanyListDialog(self, self.companies, initial_search=initial_search)
        self.wait_window(dialog)
        if dialog.selected_company_id is not None:
            self.set_company(dialog.selected_company_id)

    def _open_company_list(self, event=None) -> str:
        initial_search = ""
        if event is not None and getattr(event, "widget", None) is self.code_entry:
            initial_search = self.code_var.get().strip()
        elif event is not None and getattr(event, "widget", None) is self.name_combo:
            initial_search = self.name_var.get().strip()
        if initial_search:
            self.refresh_companies()
            dialog = CompanyListDialog(self, self.companies, initial_search=initial_search)
            self.wait_window(dialog)
            if dialog.selected_company_id is not None:
                self.set_company(dialog.selected_company_id)
            return "break"

        self.open_company_list()
        return "break"
