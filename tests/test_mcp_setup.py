from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from documentos_empresa_app.utils import mcp_setup


class McpSetupTests(unittest.TestCase):
    def setUp(self) -> None:
        pasta = tempfile.TemporaryDirectory()
        self.addCleanup(pasta.cleanup)
        self.raiz = Path(pasta.name)
        self.appdata = self.raiz / "Roaming"
        self.local = self.raiz / "Local"
        (self.appdata / "Claude").mkdir(parents=True)
        (self.local / "Packages" / "Claude_abc123" / "LocalCache" / "Roaming" / "Claude").mkdir(parents=True)
        ambiente = mock.patch.dict("os.environ", {"APPDATA": str(self.appdata), "LOCALAPPDATA": str(self.local)})
        ambiente.start()
        self.addCleanup(ambiente.stop)
        self.config: dict = {}
        for nome, fn in (("load_config", lambda: json.loads(json.dumps(self.config))),
                         ("save_config", lambda c: self.config.update(c))):
            patcher = mock.patch.object(mcp_setup, nome, fn)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_finds_store_and_regular_claude_configs(self) -> None:
        locais = mcp_setup.claude_config_locations()
        self.assertEqual([l["tipo"] for l in locais], ["Claude da Microsoft Store", "Claude (instalador do site)"])
        self.assertIn("Claude_abc123", str(locais[0]["caminho"]))
        self.assertEqual(locais[1]["caminho"], self.appdata / "Claude" / "claude_desktop_config.json")

    def test_connect_fixes_old_folder_and_keeps_other_servers(self) -> None:
        arquivo = mcp_setup.claude_config_locations()[0]["caminho"]
        arquivo.write_text(json.dumps({
            "mcpServers": {
                "outro": {"command": "node", "args": ["x.js"]},
                "docflow": {
                    "command": r"C:\pasta-antiga\python.exe",
                    "args": [r"C:\pasta-antiga\docflow_mcp"],
                    "env": {"DOCFLOW_MCP_USUARIO": "mcp", "DOCFLOW_MCP_SENHA": "segredo", "DOCFLOW_DATABASE_URL": "x"},
                },
            },
            "preferencia": True,
        }), encoding="utf-8")
        antes = mcp_setup.inspect_config(arquivo)
        self.assertTrue(antes["tem_docflow"])
        self.assertFalse(antes["desta_instalacao"])
        self.assertFalse(antes["programa_existe"])
        self.assertTrue(antes["senha_no_arquivo"])

        copia = mcp_setup.write_config(arquivo)

        dados = json.loads(arquivo.read_text(encoding="utf-8"))
        self.assertEqual(dados["mcpServers"]["outro"], {"command": "node", "args": ["x.js"]})
        self.assertTrue(dados["preferencia"])
        docflow = dados["mcpServers"]["docflow"]
        self.assertEqual((docflow["command"], docflow["args"]), mcp_setup.server_command())
        self.assertEqual(docflow["env"], {"DOCFLOW_DATABASE_URL": "x"})  # senha saiu do arquivo
        self.assertIn("segredo", copia.read_text(encoding="utf-8"))  # copia do anterior ao lado
        depois = mcp_setup.inspect_config(arquivo)
        self.assertTrue(depois["desta_instalacao"])
        self.assertFalse(depois["senha_no_arquivo"])

    def test_creates_missing_file(self) -> None:
        arquivo = mcp_setup.claude_config_locations()[1]["caminho"]
        self.assertFalse(mcp_setup.inspect_config(arquivo)["existe"])
        self.assertIsNone(mcp_setup.write_config(arquivo))
        self.assertIn("docflow", json.loads(arquivo.read_text(encoding="utf-8"))["mcpServers"])

    def test_credentials_are_saved_protected_and_kept_when_password_blank(self) -> None:
        with mock.patch.object(mcp_setup, "protect_secret", lambda s: f"protegido:{s}"), \
                mock.patch.object(mcp_setup, "unprotect_secret", lambda s: s.split(":", 1)[1] if s else s):
            mcp_setup.save_mcp_credentials(" claude ", "senha1")
            self.assertEqual(self.config["mcp_conexao"]["senha"], "protegido:senha1")
            mcp_setup.save_mcp_credentials("claude", "")
            self.assertEqual(mcp_setup.load_mcp_credentials(), ("claude", "senha1"))


if __name__ == "__main__":
    unittest.main()
