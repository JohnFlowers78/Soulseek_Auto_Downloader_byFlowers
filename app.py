"""Ponto de entrada do Soulseek Auto Downloader.

Hoje abre a tela de **Configurações** — a primeira janela do app. As demais telas
(playlist, busca avulsa, acervo, comparação de espectrogramas) estão no TODO.md.

    python app.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))


def principal() -> int:
    try:
        from tela_configuracoes import abrir
    except ImportError as erro:
        print("Não consegui carregar a interface gráfica.")
        print(f"Motivo: {erro}\n")
        print("Instale as dependências com:")
        print(r"  .\.venv\Scripts\python.exe -m pip install PySide6-Essentials")
        return 1
    return abrir()


if __name__ == "__main__":
    raise SystemExit(principal())
