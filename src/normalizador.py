"""Gerador de variantes de busca para o Soulseek.

O problema: a busca do Soulseek casa texto cru com o nome do arquivo de quem compartilha.
Não há normalização do lado do servidor. Se o sujeito salvou ``Djavan - Nao Vou Ficar.mp3``
(sem til, como muita gente salva), procurar por ``Não`` não acha nada.

E tem o caso pior, que não é de grafia e sim de sintaxe: **no Soulseek o ``-`` antes de uma
palavra significa EXCLUIR aquela palavra**. Buscar ``Djavan - Se`` manda o cliente trazer
arquivos com "Djavan" e **sem** "Se". Por isso tanta busca voltava vazia.

A solução não é achar "o tratamento certo" — ele não existe, varia caso a caso. É gerar
**várias formas de escrever a mesma busca**, da mais fiel à mais permissiva, e ir tentando.

Cada variante sai etiquetada com a estratégia que usou, para dar para medir depois qual
delas mais acerta e começar por ela.

Uso rápido pela linha de comando::

    python src/normalizador.py "Djavan" "Não Vou Ficar (feat. Alcione)"
"""

from __future__ import annotations

import re
import sys
import unicodedata
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Tabelas e expressões
# ---------------------------------------------------------------------------

#: Letras que o unicode NÃO decompõe em "letra + acento" — precisam de tradução na mão.
_LETRAS_TEIMOSAS = str.maketrans(
    {
        "ø": "o", "Ø": "O", "ł": "l", "Ł": "L", "đ": "d", "Đ": "D",
        "ð": "d", "Ð": "D", "þ": "th", "Þ": "Th", "ß": "ss",
        "æ": "ae", "Æ": "AE", "œ": "oe", "Œ": "OE", "ħ": "h", "ı": "i",
    }
)

#: Participações. Removidas numa das variantes — raramente estão no nome do arquivo.
#: "with" e "com" ficam de fora de propósito: quebrariam "Dancing With Myself".
_MARCADORES_FEAT = r"feat|feats|featuring|ft|part|participacao|participação"

#: ``(feat. Fulano)`` / ``[ft. Ciclano]`` — apaga o parêntese inteiro.
_RE_FEAT_ENTRE_PARENTESES = re.compile(
    rf"[\(\[\{{]\s*(?:{_MARCADORES_FEAT})\b\.?[^)\]\}}]*[\)\]\}}]", re.IGNORECASE
)

#: ``feat. Fulano`` solto — apaga do marcador até o próximo parêntese ou o fim.
#: Para antes de ``(`` para não comer um ``(Extended Mix)`` que venha depois.
_RE_FEAT_SOLTO = re.compile(
    rf"\b(?:{_MARCADORES_FEAT})\b\.?\s*[^(\[{{]*", re.IGNORECASE
)

#: Qualquer coisa entre parênteses, colchetes ou chaves: ``(Original Mix)``, ``[2011]``.
_RE_PARENTESES = re.compile(r"[\(\[\{][^)\]\}]*[\)\]\}]")

#: Tudo que não é letra nem número. Inclui o hífen — que sai SEMPRE.
#:
#: O ``_`` está explícito de propósito: em regex ele conta como "caractere de palavra",
#: então ``[^\w\s]`` o deixaria passar. E sublinhado é praga em nome de arquivo de DJ
#: (``Artista_-_Titulo.mp3``) — se vazasse para a consulta, a busca não acharia nada.
#: Acentos continuam preservados aqui: ``\w`` em Python 3 é ciente de Unicode, e tirar
#: acento é trabalho de outra função.
_RE_NAO_ALFANUMERICO = re.compile(r"[\W_]", re.UNICODE)

_RE_ESPACOS = re.compile(r"\s+")

#: Caracteres proibidos em nome de pasta no Windows.
_RE_PROIBIDO_WINDOWS = re.compile(r'[\\/:*?"<>|]')

