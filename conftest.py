"""Deixa os módulos de `src/` importáveis pelos testes sem precisar instalar o pacote."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))
