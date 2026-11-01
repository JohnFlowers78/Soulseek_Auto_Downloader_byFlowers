"""Baixa uma música pelo terminal — a corrente inteira, sem tela e sem Spotify.

    python baixar.py "Djavan" "Não Vou Ficar"
    python baixar.py "Djavan - Não Vou Ficar"

Escreva o nome **completo e bonito**, com todo acento, apóstrofo, hífen e til que a
música realmente tem. Não "limpe" nada: é justamente da grafia completa que saem as
variantes de busca.

Existe por dois motivos. Primeiro, prova a corrente de ponta a ponta (buscar → filtrar →
escolher → baixar → organizar) antes de a tela principal existir. Segundo, é a mesma
coisa que a tela vai fazer — então o que funcionar aqui já está pronto lá.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

import sistema  # noqa: E402
from baixador import Baixador  # noqa: E402
from buscador import Buscador  # noqa: E402
from config import Config  # noqa: E402
# O mesmo extrator que lê nome de arquivo serve para o nome digitado: ele divide em
# " - ", respeita hífen dentro do nome da banda (Blink-182) e tira selo de qualidade.
from leitor_pasta import extrair_do_nome  # noqa: E402
from modelos import EstadoTransferencia, Faixa  # noqa: E402
from normalizador import nome_pasta_segura  # noqa: E402
from qualidade import Criterios  # noqa: E402
from slskd_cliente import ClienteSlskd, ErroSlskd  # noqa: E402

PASTA_DAS_AVULSAS = "Buscas avulsas"


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


def _mostrar_achados(resultado) -> None:
    print(f"\n{resultado.resumo()}\n")

    if resultado.escolhidos:
        print("Vou baixar:")
        for i, avaliacao in enumerate(resultado.escolhidos, 1):
            c = avaliacao.candidato
            fila = f", fila {c.posicao_fila}" if c.posicao_fila else ""
            slot = "slot livre" if c.slot_livre else "sem slot"
            print(f"  {i}. {c.nome_arquivo}")
            print(f"     {avaliacao.motivo} — de {c.usuario} ({slot}{fila})")

    outros = [a for a in resultado.aprovados if a not in resultado.escolhidos]
    if outros:
        print(f"\nOutras {len(outros)} opção(ões) aprovadas (não escolhidas):")
        for avaliacao in outros[:5]:
            print(f"  · {avaliacao.motivo} — de {avaliacao.candidato.usuario}")

    if resultado.descartados and not resultado.escolhidos:
        print("\nAchei estes, mas nenhum passou no filtro:")
        for avaliacao in resultado.descartados[:8]:
            print(f"  ✗ {avaliacao.candidato.nome_arquivo}")
            print(f"     {avaliacao.motivo}")

    if resultado.de_outra_musica:
        print(
            f"\n🚫 {len(resultado.de_outra_musica)} arquivo(s) do artista certo, mas de "
            "OUTRA música — barrados:"
        )
        for candidato in resultado.de_outra_musica[:6]:
            print(f"  · {candidato.nome_arquivo}")

    if resultado.de_outro_artista:
        print(
            f"\n🚫 {len(resultado.de_outro_artista)} arquivo(s) com esse nome, mas de "
            "OUTRO artista — barrados:"
        )
        for candidato in resultado.de_outro_artista[:6]:
            pasta = candidato.caminho.replace("\\", "/").rsplit("/", 2)[-2:]
            print(f"  · {'/'.join(pasta)}")
        if not resultado.escolhidos:
            print(
                "\n   Pode ser que a música não exista com esse artista. Confira a "
                "grafia, ou busque só pelo título se quiser ver tudo."
            )


def _mostrar_progresso(silencio_max_s: float = 10.0):
    """Devolve um relator de progresso para passar ao `Baixador`.

    Imprime quando **algo muda** e, se nada mudar, dá um sinal de vida a cada poucos
    segundos. Sem esse batimento, um download lento deixa a tela muda por até dez
    minutos — e silêncio longo não se distingue de travamento. Já aconteceu.
    """
    ultimo = {"texto": "", "quando": 0.0}

    def relatar(lote) -> None:
        partes = []
        for t in lote.transferencias:
            nome = t.candidato.nome_arquivo
            curto = nome if len(nome) <= 34 else nome[:31] + "..."
            if t.estado is EstadoTransferencia.CONCLUIDA:
                partes.append(f"✅ {curto}")
            elif t.estado is EstadoTransferencia.BAIXANDO:
                partes.append(f"⬇ {curto} {t.progresso:.0%}")
            elif t.estado is EstadoTransferencia.NA_FILA:
                fila = f" (fila {t.posicao_fila})" if t.posicao_fila else ""
                partes.append(f"⏳ {curto}{fila}")
            else:
                partes.append(f"❌ {curto}")

        texto = "  |  ".join(partes)
        agora = time.monotonic()
        mudou = texto != ultimo["texto"]
        calado_demais = agora - ultimo["quando"] >= silencio_max_s
        if mudou or calado_demais:
            marca = time.strftime("%H:%M:%S")
            print(f"   [{marca}] {texto}")
            ultimo["texto"] = texto
            ultimo["quando"] = agora

    return relatar


def main(argumentos: list[str]) -> int:
    if not argumentos:
        print(__doc__)
        return 2

    nomes = [a for a in argumentos if not a.startswith("--")]
    if not nomes:
        print(__doc__)
        return 2
    if len(nomes) >= 2:
        artista, titulo = nomes[0], nomes[1]
    else:
        artista, titulo = extrair_do_nome(nomes[0])
    faixa = Faixa(artista=artista, titulo=titulo)

    config = Config.carregar()
    if not config.pasta_mae_playlists.strip():
        print("Falta definir a pasta das playlists nas Configurações (python app.py).")
        return 1

    cliente = ClienteSlskd(url=config.slskd_url, chave_api=config.slskd_api_key)
    if not cliente.chave_api:
        print("Não achei a chave de API — nem nas Configurações, nem no slskd.yml.")
        return 1

    print(f"🎵 {faixa}")
    print(f"   falando com o slskd em {config.slskd_url} ...")
    try:
        if not cliente.conectado():
            print("   ❌ o slskd respondeu, mas NÃO está logado na rede Soulseek.")
            print("      Ligue o motor e espere ele logar:")
            print(f'      & "{sistema.encontrar_slskd()}" --app-dir '
                  f'"{(sistema.encontrar_slskd() or Path()).parent / "dados"}"')
            return 1
    except ErroSlskd as erro:
        print(f"   ❌ {erro}")
        return 1
    print("   ✅ conectado\n   buscando (pode demorar, o limite da rede é 34 por 220 s) ...")

    buscador = Buscador(
        cliente, criterios=_criterios(config), quantidade_por_faixa=config.quantidade_por_faixa
    )
    resultado = buscador.buscar_faixa(faixa)
    _mostrar_achados(resultado)

    if not resultado.escolhidos:
        return 1

    if "--sem-perguntar" not in argumentos:
        if input("\nBaixar? (s/N) ").strip().lower() != "s":
            print("Cancelado — nada foi baixado.")
            return 0

    passagem = (sistema.encontrar_slskd() or Path()).parent / "dados" / "downloads"
    destino = Path(config.pasta_mae_playlists) / PASTA_DAS_AVULSAS / nome_pasta_segura(str(faixa))

    operario = Baixador(cliente, passagem)
    fila = operario.enfileirar(resultado.escolhidos)

    for candidato, motivo in fila.recusados:
        print(f"\n   ⚠ o slskd recusou {candidato.nome_arquivo}")
        print(f"     de {candidato.usuario} — {motivo}")

    if not fila.aceitos:
        print("\nNenhum dos escolhidos entrou na fila. O motivo está logo acima.")
        return 1

    print(f"\n{len(fila.aceitos)} na fila. Acompanhando (Ctrl+C para parar de olhar)...\n")
    lote = operario.acompanhar(fila.aceitos, ao_progredir=_mostrar_progresso())

    movidos = operario.organizar(lote, destino)
    print()
    if movidos:
        print(f"✅ {len(movidos)} arquivo(s) em:\n   {destino}")
        for caminho in movidos:
            print(f"   · {caminho.name}")
    if lote.presas:
        print(f"⏳ {len(lote.presas)} ainda na fila (usuário offline ou fila comprida)")
    if lote.falhadas:
        print(f"❌ {len(lote.falhadas)} falharam")
    return 0 if movidos else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except KeyboardInterrupt:
        print("\nInterrompido.")
        raise SystemExit(130)
