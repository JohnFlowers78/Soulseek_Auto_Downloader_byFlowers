"""O que muda entre Windows e macOS, isolado num módulo só.

Existe desde cedo de propósito: enquanto tudo passar por aqui, a versão macOS é um
**porte** e não uma reescrita (ver ARQUITETURA.md). Nenhum outro módulo deve escrever
``C:\\`` na mão nem montar caminho com barra invertida.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

NOME_DO_APP = "SoulseekAutoDownloader"


def eh_windows() -> bool:
    return sys.platform.startswith("win")


def eh_mac() -> bool:
    return sys.platform == "darwin"


def nome_do_sistema() -> str:
    if eh_windows():
        return "Windows"
    if eh_mac():
        return "macOS"
    return sys.platform


def pasta_de_dados() -> Path:
    """Onde ficam configurações, fila e histórico — **fora** da pasta do programa.

    Separar isso não é preciosismo: é o que permite o pacote atualizador trocar os
    arquivos do programa sem nunca encostar nos dados do usuário.
    """
    if eh_windows():
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    elif eh_mac():
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / NOME_DO_APP


def pasta_de_musicas_padrao() -> Path:
    """Um destino inicial plausível, só para o campo não nascer vazio."""
    return Path.home() / "Music" / "Soulseek Auto Downloader"


#: Lugares onde o ffmpeg costuma se instalar no Windows sem entrar no PATH.
_LUGARES_PROVAVEIS = (
    Path(r"C:\ffmpeg\bin"),
    Path(r"C:\Program Files\ffmpeg\bin"),
    Path(r"C:\ProgramData\chocolatey\bin"),
    Path.home() / "scoop" / "shims",
    Path("/opt/homebrew/bin"),
    Path("/usr/local/bin"),
)


def encontrar_programa(nome: str) -> Path | None:
    """Procura um programa no PATH e, se não achar, nos lugares onde ele costuma estar.

    A segunda parte existe porque instalar o ffmpeg no Windows e **esquecer de colocar no
    PATH** é o desfecho mais comum — e é frustrante o app dizer "não instalado" quando o
    programa está ali, dois diretórios ao lado.
    """
    achado = shutil.which(nome)
    if achado:
        return Path(achado)

    sufixos = (".exe", ".bat", "") if eh_windows() else ("",)
    for pasta in _LUGARES_PROVAVEIS:
        for sufixo in sufixos:
            candidato = pasta / f"{nome}{sufixo}"
            try:
                if candidato.is_file():
                    return candidato
            except OSError:
                continue
    return None


def encontrar_ffmpeg() -> Path | None:
    return encontrar_programa("ffmpeg")


def encontrar_ffprobe() -> Path | None:
    return encontrar_programa("ffprobe")
