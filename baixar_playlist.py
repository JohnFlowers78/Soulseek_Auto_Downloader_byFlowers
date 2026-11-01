"""Baixa uma playlist inteira do Spotify.

    python baixar_playlist.py "https://open.spotify.com/playlist/<id>"

Lê a playlist, mostra o que vai fazer e **quanto tempo vai levar**, pede confirmação, e
aí busca e baixa faixa por faixa. No fim, as três listas: baixadas, presas na fila e
não encontradas.

Precisa de `python entrar_spotify.py` uma vez antes.
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

import sistema  # noqa: E402
from baixador import Baixador  # noqa: E402
from buscador import Buscador, ResultadoDaBusca  # noqa: E402
from config import Config  # noqa: E402
from leitor_spotify import ErroSpotify, LeitorSpotify, acesso_a_partir_do_refresh  # noqa: E402
from normalizador import nome_pasta_segura  # noqa: E402
from politica import Foco, resumir_politica  # noqa: E402
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


def _montar_relatorio(
    nome_playlist: str,
    resultados: list[ResultadoDaBusca],
    lotes: dict,
    destino: Path,
    falhas: list[tuple] | None = None,
) -> list[str]:
    """Monta o relatório como linhas, para ser impresso **e** gravado."""
    baixadas, presas, nao_vieram = [], [], []
    for resultado in resultados:
        lote = lotes.get(id(resultado))
        if lote and lote.concluidas:
            baixadas.append((resultado, lote))
        elif lote and lote.presas:
            presas.append((resultado, lote))
        else:
            nao_vieram.append(resultado)

    linhas = [
        "=" * 70,
        f"PLAYLIST TERMINADA — {nome_playlist}",
        f"{datetime.now():%d/%m/%Y %H:%M:%S}",
        f"pasta: {destino}",
        "=" * 70,
        "",
        f"✅ BAIXADAS ({len(baixadas)})",
    ]
    for resultado, lote in baixadas:
        linhas.append(f"   {resultado.faixa}")
        for transferencia in lote.concluidas:
            nome = Path(transferencia.caminho_local).name or transferencia.candidato.nome_arquivo
            linhas.append(f"      · {nome}")

    if presas:
        linhas += ["", f"⏳ PRESAS NA FILA ({len(presas)}) — usuário offline ou fila comprida"]
        for resultado, lote in presas:
            posicoes = [str(t.posicao_fila) for t in lote.presas if t.posicao_fila]
            onde = f" (posição {', '.join(posicoes)})" if posicoes else ""
            linhas.append(f"   {resultado.faixa}{onde}")

    if nao_vieram:
        linhas += ["", f"❌ NÃO ENCONTRADAS ({len(nao_vieram)})"]
        for resultado in nao_vieram:
            detalhe = ""
            if resultado.de_outro_artista:
                detalhe = f" — {len(resultado.de_outro_artista)} de outro artista"
            elif resultado.de_outra_musica:
                detalhe = f" — {len(resultado.de_outra_musica)} de outra música do artista"
            elif resultado.descartados:
                detalhe = f" — {len(resultado.descartados)} achados, nenhum passou no filtro"
            linhas.append(f"   {resultado.faixa}{detalhe}")

    if falhas:
        linhas += ["", f"💥 DERAM ERRO ({len(falhas)}) — dá para tentar estas de novo depois"]
        for faixa, motivo in falhas:
            linhas += [f"   {faixa}", f"      {motivo}"]

    return linhas


def _relatorio(
    nome_playlist: str,
    resultados: list[ResultadoDaBusca],
    lotes: dict,
    destino: Path,
    falhas: list[tuple] | None = None,
) -> None:
    """Imprime o relatório **e grava ao lado das músicas**.

    Gravar importa mais do que parece numa corrida longa: playlist grande roda por
    horas, e o histórico do terminal rola, a janela fecha, a máquina reinicia. De
    manhã, o arquivo é o que sobra para saber o que faltou.
    """
    linhas = _montar_relatorio(nome_playlist, resultados, lotes, destino, falhas)

    print()
    for linha in linhas:
        print(linha)
    print()

    try:
        destino.mkdir(parents=True, exist_ok=True)
        arquivo = destino / "_relatorio.txt"
        arquivo.write_text("\n".join(linhas) + "\n", encoding="utf-8")
        print(f"📄 Relatório gravado em:\n   {arquivo}\n")
    except OSError as erro:
        # Não gravar o relatório não pode estragar uma corrida que deu certo.
        print(f"(não consegui gravar o relatório: {erro})\n")


def _perguntar_foco(argumentos: list[str]) -> Foco:
    """Pergunta qual formato vai tocar — e portanto ganha a segunda cópia.

    A razão é de pista: tocar sempre o mesmo formato evita que a diferença de
    qualidade apareça no meio do set. A política traz um de cada tipo de todo jeito;
    o foco decide para onde vai a vaga extra.
    """
    if "--mp3" in argumentos:
        return Foco.MP3
    if "--sem-perda" in argumentos or "--sem-perguntar" in argumentos:
        return Foco.SEM_PERDA

    print()
    print("Qual formato você vai TOCAR? (a segunda cópia vai para ele)")
    print("  1 — sem perda: AIFF / WAV / FLAC   [padrão]")
    print("  2 — MP3 320")
    return Foco.MP3 if input("Escolha (1/2): ").strip() == "2" else Foco.SEM_PERDA


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

    sem_duracao = [f for f in faixas if not f.duracao_s]
    if sem_duracao:
        # A duração é o filtro que separa a faixa certa de um remix, de uma versão ao
        # vivo ou de uma sinfonia homônima. Sem ela o app fica muito mais crédulo, e o
        # usuário precisa saber disso ANTES de aceitar o que vier.
        print(
            f"\n⚠ {len(sem_duracao)} de {len(faixas)} faixa(s) vieram do Spotify SEM "
            "duração.\n  Sem ela, o filtro que compara o tamanho da gravação fica "
            "desligado para essas —\n  e versões erradas de mesmo nome passam mais fácil."
        )

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

    foco = _perguntar_foco(argumentos)
    buscador = Buscador(
        cliente,
        criterios=_criterios(config),
        quantidade_por_faixa=max(3, config.quantidade_por_faixa),
        foco=foco,
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
    #: O que foi enfileirado e ainda não terminou. A busca da próxima faixa **não**
    #: espera por isto — os downloads correm por conta do slskd enquanto a gente busca.
    pendentes: dict[int, list] = {}

    for i, faixa in enumerate(faixas, 1):
        print(f"\n[{i}/{len(faixas)}] {faixa}")
        # Cada faixa é isolada. Uma playlist de 14 já morreu na quarta porque um
        # HTTP 409 do slskd subiu até o topo e levou as outras dez junto. Erro de uma
        # faixa é problema daquela faixa — nunca da corrida.
        try:
            resultado = _buscar_e_enfileirar(faixa, buscador, operario, pendentes)
            resultados.append(resultado)
        except KeyboardInterrupt:
            raise
        except Exception as erro:  # noqa: BLE001 — o motivo vai para o relatório
            falhas.append((faixa, f"{type(erro).__name__}: {erro}"))
            print(f"   💥 falhou: {erro}")
            continue

        # Confere de passagem o que já terminou, sem esperar por nada.
        _recolher(operario, pendentes, lotes, destino, bloquear=False)

    # No fim, aí sim espera o que ficou faltando.
    if pendentes:
        print(f"\nTerminando {len(pendentes)} download(s) que ainda estão correndo...")
        _recolher(operario, pendentes, lotes, destino, bloquear=True)

    _relatorio(nome, resultados, lotes, destino, falhas)
    return 0


def _buscar_e_enfileirar(faixa, buscador, operario, pendentes) -> ResultadoDaBusca:
    """Busca **uma** faixa e põe na fila — sem esperar o download."""
    resultado = buscador.buscar_faixa(faixa)
    print(f"   {resultado.resumo()}")
    if resultado.escolhas:
        for escolha in resultado.escolhas:
            print(f"      [{escolha.papel}] {escolha.avaliacao.motivo}")

    if not resultado.escolhidos:
        return resultado

    fila = operario.enfileirar(resultado.escolhidos)
    for candidato, motivo in fila.recusados:
        print(f"   ⚠ recusado por {candidato.usuario}: {motivo}")
    if fila.aceitos:
        pendentes[id(resultado)] = fila.aceitos
    return resultado


def _recolher(operario, pendentes, lotes, destino, bloquear: bool) -> None:
    """Move para a pasta o que já terminou. Com `bloquear`, espera o resto."""
    for chave in list(pendentes):
        candidatos = pendentes[chave]
        if bloquear:
            lote = operario.acompanhar(candidatos, espera_max_s=300)
        else:
            lote = operario.conferir(candidatos)

        lotes[chave] = lote
        for caminho in operario.organizar(lote, destino):
            print(f"   ⬇ {caminho.name}")

        if bloquear or lote.tudo_terminou:
            del pendentes[chave]


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except KeyboardInterrupt:
        print("\nInterrompido — o que já baixou está na pasta.")
        raise SystemExit(130)
