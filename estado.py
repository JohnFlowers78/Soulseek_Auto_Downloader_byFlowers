"""Mostra o estado real do app nesta máquina — para parar de adivinhar.

    python estado.py

Imprime o que está configurado, o que falta, e onde cada coisa mora. **Nenhum segredo
é impresso** — só se o campo está preenchido e há quantos caracteres.
"""

from __future__ import annotations

import json
import socket
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

import sistema  # noqa: E402
from config import Config  # noqa: E402
from slskd_cliente import ler_chave_do_yml  # noqa: E402


def marca(valor) -> str:
    return "✅" if valor else "⬜"


def segredo(valor: str) -> str:
    return f"✅ preenchido ({len(valor)} caracteres)" if valor else "⬜ VAZIO"


def pasta(caminho: str) -> str:
    if not caminho.strip():
        return "⬜ não definida"
    p = Path(caminho)
    if not p.is_dir():
        return f"❌ NÃO EXISTE — {caminho}"
    quantos = sum(1 for _ in p.iterdir())
    return f"✅ {caminho}  ({quantos} item(ns))"


def porta_aberta(porta: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", porta)) == 0


def main() -> int:
    caminho_config = Config.caminho_padrao()
    config = Config.carregar()

    print("=" * 68)
    print("ESTADO DO SOULSEEK AUTO DOWNLOADER")
    print("=" * 68)

    print(f"\nmáquina ......: {sistema.nome_do_sistema()}")
    print(f"config .......: {caminho_config}")
    if caminho_config.exists():
        quando = datetime.fromtimestamp(caminho_config.stat().st_mtime)
        tamanho = caminho_config.stat().st_size
        print(f"                existe, {tamanho} bytes, salvo em {quando:%d/%m/%Y %H:%M:%S}")
        try:
            chaves = sorted(json.loads(caminho_config.read_text(encoding="utf-8")))
            print(f"                campos no arquivo: {len(chaves)}")
        except Exception as erro:  # noqa: BLE001
            print(f"                ⚠ não consegui ler: {erro}")
    else:
        print("                ❌ NÃO EXISTE")

    print("\n── Pastas")
    print(f"  playlists ....: {pasta(config.pasta_mae_playlists)}")
    print(f"  acervo .......: {pasta(config.pasta_mae_acervo)}")
    print(f"  compartilhada : {pasta(config.pasta_compartilhada)}")
    dias = config.dias_desde_confirmacao()
    if dias is None:
        print("  confirmação ..: ⬜ nunca confirmada")
    else:
        aviso = " ⚠ passou do prazo" if config.precisa_revalidar_compartilhada() else ""
        print(f"  confirmação ..: há {dias} dia(s){aviso}")

    print("\n── Spotify")
    print(f"  client id ....: {config.spotify_client_id or '⬜ VAZIO'}")
    print(f"  client secret : {segredo(config.spotify_client_secret)}  (não é necessário com PKCE)")
    print(f"  refresh token : {segredo(config.spotify_refresh_token)}")
    if not config.spotify_refresh_token:
        print("                  → rode: python entrar_spotify.py")

    print("\n── Soulseek / slskd")
    executavel = sistema.encontrar_slskd()
    print(f"  programa .....: {marca(executavel)} {executavel or 'não encontrado'}")
    print(f"  chave no app .: {segredo(config.slskd_api_key)}")
    do_yml = ler_chave_do_yml()
    print(f"  chave no yml .: {segredo(do_yml)}")
    if do_yml and config.slskd_api_key and do_yml != config.slskd_api_key:
        print("                  ⚠ as duas são DIFERENTES — o app usa a do config")
    rodando = porta_aberta(5030)
    print(f"  rodando ......: {marca(rodando)} {'porta 5030 atende' if rodando else 'porta 5030 fechada'}")
    if not rodando and executavel:
        print(f'                  → & "{executavel}" --app-dir "{executavel.parent / "dados"}"')

    print("\n── Programas de sistema")
    for nome, achar in (("ffmpeg", sistema.encontrar_ffmpeg), ("ffprobe", sistema.encontrar_ffprobe)):
        achado = achar()
        print(f"  {nome:8}....: {marca(achado)} {achado or 'não encontrado'}")

    pendencias = config.problemas()
    print(f"\n── Pendências ({len(pendencias)})")
    for p in pendencias:
        print(f"  • {p}")
    if not pendencias:
        print("  nenhuma 🎉")

    print("\nPode colar esta saída inteira — não há segredo aqui.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
