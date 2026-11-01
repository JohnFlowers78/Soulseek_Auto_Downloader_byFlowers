"""Baixa uma playlist inteira do Spotify.

    python baixar_playlist.py "https://open.spotify.com/playlist/<id>"

Lê a playlist, mostra o que vai fazer e **quanto tempo vai levar**, pede confirmação, e
aí busca e baixa faixa por faixa. No fim, as três listas: baixadas, presas na fila e
não encontradas.

Precisa de `python entrar_spotify.py` uma vez antes.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

import sistema  # noqa: E402
from baixador import Baixador  # noqa: E402
from buscador import Buscador, ResultadoDaBusca  # noqa: E402
from config import Config  # noqa: E402
from leitor_spotify import ErroSpotify, LeitorSpotify, acesso_a_partir_do_refresh  # noqa: E402
from normalizador import nome_pasta_segura  # noqa: E402
from qualidade import Criterios  # noqa: E402
from slskd_cliente import ClienteSlskd, ErroSlskd  # noqa: E402


def _criterios(config: Config) -> Criterios:
    padrao = Criterios()
    sem_perda = tuple(f for f in config.formatos_aceitos if f in padrao.formatos_sem_perda)
    com_perda = tuple(f for f in config.formatos_aceitos if f in padrao.formatos_com_perda)
    return Criterios(
        formatos_sem_perda=sem_perda or padrao.formatos_sem_perda,
        formatos_com_perda=com_perda or padrao.formatos_com_perda,
        minimo_mp3_kbps=config.minimo_mp3_kbps,
        minimo_aac_kbps=config.minimo_aac_kbps,
    )


def _tempo_legivel(segundos: float) -> str:
    minutos = int(segundos // 60)
    if minutos < 1:
        return f"{int(segundos)} s"
    if minutos < 60:
        return f"{minutos} min"
    return f"{minutos // 60}h{minutos % 60:02d}"


def _relatorio(
    resultados: list[ResultadoDaBusca],
    lotes: dict,
    destino: Path,
    falhas: list[tuple] | None = None,
) -> None:
    baixadas, presas, nao_vieram = [], [], []
    for resultado in resultados:
        lote = lotes.get(id(resultado))
        if lote and lote.concluidas:
            baixadas.append((resultado, lote))
        elif lote and lote.presas:
            presas.append((resultado, lote))
        else:
            nao_vieram.append(resultado)

    print("\n" + "=" * 70)
    print(f"PLAYLIST TERMINADA — {destino}")
    print("=" * 70)

    print(f"\n✅ BAIXADAS ({len(baixadas)})")
    for resultado, lote in baixadas:
        print(f"   {resultado.faixa}")
        for transferencia in lote.concluidas:
            print(f"      · {Path(transferencia.caminho_local).name or transferencia.candidato.nome_arquivo}")

    if presas:
        print(f"\n⏳ PRESAS NA FILA ({len(presas)}) — usuário offline ou fila comprida")
        for resultado, lote in presas:
            posicoes = [str(t.posicao_fila) for t in lote.presas if t.posicao_fila]
            onde = f" (posição {', '.join(posicoes)})" if posicoes else ""
            print(f"   {resultado.faixa}{onde}")

    if nao_vieram:
        print(f"\n❌ NÃO ENCONTRADAS ({len(nao_vieram)})")
        for resultado in nao_vieram:
            detalhe = ""
            if resultado.de_outro_artista:
                detalhe = f" — {len(resultado.de_outro_artista)} de outro artista"
            elif resultado.de_outra_musica:
                detalhe = f" — {len(resultado.de_outra_musica)} de outra música do artista"
            elif resultado.descartados:
                detalhe = f" — {len(resultado.descartados)} achados, nenhum passou no filtro"
            print(f"   {resultado.faixa}{detalhe}")

    if falhas:
        print(f"\n💥 DERAM ERRO ({len(falhas)}) — dá para tentar estas de novo depois")
        for faixa, motivo in falhas:
            print(f"   {faixa}")
            print(f"      {motivo}")

    print()


def main(argumentos: list[str]) -> int:
    links = [a for a in argumentos if not a.startswith("--")]
    if not links:
        print(__doc__)
        return 2

    config = Config.carregar()
    if not config.pasta_mae_playlists.strip():
        print("Falta definir a pasta das playlists nas Configurações (python app.py).")
        return 1

    # --- Spotify -----------------------------------------------------------
    try:
        acesso, refresh = acesso_a_partir_do_refresh(
            config.spotify_client_id, config.spotify_refresh_token
        )
    except ErroSpotify as erro:
        print(f"❌ {erro}")
        return 1
    if refresh != config.spotify_refresh_token:
        config.spotify_refresh_token = refresh
        config.salvar()

    print("Lendo a playlist...")
    try:
        nome, faixas = LeitorSpotify(acesso).ler(links[0])
    except ErroSpotify as erro:
        print(f"❌ {erro}")
        return 1

    if not faixas:
        print(f"\n⚠ A playlist '{nome}' veio sem nenhuma faixa.")
        print()
        print("Playlist PRIVADA não é problema — suas playlists privadas funcionam.")
        print("O que a API não entrega, desde fev/2026, é o conteúdo de playlist de")
        print("OUTRA PESSOA, por mais pública que seja. A regra é dono, não visibilidade.")
        print()
        print("Se esta playlist é sua mesmo, pode ser que ela esteja realmente vazia,")
        print("ou que só tenha podcast (episódio não é faixa de música).")
        print()
        print("Se tem faixa e mesmo assim veio vazia, rode o diagnóstico e me mande:")
        print(f'   .\\.venv\\Scripts\\python.exe diagnostico_spotify.py "{links[0]}"')
        return 1

    print(f"\n📋 {nome} — {len(faixas)} faixa(s)\n")
    for i, faixa in enumerate(faixas[:10], 1):
        print(f"   {i:3d}. {faixa}")
    if len(faixas) > 10:
        print(f"   ... e mais {len(faixas) - 10}")

    # --- slskd -------------------------------------------------------------
    cliente = ClienteSlskd(url=config.slskd_url, chave_api=config.slskd_api_key)
    try:
        if not cliente.conectado():
            print("\n❌ o slskd não está logado na rede Soulseek. Ligue o motor primeiro.")
            return 1
    except ErroSlskd as erro:
        print(f"\n❌ {erro}")
        return 1

    buscador = Buscador(
        cliente, criterios=_criterios(config), quantidade_por_faixa=config.quantidade_por_faixa
    )
    estimativa = buscador.tempo_estimado_s(len(faixas))
    print(f"\n⏱  Busca: ~{_tempo_legivel(estimativa)} (limite da rede + tempo de cada busca).")
    print("   O download de cada faixa entra por cima disso.")

    if "--sem-perguntar" not in argumentos:
        if input("\nComeçar? (s/N) ").strip().lower() != "s":
            print("Cancelado.")
            return 0

    # --- a maratona --------------------------------------------------------
    destino = Path(config.pasta_mae_playlists) / nome_pasta_segura(nome)
    passagem = (sistema.encontrar_slskd() or Path()).parent / "dados" / "downloads"
    operario = Baixador(cliente, passagem)

    resultados: list[ResultadoDaBusca] = []
    lotes: dict = {}

    falhas: list[tuple[Faixa, str]] = []

    for i, faixa in enumerate(faixas, 1):
        print(f"\n[{i}/{len(faixas)}] {faixa}")
        # Cada faixa é isolada. Uma playlist de 14 já morreu na quarta porque um
        # HTTP 409 do slskd subiu até o topo e levou as outras dez junto. Erro de uma
        # faixa é problema daquela faixa — nunca da corrida.
        try:
            resultado = _processar(faixa, buscador, operario, destino, lotes)
            resultados.append(resultado)
        except KeyboardInterrupt:
            raise
        except Exception as erro:  # noqa: BLE001 — o motivo vai para o relatório
            falhas.append((faixa, f"{type(erro).__name__}: {erro}"))
            print(f"   💥 falhou: {erro}")

    _relatorio(resultados, lotes, destino, falhas)
    return 0


def _processar(faixa, buscador, operario, destino, lotes) -> ResultadoDaBusca:
    """Busca, enfileira, acompanha e organiza **uma** faixa."""
    resultado = buscador.buscar_faixa(faixa)
    print(f"   {resultado.resumo()}")

    if not resultado.escolhidos:
        return resultado

    fila = operario.enfileirar(resultado.escolhidos)
    for candidato, motivo in fila.recusados:
        print(f"   ⚠ recusado por {candidato.usuario}: {motivo}")
    if not fila.aceitos:
        return resultado

    lote = operario.acompanhar(fila.aceitos, espera_max_s=300)
    lotes[id(resultado)] = lote
    for caminho in operario.organizar(lote, destino):
        print(f"   ⬇ {caminho.name}")
    return resultado


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except KeyboardInterrupt:
        print("\nInterrompido — o que já baixou está na pasta.")
        raise SystemExit(130)