#: Palavras curtas demais ou genéricas demais para ajudar. Como a busca é um E de todos
#: os termos, cada uma delas só endurece o filtro sem discriminar nada. Usadas apenas na
#: variante mais permissiva.
PALAVRAS_VAZIAS = {
    "a", "as", "o", "os", "um", "uma", "de", "da", "do", "das", "dos", "e", "em",
    "no", "na", "nos", "nas", "ao", "aos", "por", "para", "pra", "com", "que", "se",
    "the", "a", "an", "of", "in", "on", "at", "to", "and", "or", "for", "my", "your",
    "el", "la", "los", "las", "y", "del",
}


@dataclass(frozen=True)
class Variante:
    """Uma forma de escrever a busca, com a etiqueta de como foi gerada."""

    consulta: str
    estrategia: str

    def __str__(self) -> str:  # pragma: no cover - conveniência de depuração
        return f"[{self.estrategia}] {self.consulta}"


# ---------------------------------------------------------------------------
# Tratamentos isolados (cada um faz uma coisa só, e é testado sozinho)
# ---------------------------------------------------------------------------


def sem_acentos(texto: str) -> str:
    """``ã→a``, ``ç→c``, ``é→e``, ``ô→o``. Também resolve ``ø``, ``ł`` e companhia."""
    texto = texto.translate(_LETRAS_TEIMOSAS)
    decomposto = unicodedata.normalize("NFD", texto)
    sem_marcas = "".join(c for c in decomposto if unicodedata.category(c) != "Mn")
    return unicodedata.normalize("NFC", sem_marcas)


def sem_pontuacao(texto: str) -> str:
    """Troca por espaço tudo que não é letra/número.

    O hífen sai por aqui — e sair é obrigatório, porque no Soulseek ele é o operador de
    exclusão, não um caractere comum.
    """
    return colapsa_espacos(_RE_NAO_ALFANUMERICO.sub(" ", texto))


def sem_participacao(texto: str) -> str:
    """Remove ``feat.``, ``ft.``, ``featuring``, ``part.`` e quem vem junto."""
    texto = _RE_FEAT_ENTRE_PARENTESES.sub(" ", texto)
    texto = _RE_FEAT_SOLTO.sub(" ", texto)
    return colapsa_espacos(texto)


def sem_parenteses(texto: str) -> str:
    """Remove ``(Original Mix)``, ``[Remastered 2011]``, ``{Bonus}``."""
    return colapsa_espacos(_RE_PARENTESES.sub(" ", texto))


def colapsa_espacos(texto: str) -> str:
    """Espaços repetidos viram um só; sobra e falta nas pontas somem."""
    return _RE_ESPACOS.sub(" ", texto).strip()


def primeiro_artista(artista: str) -> str:
    """De ``"Djavan, Alcione & Zeca"`` fica só ``"Djavan"``.

    A grafia dos convidados varia demais entre quem cataloga — o artista principal é o
    que tem chance real de bater com o nome do arquivo.
    """
    partido = re.split(r"\s*[,;&/]\s*|\s+(?:feat|ft|featuring|part)\b\.?\s*", artista, flags=re.IGNORECASE)
    return colapsa_espacos(partido[0]) if partido else colapsa_espacos(artista)


def palavras_uteis(texto: str) -> list[str]:
    """As palavras que realmente discriminam: sem as vazias e sem as de uma letra só."""
    return [
        p for p in sem_pontuacao(sem_acentos(texto)).lower().split()
        if len(p) > 1 and p not in PALAVRAS_VAZIAS
    ]


def palavras_marcantes(palavras: list[str]) -> list[str]:
    """Escolhe a(s) palavra(s) do título com mais chance de identificar a faixa.

    Palavra longa discrimina bem: ``malemolencia`` sozinha já acha a música. Mas quando
    todas são curtas o critério desanda — em "One More Time" a mais longa é ``more``, que
    aparece em meio mundo de arquivo. Nesse caso vão **duas** palavras, na ordem do título,
    que juntas voltam a discriminar.
    """
    if not palavras:
        return []
    mais_longa = max(palavras, key=len)
    if len(mais_longa) > 4:
        return [mais_longa]
    duas_maiores = sorted(palavras, key=len, reverse=True)[:2]
    return [p for p in palavras if p in duas_maiores][:2]


