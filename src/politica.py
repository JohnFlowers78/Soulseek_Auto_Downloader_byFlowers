"""Quantas versões baixar de cada faixa, e quais.

Pedido do usuário, e a razão é de pista de dança: **tocar sempre o mesmo formato**, para
a diferença de qualidade não aparecer no meio do set. Então não basta "baixe as duas
melhores" — é preciso garantir que haja uma de cada tipo, e preferir o tipo escolhido.

A política é:

1. uma **MP3 320** (para ter o formato leve, compatível com tudo);
2. uma **sem perda** (AIFF, WAV ou FLAC);
3. uma **segunda do formato em foco**, que é o que vai realmente tocar.

Quando a rede não oferece algum desses, a vaga não se perde: ela vai para a melhor
opção que sobrou. Trazer duas boas é melhor que trazer uma boa e uma lacuna.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from qualidade import Avaliacao, Criterios


class Foco(str, Enum):
    """O formato que o usuário vai tocar — e que, por isso, ganha a vaga extra."""

    SEM_PERDA = "sem_perda"   # AIFF / WAV / FLAC
    MP3 = "mp3"

    @property
    def rotulo(self) -> str:
        return "sem perda (AIFF/WAV/FLAC)" if self is Foco.SEM_PERDA else "MP3 320"


@dataclass(frozen=True)
class Escolha:
    """Uma versão escolhida, com o motivo da escolha — que vai para a tela."""

    avaliacao: Avaliacao
    papel: str

    def __str__(self) -> str:  # pragma: no cover - conveniência
        return f"{self.papel}: {self.avaliacao.motivo}"


def _e_sem_perda(avaliacao: Avaliacao, criterios: Criterios) -> bool:
    return avaliacao.candidato.extensao in criterios.formatos_sem_perda


def _e_mp3(avaliacao: Avaliacao) -> bool:
    return avaliacao.candidato.extensao == "mp3"


def escolher_por_politica(
    aprovados: list[Avaliacao],
    foco: Foco = Foco.SEM_PERDA,
    quantidade: int = 3,
    criterios: Criterios | None = None,
    diversificar_por_usuario: bool = True,
) -> list[Escolha]:
    """Escolhe as versões a baixar, cumprindo a política acima.

    `aprovados` já vem ordenado do melhor para o pior. A diversificação por usuário
    continua valendo dentro de cada papel: duas opções do mesmo usuário caem juntas se
    ele sair do ar, e aí a garantia de ter os dois formatos some junto.
    """
    criterios = criterios or Criterios()
    escolhidas: list[Escolha] = []
    usados: set[str] = set()

    def pegar(filtro, papel: str) -> bool:
        for avaliacao in aprovados:
            if any(e.avaliacao is avaliacao for e in escolhidas):
                continue
            if diversificar_por_usuario and avaliacao.candidato.usuario in usados:
                continue
            if filtro(avaliacao):
                escolhidas.append(Escolha(avaliacao, papel))
                usados.add(avaliacao.candidato.usuario)
                return True
        return False

    # 1 e 2: um de cada formato, para a coleção ter sempre as duas caras.
    pegar(lambda a: _e_sem_perda(a, criterios), "sem perda")
    pegar(_e_mp3, "MP3 320")

    # 3: a vaga extra vai para o formato que vai tocar.
    if foco is Foco.SEM_PERDA:
        pegar(lambda a: _e_sem_perda(a, criterios), "2ª sem perda (foco)")
    else:
        pegar(_e_mp3, "2º MP3 (foco)")

    # Faltou alguém? A vaga não se perde — vai para o melhor que sobrou. Uma lacuna
    # não ajuda ninguém; uma segunda opção boa, sim.
    while len(escolhidas) < quantidade:
        if not pegar(lambda _a: True, "melhor restante"):
            if not diversificar_por_usuario:
                break
            # Esgotou gente nova: aceita repetir usuário em vez de voltar de mãos
            # mais vazias do que o pedido.
            diversificar_por_usuario = False
            usados.clear()

    return escolhidas[:quantidade]


def resumir_politica(escolhidas: list[Escolha], foco: Foco) -> str:
    """Uma linha dizendo o que a política conseguiu cumprir — e o que não."""
    if not escolhidas:
        return "nada escolhido"

    tem_sem_perda = any("sem perda" in e.papel for e in escolhidas)
    tem_mp3 = any("MP3" in e.papel for e in escolhidas)

    faltou = []
    if not tem_sem_perda:
        faltou.append("sem perda")
    if not tem_mp3:
        faltou.append("MP3 320")

    texto = f"{len(escolhidas)} versão(ões), foco em {foco.rotulo}"
    if faltou:
        texto += f" — a rede não tinha: {', '.join(faltou)}"
    return texto
