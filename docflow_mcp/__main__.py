from pathlib import Path
import sys

# Permite rodar como "python /caminho/do/projeto/docflow_mcp" de qualquer diretorio - os
# clientes MCP costumam iniciar o servidor sem definir o diretorio de trabalho.
PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from docflow_mcp.server import main  # noqa: E402

main()
