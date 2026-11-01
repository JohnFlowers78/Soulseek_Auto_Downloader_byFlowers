"""Decide se um arquivo achado na rede presta, e ordena os que prestam.

As qualidades aceitas são as combinadas: **AIFF, WAV, FLAC, MP3 320 kbps e AAC/M4A**.
O resto é descartado com um motivo escrito — o motivo aparece na tela, para quando a faixa
não vier e a pergunta for "mas não tinha nada mesmo?".

Duas coisas moldam este módulo:

1. **O motor pode não informar o bitrate.** A automação de tela do SoulseekQt muitas vezes
   só tem nome e tamanho. Então o bitrate é **estimado** pelo tamanho e pela duração quando
   não vier declarado.
2. **Baixar mais de uma opção é o pedido**, mas baixar duas do *mesmo usuário* é ilusão de
   segurança: se ele estiver offline, as duas falham juntas. Por isso a escolha
   **diversifica por usuário**.
"""

from __future__ import annotations

from dataclasses import dataclass

from modelos import ArquivoLocal, Candidato

# ---------------------------------------------------------------------------
# Critérios
# ---------------------------------------------------------------------------

#: Sem perda: o áudio é idêntico ao original. Bitrate aqui não é critério de aceite —
#: um FLAC varia de 400 a 1400 kbps conforme a música, e todos são perfeitos.
FORMATOS_SEM_PERDA = ("flac", "wav", "aiff", "aif")

#: Com perda: só entram acima do mínimo de cada um.
FORMATOS_COM_PERDA = ("mp3", "m4a", "aac")


@dataclass(frozen=True)
class Criterios:
    """O que é aceitável. Vira configuração do app mais tarde."""

    formatos_sem_perda: tuple[str, ...] = FORMATOS_SEM_PERDA
    formatos_com_perda: tuple[str, ...] = FORMATOS_COM_PERDA

    #: MP3 abaixo disso não entra. Foi o pedido: 320.
    minimo_mp3_kbps: int = 320
    #: AAC rende mais por bit que MP3 — 256 de AAC equivale, na prática, a 320 de MP3.
    minimo_aac_kbps: int = 256
    #: Folga para arredondamento de quem informa o bitrate (320 às vezes vira 319).
    tolerancia_bitrate_kbps: int = 5

    #: Quanto a duração pode divergir da que o Spotify informou. É esta checagem que
    #: separa a faixa certa do "Extended Mix" achado pela variante mais permissiva.
    tolerancia_duracao_s: float = 5.0

    #: Abaixo disso é arquivo quebrado, capa de álbum ou pedaço de download.
    tamanho_minimo_bytes: int = 200_000

    #: Fila do outro usuário acima disso: nem tenta.
    #:
    #: Não é só impaciência. O slskd desiste de entrar numa fila remota depois de 180
    #: segundos — e foi **nesse caminho de desistência** que ele quebrou com uma exceção
    #: fatal e levou o processo inteiro junto, no meio de uma playlist. Fila de 677
    #: pessoas (número real, visto na rede) não anda nesse tempo. Evitar essas fontes
    #: tira a corrida do caminho do defeito, e de quebra ela anda mais rápido.
    fila_maxima: int = 300

    #: Preferência entre os sem-perda. FLAC na frente porque é o mesmo áudio ocupando
    #: menos e — diferente de WAV e AIFF — carrega as tags direito.
    preferencia_sem_perda: tuple[str, ...] = ("flac", "aiff", "aif", "wav")


@dataclass(frozen=True)
class Avaliacao:
    """O veredito sobre um candidato."""

    candidato: Candidato
    aceito: bool
    motivo: str
    pontos: int = 0
    bitrate_usado_kbps: int | None = None
    #: True quando o bitrate foi calculado por nós, não informado pelo motor.
    bitrate_estimado: bool = False

    def __str__(self) -> str:  # pragma: no cover - conveniência de depuração
        selo = "✅" if self.aceito else "❌"
        return f"{selo} {self.candidato.nome_arquivo} — {self.motivo} ({self.pontos} pts)"


# ---------------------------------------------------------------------------
# Cálculos
# ---------------------------------------------------------------------------


def bitrate_estimado_kbps(tamanho_bytes: int, duracao_s: float | None) -> int | None:
    """Deduz o bitrate pelo tamanho e pela duração, para quando o motor não informa.

    A conta puxa **para cima**, porque o tamanho inclui tags e capa embutida. Isso é bom:
    significa que um arquivo ruim dificilmente passa por bom — para um 256 kbps parecer
    320, precisaria de megabytes de capa. E um 320 legítimo passa com folga.
    """
    if not duracao_s or duracao_s <= 0 or tamanho_bytes <= 0:
        return None
    return round(tamanho_bytes * 8 / duracao_s / 1000)


