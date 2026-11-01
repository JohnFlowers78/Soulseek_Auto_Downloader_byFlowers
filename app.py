"""Ponto de entrada do Soulseek Auto Downloader.

    python app.py

Abre a janela com tudo: baixar playlist ou música avulsa, ligar o motor (o slskd em
segundo plano, **sem terminal**) e as Configurações. Os comandos de linha continuam
existindo (`baixar.py`, `baixar_playlist.py`) para quem preferir, mas a janela não
depende deles.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))


def principal() -> int:
    try:
        from tela_principal import abrir
    except ImportError as erro:
        print("Não consegui carregar a interface gráfica.")
        print(f"Motivo: {erro}\n")
        print("Instale as dependências com:")
        print(r"  .\.venv\Scripts\python.exe -m pip install PySide6-Essentials")
        return 1
    return abrir()


if __name__ == "__main__":
    raise SystemExit(principal())
