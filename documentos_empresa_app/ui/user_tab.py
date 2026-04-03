from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from documentos_empresa_app.utils.helpers import ValidationError


class UserTab(ttk.Frame):
    def __init__(self, master, services, on_data_changed) -> None:
        super().__init__(master, padding=12)
        self.services = services
        self.on_data_changed = on_data_changed
        self.selected_user_id: int | None = None

        self.username_var = tk.StringVar()
        self.password_var = tk.StringVar()
        self.tipo_var = tk.StringVar(value="comum")
        self.ativo_var = tk.BooleanVar(value=True)

        self._build_layout()

    def _build_layout(self) -> None:
        form = ttk.LabelFrame(self, text="Cadastro de usuarios", padding=12)
        form.pack(fill="x", pady=(0, 12))

        ttk.Label(form, text="Nome de usuario").grid(row=0, column=0, sticky="w")
        ttk.Entry(form, textvariable=self.username_var).grid(row=1, column=0, sticky="ew", padx=(0, 10))

        ttk.Label(form, text="Senha").grid(row=0, column=1, sticky="w")
        ttk.Entry(form, textvariable=self.password_var, show="*").grid(row=1, column=1, sticky="ew", padx=(0, 10))

        ttk.Label(form, text="Tipo").grid(row=0, column=2, sticky="w")
        self.tipo_combo = ttk.Combobox(form, textvariable=self.tipo_var, state="readonly", values=("admin", "comum"))
        self.tipo_combo.grid(row=1, column=2, sticky="ew", padx=(0, 10))

        ttk.Checkbutton(form, text="Usuario ativo", variable=self.ativo_var).grid(
            row=1, column=3, sticky="w", padx=(0, 10)
        )

        self.save_button = ttk.Button(form, text="Cadastrar usuario", command=self.save_user)
        self.save_button.grid(row=1, column=4, sticky="ew", padx=(0, 8))
        ttk.Button(form, text="Limpar", command=self.clear_form).grid(row=1, column=5, sticky="ew")

        ttk.Label(
            form,
            text="Na edicao, deixe a senha em branco para manter a atual.",
            foreground="#5A5A5A",
        ).grid(row=2, column=0, columnspan=6, sticky="w", pady=(8, 0))

        form.columnconfigure(0, weight=1)
        form.columnconfigure(1, weight=1)

        list_frame = ttk.LabelFrame(self, text="Usuarios cadastrados", padding=10)
        list_frame.pack(fill="both", expand=True)

        self.tree = ttk.Treeview(
            list_frame,
            columns=("username", "tipo", "situacao", "criado_em"),
            show="headings",
            selectmode="browse",
        )
        self.tree.heading("username", text="Usuario")
        self.tree.heading("tipo", text="Tipo")
        self.tree.heading("situacao", text="Situacao")
        self.tree.heading("criado_em", text="Criado em")
        self.tree.column("username", width=240)
        self.tree.column("tipo", width=120, anchor="center")
        self.tree.column("situacao", width=120, anchor="center")
        self.tree.column("criado_em", width=180, anchor="center")
        self.tree.pack(side="left", fill="both", expand=True)
        self.tree.bind("<<TreeviewSelect>>", self.load_selected_user)

        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.tree.yview)
        scrollbar.pack(side="right", fill="y")
        self.tree.configure(yscrollcommand=scrollbar.set)

    def refresh_data(self) -> None:
        self.tree.delete(*self.tree.get_children())
        try:
            users = self.services.user_service.list_users()
        except ValidationError:
            return
        for user in users:
            situacao = "Ativo" if user["ativa"] else "Inativo"
            self.tree.insert(
                "",
                "end",
                iid=str(user["id"]),
                values=(user["username"], user["tipo_usuario"], situacao, user["criado_em"]),
            )

    def load_selected_user(self, _event=None) -> None:
        selection = self.tree.selection()
        if not selection:
            return
        self.selected_user_id = int(selection[0])
        user = self.services.user_service.get_user(self.selected_user_id)
        self.username_var.set(user["username"])
        self.password_var.set("")
        self.tipo_var.set(user["tipo_usuario"])
        self.ativo_var.set(bool(user["ativa"]))
        self.save_button.configure(text="Salvar alteracoes")

    def clear_form(self) -> None:
        self.selected_user_id = None
        self.username_var.set("")
        self.password_var.set("")
        self.tipo_var.set("comum")
        self.ativo_var.set(True)
        self.save_button.configure(text="Cadastrar usuario")
        selection = self.tree.selection()
        if selection:
            self.tree.selection_remove(*selection)

    def save_user(self) -> None:
        try:
            if self.selected_user_id:
                password = self.password_var.get().strip()
                self.services.user_service.update_user(
                    self.selected_user_id,
                    self.username_var.get(),
                    self.tipo_var.get(),
                    self.ativo_var.get(),
                    password=password if password else None,
                )
                messagebox.showinfo("Usuarios", "Usuario atualizado com sucesso.", parent=self)
            else:
                self.services.user_service.create_user(
                    self.username_var.get(),
                    self.password_var.get(),
                    self.tipo_var.get(),
                    ativo=self.ativo_var.get(),
                )
                messagebox.showinfo("Usuarios", "Usuario cadastrado com sucesso.", parent=self)
        except ValidationError as exc:
            messagebox.showerror("Usuarios", str(exc), parent=self)
            return

        self.clear_form()
        self.on_data_changed()