def _minimo_para(extensao: str, criterios: Criterios) -> int:
    return criterios.minimo_mp3_kbps if extensao == "mp3" else criterios.minimo_aac_kbps


def _pontos_do_formato(extensao: str, criterios: Criterios) -> int:
    """Sem perda vale muito mais que com perda; entre os sem perda vale a preferência."""
    if extensao in criterios.formatos_sem_perda:
        try:
            lugar = criterios.preferencia_sem_perda.index(extensao)
        except ValueError:
            lugar = len(criterios.preferencia_sem_perda)
        return 1000 - lugar * 10
    return 500


def _pontos_da_fonte(candidato: Candidato) -> int:
    """Quem entrega agora vale mais que quem entrega talvez.

    Nada disso fala de qualidade de áudio — fala da chance de o download **acontecer**.
    Fila comprida e usuário sem slot é a origem da lista "presas na fila".
    """
    pontos = 0
    if candidato.slot_livre:
        pontos += 25
    if candidato.posicao_fila is not None:
        pontos -= min(candidato.posicao_fila, 20)
    if candidato.velocidade_bps:
        pontos += min(candidato.velocidade_bps // 100_000, 15)
    return pontos


def _pontos_da_resolucao(candidato: Candidato) -> int:
    """Bônus pequeno para 24 bits / alta taxa. Desempata sem virar critério."""
    pontos = 0
    if candidato.profundidade_bits and candidato.profundidade_bits >= 24:
        pontos += 8
    if candidato.taxa_amostragem_hz and candidato.taxa_amostragem_hz > 48_000:
        pontos += 4
    return pontos


# ---------------------------------------------------------------------------
# O veredito
# ---------------------------------------------------------------------------


def avaliar(
    candidato: Candidato,
    duracao_esperada_s: float | None = None,
    criterios: Criterios | None = None,
) -> Avaliacao:
    """Diz se este arquivo presta e quantos pontos vale.

    ``duracao_esperada_s`` é a duração que o Spotify informou. Quando não houver (playlist
    lida pelo navegador nem sempre traz), a checagem de duração é **pulada** em vez de
    reprovar — melhor arriscar a versão errada do que descartar tudo.
    """
    criterios = criterios or Criterios()
    extensao = candidato.extensao

    if candidato.tamanho_bytes < criterios.tamanho_minimo_bytes:
        return Avaliacao(candidato, False, f"arquivo pequeno demais ({candidato.tamanho_bytes} bytes)")

    if candidato.posicao_fila and candidato.posicao_fila > criterios.fila_maxima:
        return Avaliacao(
            candidato,
            False,
            f"fila do usuário comprida demais ({candidato.posicao_fila}) — "
            "não entra nela a tempo",
        )

    aceitos = (*criterios.formatos_sem_perda, *criterios.formatos_com_perda)
    if extensao not in aceitos:
        rotulo = extensao or "sem extensão"
        return Avaliacao(candidato, False, f"formato não aceito ({rotulo})")

    # Duração: é o que separa a faixa certa de um remix de mesmo nome.
    if duracao_esperada_s and candidato.duracao_s:
        diferenca = abs(candidato.duracao_s - duracao_esperada_s)
        if diferenca > criterios.tolerancia_duracao_s:
            return Avaliacao(
                candidato,
                False,
                f"duração fora do esperado ({candidato.duracao_s:.0f}s vs {duracao_esperada_s:.0f}s)",
            )

    bitrate = candidato.bitrate_kbps
    estimado = False
    if extensao in criterios.formatos_com_perda:
        if bitrate is None:
            bitrate = bitrate_estimado_kbps(candidato.tamanho_bytes, candidato.duracao_s)
            estimado = bitrate is not None

        if bitrate is None:
            return Avaliacao(
                candidato,
                False,
                "sem bitrate e sem duração para estimar — não dá para saber a qualidade",
            )

        minimo = _minimo_para(extensao, criterios)
        if bitrate < minimo - criterios.tolerancia_bitrate_kbps:
            como = "estimado" if estimado else "declarado"
            return Avaliacao(
                candidato,
                False,
                f"bitrate abaixo do mínimo ({bitrate} kbps {como}, mínimo {minimo})",
                bitrate_usado_kbps=bitrate,
                bitrate_estimado=estimado,
            )

    pontos = (
        _pontos_do_formato(extensao, criterios)
        + _pontos_da_fonte(candidato)
        + _pontos_da_resolucao(candidato)
    )
    # Entre dois com perda, o de bitrate maior leva. Não vale para sem perda, onde
    # bitrate alto só significa música mais densa, não melhor.
    if extensao in criterios.formatos_com_perda and bitrate:
        pontos += min(bitrate // 32, 20)
    # Bitrate estimado é palpite: perde para quem declarou, em caso de empate.
    if estimado:
        pontos -= 5

    descricao = extensao.upper()
    if extensao in criterios.formatos_com_perda and bitrate:
        descricao += f" {bitrate} kbps" + (" (estimado)" if estimado else "")

    return Avaliacao(candidato, True, descricao, pontos, bitrate, estimado)


def ranquear(
    candidatos: list[Candidato],
    duracao_esperada_s: float | None = None,
    criterios: Criterios | None = None,
) -> list[Avaliacao]:
    """Avalia todos e devolve **só os aprovados**, do melhor para o pior."""
    aprovados = [
        a for a in (avaliar(c, duracao_esperada_s, criterios) for c in candidatos) if a.aceito
    ]
    return sorted(aprovados, key=lambda a: a.pontos, reverse=True)


def reprovados(
    candidatos: list[Candidato],
    duracao_esperada_s: float | None = None,
    criterios: Criterios | None = None,
) -> list[Avaliacao]:
    """Os descartados, com o motivo de cada um — é o que responde "não tinha nada mesmo?"."""
    return [
        a for a in (avaliar(c, duracao_esperada_s, criterios) for c in candidatos) if not a.aceito
    ]


def escolher_melhores(
    aprovados: list[Avaliacao],
    quantidade: int = 2,
    diversificar_por_usuario: bool = True,
) -> list[Avaliacao]:
    """Escolhe o que vai para a fila de download.

    Baixar mais de uma opção foi o pedido — dá para comparar os espectrogramas depois.
    Mas duas opções **do mesmo usuário** não são duas chances: se ele estiver offline,
    caem juntas. Por isso a segunda escolha prefere **outro usuário**, e só repete quando
    não há mais ninguém oferecendo.
    """
    if quantidade <= 0:
        return []
    if not diversificar_por_usuario:
        return aprovados[:quantidade]

    escolhidos: list[Avaliacao] = []
    usuarios_usados: set[str] = set()

    for avaliacao in aprovados:
        if len(escolhidos) >= quantidade:
            break
        if avaliacao.candidato.usuario not in usuarios_usados:
            escolhidos.append(avaliacao)
            usuarios_usados.add(avaliacao.candidato.usuario)

    # Faltou gente? Completa com os melhores que sobraram, mesmo repetindo usuário.
    if len(escolhidos) < quantidade:
        for avaliacao in aprovados:
            if len(escolhidos) >= quantidade:
                break
            if avaliacao not in escolhidos:
                escolhidos.append(avaliacao)

    return escolhidos


# ---------------------------------------------------------------------------
# Melhorar o acervo: a pergunta deixa de ser "presta?" e vira "é melhor que o meu?"
# ---------------------------------------------------------------------------
#
# Este é o ponto em que o módulo muda de sentido. Vindo de uma playlist, qualquer arquivo
# aprovado serve — não há nada com que comparar. Vindo de uma pasta do usuário, aprovar
# não basta: baixar um FLAC para substituir um FLAC é gastar cota de busca, banda e o
# tempo do usuário para terminar exatamente onde começou.

NIVEL_DESCONHECIDO = 0
NIVEL_COM_PERDA_FRACO = 100
NIVEL_COM_PERDA_BOM = 200
NIVEL_SEM_PERDA = 300
NIVEL_SEM_PERDA_24 = 350
NIVEL_SEM_PERDA_ALTA_TAXA = 400

_NOME_DO_NIVEL = {
    NIVEL_DESCONHECIDO: "qualidade desconhecida",
    NIVEL_COM_PERDA_FRACO: "com perda, abaixo do ideal",
    NIVEL_COM_PERDA_BOM: "com perda, no topo útil",
    NIVEL_SEM_PERDA: "sem perda (16 bits)",
    NIVEL_SEM_PERDA_24: "sem perda (24 bits)",
    NIVEL_SEM_PERDA_ALTA_TAXA: "sem perda (24 bits, alta taxa)",
}


def descrever_nivel(nivel: int) -> str:
    return _NOME_DO_NIVEL.get(nivel, "qualidade desconhecida")


def nivel_de_qualidade(
    formato: str,
    bitrate_kbps: int | None = None,
    profundidade_bits: int | None = None,
    taxa_amostragem_hz: int | None = None,
    criterios: Criterios | None = None,
) -> int:
    """Coloca um arquivo num degrau comparável.

    Repare que **bitrate não entra na conta dos sem perda**. Um FLAC de 700 kbps e um de
    1100 kbps carregam o mesmo áudio original — a diferença é a densidade da música, não
    a qualidade. Quem separa os degraus ali é profundidade de bits e taxa de amostragem.
    """
    criterios = criterios or Criterios()
    formato = (formato or "").lower()

    if formato in criterios.formatos_sem_perda or formato in ("alac", "ape", "wv"):
        if profundidade_bits and profundidade_bits >= 24:
            if taxa_amostragem_hz and taxa_amostragem_hz > 48_000:
                return NIVEL_SEM_PERDA_ALTA_TAXA
            return NIVEL_SEM_PERDA_24
        return NIVEL_SEM_PERDA

    if not formato:
        return NIVEL_DESCONHECIDO

    if bitrate_kbps is None:
        return NIVEL_DESCONHECIDO

    minimo = _minimo_para(formato, criterios)
    if bitrate_kbps >= minimo - criterios.tolerancia_bitrate_kbps:
        return NIVEL_COM_PERDA_BOM
    return NIVEL_COM_PERDA_FRACO


def nivel_do_arquivo_local(arquivo: ArquivoLocal, criterios: Criterios | None = None) -> int:
    return nivel_de_qualidade(
        arquivo.formato,
        arquivo.bitrate_kbps,
        arquivo.profundidade_bits,
        arquivo.taxa_amostragem_hz,
        criterios,
    )


def nivel_do_candidato(avaliacao: Avaliacao, criterios: Criterios | None = None) -> int:
    candidato = avaliacao.candidato
    return nivel_de_qualidade(
        candidato.extensao,
        avaliacao.bitrate_usado_kbps or candidato.bitrate_kbps,
        candidato.profundidade_bits,
        candidato.taxa_amostragem_hz,
        criterios,
    )


def vale_a_pena_trocar(
    atual: ArquivoLocal,
    avaliacao: Avaliacao,
    criterios: Criterios | None = None,
) -> tuple[bool, str]:
    """Diz se este candidato melhora o que o usuário já tem — e explica por quê.

    O motivo volta escrito porque vai para a tela. Quando o app **não** baixa algo, o
    usuário precisa saber que foi decisão e não falha: "achei, mas é a mesma coisa que
    você já tem" é informação; silêncio é bug aparente.
    """
    if not avaliacao.aceito:
        return False, f"reprovado antes da comparação: {avaliacao.motivo}"

    nivel_atual = nivel_do_arquivo_local(atual, criterios)
    nivel_novo = nivel_do_candidato(avaliacao, criterios)

    # O arquivo do acervo mente sobre si mesmo (diz 320, corta em 16 kHz). Nesse caso o
    # degrau declarado dele não vale nada — qualquer versão íntegra e boa é ganho real.
    if atual.suspeito and nivel_novo >= NIVEL_COM_PERDA_BOM:
        return True, "o arquivo do acervo é suspeito de transcodificação — vale conferir esta"

    if nivel_atual == NIVEL_DESCONHECIDO:
        return True, "não dá para saber a qualidade do arquivo atual — vale comparar"

    if nivel_novo > nivel_atual:
        return True, f"sobe de {descrever_nivel(nivel_atual)} para {descrever_nivel(nivel_novo)}"

    if nivel_novo == nivel_atual:
        return False, f"mesma qualidade do que você já tem ({descrever_nivel(nivel_atual)})"

    return False, f"seria piora: {descrever_nivel(nivel_novo)} contra {descrever_nivel(nivel_atual)}"


def filtrar_upgrades(
    atual: ArquivoLocal,
    aprovados: list[Avaliacao],
    criterios: Criterios | None = None,
) -> tuple[list[Avaliacao], list[tuple[Avaliacao, str]]]:
    """Separa os que melhoram o acervo dos que não melhoram.

    Devolve ``(vale_baixar, descartados_com_motivo)`` — os dois lados interessam à tela.
    """
    valem: list[Avaliacao] = []
    descartados: list[tuple[Avaliacao, str]] = []
    for avaliacao in aprovados:
        melhora, motivo = vale_a_pena_trocar(atual, avaliacao, criterios)
        if melhora:
            valem.append(avaliacao)
        else:
            descartados.append((avaliacao, motivo))
    return valem, descartados