def artista_aparece_em(caminho: str, artista: str) -> bool:
    """O artista pedido aparece no caminho do arquivo achado?

    Esta função existe por causa de um erro real: ao buscar *Djavan — Não Vou Ficar*, as
    variantes com o artista voltaram vazias, a variante ``so_titulo`` buscou só
    ``Nao Vou Ficar``, trouxe 51 respostas, e o app baixou **Kid Abelha** e **Tim Maia**.
    Os arquivos eram bons, o nome batia, e a faixa estava errada.

    A variante sem artista continua valendo — ela resolve o caso do artista grafado de
    outro jeito. O que faltava era **conferir o artista de volta** no resultado.

    A comparação é por palavra inteira, no caminho todo (pasta inclusive), sem acento e
    sem pontuação: quem compartilha quase sempre guarda em ``Artista/Álbum/faixa``.
    Quando não há artista para conferir, não há o que reprovar.
    """
    if not (artista or "").strip():
        return True

    palavras_do_artista = palavras_uteis(primeiro_artista(artista))
    if not palavras_do_artista:
        return True

    texto = caminho.replace("\\", " ").replace("/", " ")
    presentes = set(sem_pontuacao(sem_acentos(texto)).casefold().split())
    return all(palavra in presentes for palavra in palavras_do_artista)


def titulo_aparece_em(nome_arquivo: str, titulo: str) -> bool:
    """O título pedido aparece no nome do arquivo achado?

    Companheira de `artista_aparece_em`, e nascida do mesmo jeito: depois de conferir o
    artista, o app pediu *Djavan — Não Vou Ficar*, a variante ``artista_palavra_chave``
    buscou ``Djavan ficar``, e veio **Tenho Medo de Ficar Só** — do Djavan mesmo, com
    "ficar" no nome. Artista certo, título errado.

    Confere só o **nome do arquivo**, não o caminho: o título está no nome, e usar a
    pasta deixaria passar qualquer faixa de um álbum que se chame como a música.

    O que vale é o **núcleo** do título — sem participação e sem parênteses. Exigir
    ``(Original Mix)`` reprovaria o arquivo certo de quem não escreveu isso no nome.
    """
    nucleo = sem_parenteses(sem_participacao(titulo or ""))
    palavras_do_titulo = palavras_uteis(nucleo)
    if not palavras_do_titulo:
        return True

    presentes = set(sem_pontuacao(sem_acentos(nome_arquivo)).casefold().split())
    return all(palavra in presentes for palavra in palavras_do_titulo)


def nome_pasta_segura(nome: str, tamanho_maximo: int = 120) -> str:
    """Transforma o nome da playlist em nome de pasta que o Windows aceita.

    Tira ``\\ / : * ? " < > |``, os caracteres de controle, e o ponto/espaço no fim —
    que o Windows silenciosamente descarta e depois ninguém entende por que a pasta
    "sumiu".
    """
    limpo = _RE_PROIBIDO_WINDOWS.sub(" ", nome)
    limpo = "".join(c for c in limpo if c.isprintable())
    limpo = colapsa_espacos(limpo).rstrip(". ")
    limpo = limpo[:tamanho_maximo].rstrip(". ")
    return limpo or "Playlist sem nome"


# ---------------------------------------------------------------------------
# O gerador
# ---------------------------------------------------------------------------


