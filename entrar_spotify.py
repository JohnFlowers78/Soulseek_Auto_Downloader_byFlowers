"""Entra na sua conta do Spotify — uma vez só.

    python entrar_spotify.py

Abre o navegador, você autoriza, e o app guarda um *refresh token* para não precisar
pedir de novo. Usa **PKCE**, então o *Client Secret* não é necessário — só o Client ID.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from config import Config  # noqa: E402
from leitor_spotify import (  # noqa: E402
    REDIRECIONAMENTO,
    ErroSpotify,
    LeitorSpotify,
    autorizar_no_navegador,
)


def main() -> int:
    config = Config.carregar()

    client_id = config.spotify_client_id.strip()
    if not client_id:
        print("Falta o Client ID do Spotify.\n")
        print("1. Entre em https://developer.spotify.com/dashboard")
        print("2. Create app → marque Web API")
        print(f"3. Redirect URI, exatamente: {REDIRECIONAMENTO}")
        print("4. Copie o Client ID e cole nas Configurações (python app.py), aba 🎧 Spotify")
        print("\nOu cole aqui agora:")
        client_id = input("Client ID: ").strip()
        if not client_id:
            return 1
        config.spotify_client_id = client_id

    print(f"\nClient ID: {client_id}")
    print(f"Redirect URI esperado no painel: {REDIRECIONAMENTO}")
    print("(se não bater exatamente, o Spotify recusa com INVALID_CLIENT)\n")

    try:
        tokens = autorizar_no_navegador(client_id)
    except ErroSpotify as erro:
        print(f"❌ {erro}")
        return 1

    config.spotify_refresh_token = tokens.get("refresh_token", "")
    onde = config.salvar()

    print("✅ Entrou.")
    print(f"   token guardado em: {onde}")

    # Confirma de verdade: um token que não lê nada não serve de prova.
    try:
        leitor = LeitorSpotify(tokens["access_token"])
        eu = leitor._get("https://api.spotify.com/v1/me")
        # `product` (free/premium) só vem com o escopo `user-read-private`, que não
        # pedimos — não precisamos saber o plano para ler playlist. Então some, em vez
        # de mostrar um "(?)" que parece defeito.
        nome = eu.get("display_name") or eu.get("id") or "(sem nome)"
        print(f"   conta: {nome}")
    except ErroSpotify as erro:
        print(f"   ⚠ entrou, mas não consegui ler a conta: {erro}")

    print("\nAgora dá para baixar uma playlist inteira:")
    print('   .\\.venv\\Scripts\\python.exe baixar_playlist.py "<link da playlist>"')
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nCancelado.")
        raise SystemExit(130)
