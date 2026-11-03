from __future__ import annotations

import os
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

import main as app_main  # noqa: E402
from documentos_empresa_app.qt_ui.splash_screen import SplashScreen  # noqa: E402

APP = QApplication.instance() or QApplication([])


class FirstRunTests(unittest.TestCase):
    """Computador novo, sem banco configurado: a configuracao do banco tem que aparecer na
    frente, e nao escondida atras da tela de carregamento (que fica sempre por cima)."""

    def test_database_setup_is_not_hidden_behind_the_splash(self) -> None:
        visivel_durante_configuracao = []

        def configurar_banco(*_args, **_kwargs):
            splashes = [w for w in QApplication.topLevelWidgets() if isinstance(w, SplashScreen)]
            visivel_durante_configuracao.extend(s.isVisible() for s in splashes)
            return None  # usuario cancela

        with mock.patch.object(app_main, "resolve_database_conninfo", return_value=None), \
                mock.patch.object(app_main, "ensure_database_connection_qt", side_effect=configurar_banco), \
                mock.patch.object(app_main.QApplication, "exec", return_value=0), \
                mock.patch.object(app_main, "QApplication", return_value=APP):
            app_main.main()

        self.assertTrue(visivel_durante_configuracao)
        self.assertFalse(any(visivel_durante_configuracao))


if __name__ == "__main__":
    unittest.main()