def gerar_variantes(artista: str, titulo: str) -> list[Variante]:
    """Devolve as formas de buscar esta faixa, da mais fiel à mais permissiva.

    A ordem importa: quem consome deve tentar uma por vez e **parar na primeira que
    trouxer resultado aproveitável**, porque cada busca gasta cota do limite de
    34 buscas / 220 s da rede (ver GUIA_SOULSEEK.md).

    Nenhuma consulta devolvida contém ``-``, em nenhuma hipótese.
    """
    artista = colapsa_espacos(artista or "")
    titulo = colapsa_espacos(titulo or "")
    if not artista and not titulo:
        return []

    candidatas: list[Variante] = []

    def registra(consulta: str, estrategia: str) -> None:
        consulta = colapsa_espacos(consulta)
        if consulta:
            candidatas.append(Variante(consulta, estrategia))

    # 1. Fiel: só tira a pontuação (obrigatório por causa do hífen), mantém os acentos.
    registra(sem_pontuacao(f"{artista} {titulo}"), "fiel")

    # 2. A mesma coisa sem acentos — metade da rede cataloga assim.
    registra(sem_pontuacao(sem_acentos(f"{artista} {titulo}")), "sem_acentos")

    # 3. Sem a participação, que quase nunca está no nome do arquivo.
    sem_feat = sem_participacao(f"{artista} {titulo}")
    registra(sem_pontuacao(sem_acentos(sem_feat)), "sem_participacao")

    # 4. Sem os parênteses: adeus "(Original Mix)", "(Remastered 2011)".
    #    Fica DEPOIS da variante 3 de propósito — para DJ, "Extended Mix" às vezes é
    #    justamente o que distingue a faixa certa da errada.
    enxuto = sem_parenteses(sem_feat)
    registra(sem_pontuacao(sem_acentos(enxuto)), "sem_parenteses")

    # 5. Só o título — para quando o artista está escrito de outro jeito no arquivo.
    so_titulo = sem_parenteses(sem_participacao(titulo))
    registra(sem_pontuacao(sem_acentos(so_titulo)), "so_titulo")

    # 6. Artista principal + a(s) palavra(s) mais característica(s) do título.
    principal = sem_pontuacao(sem_acentos(primeiro_artista(artista)))
    palavras_titulo = palavras_uteis(so_titulo)
    if principal and palavras_titulo:
        marcantes = " ".join(palavras_marcantes(palavras_titulo))
        registra(f"{principal} {marcantes}", "artista_palavra_chave")

    # 7. Núcleo: só as palavras que discriminam. A rede de arrasto, por último.
    #    Com menos de 2 palavras a busca fica genérica demais e volta lixo — nesse caso
    #    a variante nem é oferecida.
    nucleo = palavras_uteis(f"{principal} {so_titulo}")
    if len(nucleo) >= 2:
        registra(" ".join(nucleo), "nucleo")

    return _sem_repetidas(candidatas)


def _sem_repetidas(variantes: list[Variante]) -> list[Variante]:
    """Tira as consultas repetidas mantendo a primeira (a de estratégia mais fiel)."""
    vistas: set[str] = set()
    unicas: list[Variante] = []
    for v in variantes:
        chave = v.consulta.casefold()
        if chave not in vistas:
            vistas.add(chave)
            unicas.append(v)
    return unicas


# ---------------------------------------------------------------------------


def _demonstracao(argumentos: list[str]) -> int:
    if len(argumentos) < 2:
        exemplos = [
            ("Djavan", "Não Vou Ficar (feat. Alcione)"),
            ("Tim Maia", "Você"),
            ("Céu", "Malemolência - Instrumental"),
            ("Sigur Rós", "Hoppípolla"),
            ("Daft Punk", "One More Time [Extended Mix]"),
        ]
        print("Sem argumentos — mostrando exemplos.\n")
        print('Uso: python src/normalizador.py "Artista" "Título"\n')
    else:
        exemplos = [(argumentos[0], argumentos[1])]

    for artista, titulo in exemplos:
        print(f"🎵 {artista} — {titulo}")
        for i, v in enumerate(gerar_variantes(artista, titulo), 1):
            print(f"   {i}. {v.consulta!r}  ({v.estrategia})")
        print()
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_demonstracao(sys.argv[1:]))
