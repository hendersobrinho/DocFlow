from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from documentos_empresa_app.app_context import ApplicationServices
from documentos_empresa_app.utils.common import APP_NAME
from documentos_empresa_app.utils.display import get_preferred_screen_bounds
from documentos_empresa_app.utils.helpers import ValidationError
from documentos_empresa_app.utils.resources import apply_window_icon


class LoginWindow(tk.Tk):
    def __init__(self, services: ApplicationServices) -> None:
        super().__init__()
        self.services = services
        self.authenticated_user: dict | None = None

        self.username_var = tk.StringVar()
        self.password_var = tk.StringVar()

        self.title(f"{APP_NAME} - Login")
        self.resizable(False, False)
        self.protocol("WM_DELETE_WINDOW", self.close)

        self._configure_style()
        self._configure_geometry()
        apply_window_icon(self)
        self._build_layout()

    def _configure_style(self) -> None:
        style = ttk.Style(self)
        if "clam" in style.theme_names():
            style.theme_use("clam")

    def _configure_geometry(self) -> None:
        width = 420
        height = 250
        bounds = get_preferred_screen_bounds(self.winfo_pointerx(), self.winfo_pointery())
        if bounds:
            x = bounds.x + max((bounds.width - width) // 2, 0)
            y = bounds.y + max((bounds.height - height) // 2, 0)
        else:
            x = max((self.winfo_screenwidth() - width) // 2, 0)
            y = max((self.winfo_screenheight() - height) // 2, 0)
        self.geometry(f"{width}x{height}+{x}+{y}")

    def _build_layout(self) -> None:
        container = ttk.Frame(self, padding=18)
        container.pack(fill="both", expand=True)

        ttk.Label(container, text=APP_NAME, font=("TkDefaultFont", 12, "bold")).pack(anchor="w")
        ttk.Label(
            container,
            text="Informe nome de usuario e senha para entrar no sistema.",
            foreground="#4F4F4F",
        ).pack(anchor="w", pady=(4, 12))

        form = ttk.Frame(container)
        form.pack(fill="x")
        form.columnconfigure(0, weight=1)

        ttk.Label(form, text="Nome de usuario").grid(row=0, column=0, sticky="w")
        username_entry = ttk.Entry(form, textvariable=self.username_var)
        username_entry.grid(row=1, column=0, sticky="ew", pady=(0, 10))

        ttk.Label(form, text="Senha").grid(row=2, column=0, sticky="w")
        password_entry = ttk.Entry(form, textvariable=self.password_var, show="*")
        password_entry.grid(row=3, column=0, sticky="ew", pady=(0, 14))

        actions = ttk.Frame(container)
        actions.pack(fill="x")
        ttk.Button(actions, text="Entrar", command=self.login).pack(side="right")
        ttk.Button(actions, text="Sair", command=self.close).pack(side="right", padx=(0, 8))

        ttk.Label(
            container,
            text='Usuario inicial padrao: "admin" / senha: "admin".',
            foreground="#6A6A6A",
        ).pack(anchor="w", pady=(14, 0))

        username_entry.focus_set()
        self.bind("<Return>", lambda _event: self.login())

    def login(self) -> None:
        try:
            user = self.services.auth_service.authenticate(self.username_var.get(), self.password_var.get())
        except ValidationError as exc:
            messagebox.showerror(APP_NAME, str(exc), parent=self)
            self.password_var.set("")
            return

        self.services.session_service.login(user)
        self.authenticated_user = user
        self.destroy()

    def close(self) -> None:
        self.authenticated_user = None
        self.destroy()
