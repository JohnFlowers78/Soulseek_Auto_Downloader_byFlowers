"""Lê uma pasta de músicas e descobre o que cada arquivo é.

É a porta de entrada do modo **"melhorar o acervo"**: em vez de partir de uma playlist,
parte do que já está no disco. O resto do cano é o mesmo — as faixas lidas aqui descem
pela mesma normalização, a mesma busca e o mesmo ranking (ver ARQUITETURA.md).

Duas decisões moldam este módulo:

**Varre todo formato de áudio, inclusive os que o filtro de playlist rejeita.** OGG, WMA,
MP3 128 — são justamente os arquivos que mais valem a troca. Varrer só o que "presta"
deixaria de fora exatamente o alvo da funcionalidade.

**Usa o `ffprobe` para ler tags e especificações**, em vez de somar uma biblioteca de tags
ao projeto. O ffprobe vem junto com o ffmpeg, que já é requisito para o espectrograma —
uma dependência de sistema em vez de duas, e ele lê qualquer formato que o ffmpeg abra.

Sem ffmpeg instalado o módulo ainda funciona em modo reduzido: tira artista e título do
**nome do arquivo**. Perde as especificações técnicas, mas não trava a leitura da pasta.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

from modelos import ArquivoLocal, Faixa

#: Tudo que pode ser música. Os formatos ruins estão aqui DE PROPÓSITO — um MP3 128 é o
#: que mais vale trocar, e ignorá-lo seria ignorar o alvo.
EXTENSOES_AUDIO = frozenset(
    {
        "flac", "wav", "aiff", "aif", "alac", "ape", "wv",           # sem perda
        "mp3", "m4a", "aac", "ogg", "oga", "opus", "wma", "mp2",     # com perda
    }
)

# ---------------------------------------------------------------------------
# Limpeza de nome de arquivo
# ---------------------------------------------------------------------------

#: Separador entre artista e título. **Sempre com espaços dos dois lados** — é o que
#: permite que ``Blink-182 - All the Small Things`` divida no lugar certo em vez de
#: quebrar o nome da banda ao meio.
_SEPARADORES = (" - ", " – ", " — ", " -- ", " _ ")

#: ``www.baixaki.com_`` e afins, grudados no começo por quem distribuiu o arquivo.
#: O ``_`` está fora do trecho ganancioso porque domínio não tem sublinhado — se ficasse
#: dentro, ``www.site.com_Artista`` levaria o artista junto.
_RE_SITE_NO_COMECO = re.compile(
    r"^\s*[\(\[]?\s*(?:www\.|https?://)[^\s\)\]_]+[\)\]]?\s*[-_]*\s*", re.IGNORECASE
)

#: ``[Label001]`` ou ``[Promo]`` no começo. Limitado a 30 caracteres para não engolir um
#: título inteiro que por acaso comece com colchete.
_RE_ROTULO_NO_COMECO = re.compile(r"^\s*\[[^\]]{1,30}\]\s*")

#: Numeração no começo: ``12 - ``, ``01. ``, ``3) ``, e o lado/faixa de vinil ``A1. ``.
#: Exige separador logo depois — é o que já protege ``50 Cent - In Da Club`` e
#: ``2 Unlimited - No Limit``, onde nenhum separador vem colado ao número.
_RE_NUMERACAO = re.compile(r"^\s*(?:\d{1,3}|[A-Da-d][1-9]\d?)\s*[-._)]\s*")

#: ``04 Titulo`` — zero à esquerda seguido de espaço, sem separador nenhum.
_RE_NUMERACAO_COM_ZERO = re.compile(r"^\s*0\d\s+")

#: Zero à esquerda é numeração sem sombra de dúvida: nenhum artista se chama "01".
_RE_ZERO_A_ESQUERDA = re.compile(r"^\s*0\d")

#: ``(320kbps)``, ``[320]``, ``[FLAC]``, ``[V0]``, ``[2011]`` no fim. Note que
#: ``(Original Mix)`` e ``(Extended Mix)`` NÃO casam — e não podem casar, porque para DJ
#: eles fazem parte do nome da faixa.
#:
#: O número solto entre colchetes entra na lista porque, ali no fim, ele só é selo de
#: qualidade (``[320]``) ou ano (``[2011]``) — e tirar os dois ajuda a busca.
_RE_QUALIDADE_NO_FIM = re.compile(
    r"\s*[\(\[]\s*(?:\d{2,4}\s*k(?:bps)?|\d{2,4}|flac|wav|aiff?|lossless|v0|v2|cbr|vbr|hq)"
    r"\s*[\)\]]\s*$",
    re.IGNORECASE,
)

#: A mesma coisa solta, sem parênteses: ``Artista - Titulo - 320kbps``.
_RE_KBPS_SOLTO_NO_FIM = re.compile(r"[\s\-_]+\d{2,4}\s*kbps\s*$", re.IGNORECASE)

_RE_ESPACOS = re.compile(r"\s+")


def _tem_separador(texto: str) -> bool:
    return any(separador in texto for separador in _SEPARADORES)


def _tirar_numeracao(texto: str) -> str:
    """Tira o número de faixa do começo — mas só quando ele é mesmo número de faixa.

    Aqui mora a armadilha mais bonita do módulo. ``01 - Artista - Titulo`` e
    ``311 - Down`` têm exatamente a mesma forma, e 311 é uma banda. O que separa os dois
    é o **que sobra**: numeração de faixa vem antes de ``Artista - Titulo``, então depois
    de tirá-la ainda resta um separador. Se não resta, o "número" era o próprio artista.

    A mesma regra resolve o vinil sem regra extra: em ``A1. Artista - Titulo`` o ``A1``
    sai, e em ``A1 - Caught in the Middle`` — do grupo A1 — ele fica.

    A exceção é o zero à esquerda: ``01``, ``04``, ``09`` só existem como numeração,
    então saem mesmo sem sobrar separador.
    """
    for padrao in (_RE_NUMERACAO, _RE_NUMERACAO_COM_ZERO):
        resto = padrao.sub("", texto, count=1)
        if resto == texto:
            continue
        if _RE_ZERO_A_ESQUERDA.match(texto) or _tem_separador(resto):
            return resto
    return texto


def limpar_nome(nome: str) -> str:
    """Tira do nome do arquivo o que não é artista nem título.

    A ordem importa: os sublinhados viram espaço **antes** de procurar número de faixa,
    senão ``01_Artista_-_Titulo`` não seria reconhecido como numerado.
    """
    texto = nome
    # Só tira a extensão se ela for mesmo de áudio — "Artista - Titulo.Ao Vivo" não é.
    if "." in texto and texto.rsplit(".", 1)[-1].lower() in EXTENSOES_AUDIO:
        texto = texto.rsplit(".", 1)[0]

    texto = _RE_SITE_NO_COMECO.sub("", texto)
    texto = _RE_ROTULO_NO_COMECO.sub("", texto)

    # Nome inteiro com sublinhado no lugar de espaço é padrão de quem baixou da web.
    # Só troca quando NÃO há nenhum espaço — senão estraga um artista que usa "_" no nome.
    if "_" in texto and " " not in texto:
        texto = texto.replace("_", " ")

    texto = _tirar_numeracao(texto)
    texto = _RE_QUALIDADE_NO_FIM.sub("", texto)
    texto = _RE_KBPS_SOLTO_NO_FIM.sub("", texto)
    return _RE_ESPACOS.sub(" ", texto).strip(" -_")


def extrair_do_nome(nome: str) -> tuple[str, str]:
    """Devolve ``(artista, titulo)`` a partir do nome do arquivo.

    Quando não há separador reconhecível, o artista volta **vazio** em vez de chutado —
    e aí o `normalizador.py` busca só pelo título, que é a variante ``so_titulo``. Chutar
    um artista errado seria pior que não ter nenhum: entraria como termo obrigatório na
    busca e derrubaria todos os resultados.
    """
    limpo = limpar_nome(nome)
    if not limpo:
        return "", ""

    # Divide no separador que aparecer PRIMEIRO, seja ele hífen, travessão ou meia-risca.
    corte = min(
        ((limpo.find(sep), sep) for sep in _SEPARADORES if sep in limpo),
        default=None,
    )
    if corte is None:
        return "", limpo

    _, separador = corte
    artista, _, titulo = limpo.partition(separador)
    artista, titulo = artista.strip(" -_"), titulo.strip(" -_")

    # "- Titulo.mp3" não tem artista; devolver um vazio é melhor que devolver lixo.
    if not artista or not titulo:
        return "", (titulo or artista)
    return artista, titulo


# ---------------------------------------------------------------------------
# Leitura do ffprobe
# ---------------------------------------------------------------------------


def _para_int(valor) -> int | None:
    """Converte o que o ffprobe devolve como texto, tolerando ausência e ``N/A``."""
    try:
        numero = int(float(valor))
    except (TypeError, ValueError):
        return None
    # O ffprobe usa 0 para "não se aplica" (bits por amostra de formato comprimido).
    return numero or None


def _para_float(valor) -> float | None:
    try:
        return float(valor)
    except (TypeError, ValueError):
        return None


def _tags(dados: dict) -> dict[str, str]:
    """Junta as tags do contêiner e as da trilha, tudo em minúsculas.

    Formatos diferentes guardam em lugares diferentes: MP3 põe no contêiner, FLAC põe na
    trilha e ainda usa MAIÚSCULAS (``TITLE``). Achatar aqui evita espalhar esse
    conhecimento pelo resto do código.
    """
    reunidas: dict[str, str] = {}
    origens = [dados.get("format", {}).get("tags") or {}]
    origens += [trilha.get("tags") or {} for trilha in dados.get("streams", [])]
    for origem in origens:
        for chave, valor in origem.items():
            reunidas.setdefault(str(chave).lower(), str(valor))
    return reunidas


def _trilha_de_audio(dados: dict) -> dict:
    for trilha in dados.get("streams", []):
        if trilha.get("codec_type") == "audio":
            return trilha
    return {}


def montar_arquivo_local(caminho: Path, dados_ffprobe: dict | None) -> ArquivoLocal:
    """Monta o `ArquivoLocal` a partir do que o ffprobe devolveu.

    Separada da chamada ao ffprobe **de propósito**: é aqui que mora toda a lógica, e
    assim ela se testa com um JSON escrito à mão, sem precisar de ffmpeg instalado nem de
    arquivo de áudio de verdade no disco.
    """
    dados = dados_ffprobe or {}
    tags = _tags(dados)
    contêiner = dados.get("format", {})
    trilha = _trilha_de_audio(dados)

    titulo_tag = (tags.get("title") or "").strip()
    artista_tag = (tags.get("artist") or tags.get("album_artist") or "").strip()

    artista_nome, titulo_nome = extrair_do_nome(caminho.name)

    titulo = titulo_tag or titulo_nome
    artista = artista_tag or artista_nome

    if titulo_tag and artista_tag:
        origem = "tags"
    elif titulo_tag or artista_tag:
        origem = "tags + nome do arquivo"
    else:
        origem = "nome do arquivo"

    bitrate_bps = _para_int(contêiner.get("bit_rate") or trilha.get("bit_rate"))

    tamanho = _para_int(contêiner.get("size"))
    if tamanho is None:
        try:
            tamanho = caminho.stat().st_size
        except OSError:
            tamanho = 0

    return ArquivoLocal(
        caminho=caminho,
        faixa=Faixa(
            artista=artista,
            titulo=titulo,
            album=(tags.get("album") or "").strip(),
            duracao_s=_para_float(contêiner.get("duration") or trilha.get("duration")),
            isrc=(tags.get("isrc") or "").strip(),
        ),
        tamanho_bytes=tamanho or 0,
        duracao_s=_para_float(contêiner.get("duration") or trilha.get("duration")),
        bitrate_kbps=round(bitrate_bps / 1000) if bitrate_bps else None,
        taxa_amostragem_hz=_para_int(trilha.get("sample_rate")),
        # FLAC informa em bits_per_raw_sample; WAV/AIFF em bits_per_sample.
        profundidade_bits=_para_int(
            trilha.get("bits_per_raw_sample") or trilha.get("bits_per_sample")
        ),
        origem_do_nome=origem,
        origem="acervo",
    )


def ler_ffprobe(caminho: Path, executavel: str = "ffprobe") -> dict | None:
    """Roda o ffprobe. Devolve ``None`` quando ele não está instalado ou falha.

    Devolver ``None`` em vez de estourar é intencional: sem ffmpeg o app ainda consegue
    ler os nomes da pasta e buscar. Perde as especificações e o espectrograma, mas o
    usuário não fica travado até instalar nada.
    """
    comando = [
        executavel, "-v", "quiet", "-print_format", "json",
        "-show_format", "-show_streams", str(caminho),
    ]
    try:
        resultado = subprocess.run(
            comando, capture_output=True, text=True, encoding="utf-8", timeout=30
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if resultado.returncode != 0 or not resultado.stdout:
        return None
    try:
        return json.loads(resultado.stdout)
    except json.JSONDecodeError:
        return None


def ler_arquivo(caminho: Path, executavel: str = "ffprobe") -> ArquivoLocal:
    """Lê um arquivo de música do disco."""
    return montar_arquivo_local(caminho, ler_ffprobe(caminho, executavel))


# ---------------------------------------------------------------------------
# Varredura
# ---------------------------------------------------------------------------


def varrer_pasta(pasta: Path, recursivo: bool = True) -> list[Path]:
    """Lista os arquivos de áudio da pasta, em ordem previsível.

    A ordem é alfabética de propósito: a lista aparece na tela e o usuário precisa
    reencontrar o que viu. Ordem de sistema de arquivos varia entre máquinas.
    """
    if not pasta.is_dir():
        return []
    passo = pasta.rglob("*") if recursivo else pasta.glob("*")
    achados = [
        caminho
        for caminho in passo
        if caminho.is_file() and caminho.suffix.lstrip(".").lower() in EXTENSOES_AUDIO
    ]
    return sorted(achados, key=lambda p: str(p).lower())


def ler_pasta(pasta: Path, recursivo: bool = True, executavel: str = "ffprobe") -> list[ArquivoLocal]:
    """Lê a pasta inteira: um `ArquivoLocal` por música encontrada."""
    return [ler_arquivo(caminho, executavel) for caminho in varrer_pasta(pasta, recursivo)]


# ---------------------------------------------------------------------------


_EXEMPLOS = [
    "01 - Djavan - Não Vou Ficar.mp3",
    "Céu_-_Malemolência.flac",
    "[Label001] Bonobo - Kiara (Original Mix).wav",
    "www.baixaki.com_Tim Maia - Você.mp3",
    "50 Cent - In Da Club.mp3",
    "311 - Down.mp3",
    "A1. Daft Punk - One More Time.aiff",
    "A1 - Caught in the Middle.mp3",
    "Blink-182 - All the Small Things [320kbps].mp3",
    "04 Titulo Sem Artista.mp3",
]


def _demonstracao(argumentos: list[str]) -> int:
    if argumentos:
        pasta = Path(argumentos[0])
        arquivos = ler_pasta(pasta)
        if not arquivos:
            print(f"Nenhuma música encontrada em {pasta}")
            return 1
        print(f"📁 {pasta} — {len(arquivos)} música(s)\n")
        for arquivo in arquivos:
            ficha = arquivo.formato.upper()
            if arquivo.bitrate_kbps:
                ficha += f" {arquivo.bitrate_kbps} kbps"
            if arquivo.profundidade_bits:
                ficha += f" / {arquivo.profundidade_bits} bits"
            if arquivo.taxa_amostragem_hz:
                ficha += f" / {arquivo.taxa_amostragem_hz / 1000:g} kHz"
            print(f"  {arquivo.caminho.name}")
            print(f"    → {arquivo.faixa}  [{ficha}]  (nome veio de: {arquivo.origem_do_nome})")
        return 0

    print("Sem argumentos — mostrando como os nomes são interpretados.\n")
    print('Uso: python src/leitor_pasta.py "D:\\Caminho\\Da\\Sua\\Pasta"\n')
    for nome in _EXEMPLOS:
        artista, titulo = extrair_do_nome(nome)
        print(f"  {nome}")
        print(f"    → artista={artista!r}  titulo={titulo!r}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    import sys

    raise SystemExit(_demonstracao(sys.argv[1:]))
