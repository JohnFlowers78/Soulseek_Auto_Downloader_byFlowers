"""Mostra o que a API do Spotify REALMENTE responde para uma playlist.

    python diagnostico_spotify.py "<link da playlist>"

Existe porque a divergência de pastas desta máquina me impede de ler o seu token
daqui — então, quando a API se comporta diferente do esperado, preciso que você rode
isto e me mande a saída.

**Não imprime token nem segredo.** Só status, chaves e contagens.
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from config import Config  # noqa: E402
from leitor_spotify import (  # noqa: E402
    API,
    ErroSpotify,
    acesso_a_partir_do_refresh,
    extrair_id_da_playlist,
    lista_de_itens,
)


def chamar_cru(url: str, token: str) -> tuple[int, str, object]:
    """Devolve (status, texto do erro, corpo) sem traduzir nada."""
    pedido = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(pedido, timeout=30) as resposta:
            bruto = resposta.read().decode("utf-8")
            corpo = json.loads(bruto) if bruto.strip() else None
            return resposta.status, "", corpo
    except urllib.error.HTTPError as erro:
        try:
            detalhe = erro.read().decode("utf-8")[:500]
        except Exception:  # noqa: BLE001
            detalhe = ""
        return erro.code, detalhe, None
    except Exception as erro:  # noqa: BLE001
        return 0, f"{type(erro).__name__}: {erro}", None


def descrever(corpo) -> str:
    if corpo is None:
        return "(corpo vazio)"
    if isinstance(corpo, dict):
        partes = []
        for chave, valor in corpo.items():
            if isinstance(valor, list):
                partes.append(f"{chave}=[{len(valor)} item(ns)]")
            elif isinstance(valor, dict):
                partes.append(f"{chave}={{{len(valor)} chave(s)}}")
            else:
                texto = repr(valor)
                partes.append(f"{chave}={texto[:40]}")
        return ", ".join(partes)
    return f"{type(corpo).__name__} com {len(corpo)}" if hasattr(corpo, "__len__") else repr(corpo)


def main(argumentos: list[str]) -> int:
    if not argumentos:
        print(__doc__)
        return 2

    id_playlist = extrair_id_da_playlist(argumentos[0])
    if not id_playlist:
        print("Não reconheci o link.")
        return 1

    config = Config.carregar()
    try:
        token, _ = acesso_a_partir_do_refresh(
            config.spotify_client_id, config.spotify_refresh_token
        )
    except ErroSpotify as erro:
        print(f"❌ {erro}")
        return 1

    print(f"playlist: {id_playlist}\n")

    enderecos = [
        ("a playlist em si", f"{API}/playlists/{id_playlist}"),
        ("só o nome", f"{API}/playlists/{id_playlist}?fields=name"),
        ("/tracks", f"{API}/playlists/{id_playlist}/tracks?limit=5"),
        ("/items", f"{API}/playlists/{id_playlist}/items?limit=5"),
        ("minhas playlists", f"{API}/me/playlists?limit=5"),
    ]

    for rotulo, url in enderecos:
        status, erro, corpo = chamar_cru(url, token)
        print(f"── {rotulo}")
        print(f"   {url.replace(API, '')}")
        print(f"   HTTP {status}")
        if erro:
            print(f"   erro: {erro[:300]}")
        else:
            print(f"   {descrever(corpo)}")

        # Mostra o formato de UM item, achando a lista onde quer que ela esteja.
        itens = lista_de_itens(corpo)
        if itens:
            primeiro = itens[0]
            print(f"   {len(itens)} item(ns); chaves do item: {sorted(primeiro.keys())}")
            faixa = primeiro.get("track") or primeiro.get("item")
            if isinstance(faixa, dict):
                print(f"   chaves da faixa: {sorted(faixa.keys())[:14]}")
                print(
                    f"   exemplo: {faixa.get('name')!r} — "
                    f"{[a.get('name') for a in faixa.get('artists') or []]}"
                )
            else:
                print(f"   nem 'track' nem 'item' é dicionário: {type(faixa).__name__}")
        elif isinstance(corpo, dict):
            # Nenhuma lista achada: mostra onde o conteúdo pode estar escondido.
            for chave in ("items", "tracks"):
                valor = corpo.get(chave)
                if isinstance(valor, dict):
                    print(f"   '{chave}' é objeto de paginação: {sorted(valor.keys())}")
                    print(f"      total={valor.get('total')}  next={bool(valor.get('next'))}")
        print()

    print("Pode colar esta saída inteira — não há token nem segredo aqui.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
