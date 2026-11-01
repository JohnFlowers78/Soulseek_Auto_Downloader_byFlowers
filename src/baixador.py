"""Enfileira os escolhidos, acompanha até o fim e organiza os arquivos.

O slskd baixa para uma **área de passagem** dele. Este módulo é quem tira de lá e põe na
pasta da playlist — e quem separa, no fim, as três listas que a tela mostra:
**baixou** / **preso na fila** / **não veio**.
"""

from __future__ import annotations

import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from modelos import Candidato, EstadoTransferencia, Transferencia
from qualidade import Avaliacao
from slskd_cliente import ClienteSlskd

#: Quanto esperar, por padrão, antes de desistir de acompanhar um lote.
#: Dez minutos: fila de Soulseek anda devagar, mas esperar para sempre trava o app.
ESPERA_PADRAO_S = 600.0


@dataclass
class Lote:
    """Um conjunto de downloads acompanhado junto."""

    transferencias: list[Transferencia] = field(default_factory=list)

    @property
    def concluidas(self) -> list[Transferencia]:
        return [t for t in self.transferencias if t.estado is EstadoTransferencia.CONCLUIDA]

    @property
    def presas(self) -> list[Transferencia]:
        return [
            t
            for t in self.transferencias
            if t.estado in (EstadoTransferencia.NA_FILA, EstadoTransferencia.BAIXANDO)
        ]

    @property
    def falhadas(self) -> list[Transferencia]:
        return [
            t
            for t in self.transferencias
            if t.estado in (EstadoTransferencia.FALHOU, EstadoTransferencia.CANCELADA)
        ]

    @property
    def tudo_terminou(self) -> bool:
        return all(t.terminou for t in self.transferencias)


class Baixador:
    def __init__(
        self,
        cliente: ClienteSlskd,
        pasta_de_passagem: Path,
        dormir: Callable[[float], None] = time.sleep,
        relogio: Callable[[], float] = time.monotonic,
    ):
        """`pasta_de_passagem` é a pasta de downloads do próprio slskd."""
        self.cliente = cliente
        self.pasta_de_passagem = Path(pasta_de_passagem)
        self._dormir = dormir
        self._relogio = relogio

    # ----------------------------------------------------------- enfileirar

    def enfileirar(self, escolhidos: list[Avaliacao]) -> list[Candidato]:
        """Põe os escolhidos na fila. Devolve os que o slskd aceitou.

        Uma recusa não derruba as outras: se um usuário saiu do ar entre a busca e o
        download, as demais opções daquela faixa continuam valendo — e é exatamente
        para isso que baixamos de usuários diferentes.
        """
        aceitos = []
        for avaliacao in escolhidos:
            try:
                self.cliente.enfileirar(avaliacao.candidato)
                aceitos.append(avaliacao.candidato)
            except Exception:  # noqa: BLE001 — qualquer falha aqui é "esse não deu"
                continue
        return aceitos

    # ----------------------------------------------------------- acompanhar

    def acompanhar(
        self,
        candidatos: list[Candidato],
        espera_max_s: float = ESPERA_PADRAO_S,
        passo_s: float = 3.0,
        ao_progredir: Callable[[Lote], None] | None = None,
    ) -> Lote:
        """Fica olhando até tudo terminar ou o tempo acabar.

        O que sobra em `presas` **não é erro**: é o caso do usuário offline ou de fila
        comprida, e é a terceira lista da tela. Cancelar seria jogar fora um download
        que ainda pode completar sozinho mais tarde.
        """
        # Guardado por (usuário, arquivo) e **atualizado no lugar**, nunca substituído
        # em bloco. A diferença não é estilo: o slskd nem sempre devolve todas as
        # transferências em toda consulta, e trocar a lista inteira pelo que veio faria
        # o lote encolher. Aí `tudo_terminou` daria True com o que sumiu da lista ainda
        # baixando, e o acompanhamento terminaria cedo — perdendo um arquivo que estava
        # a caminho.
        por_chave: dict[tuple[str, str], Transferencia] = {
            (c.usuario, c.nome_arquivo): Transferencia(candidato=c) for c in candidatos
        }
        lote = Lote(transferencias=list(por_chave.values()))

        inicio = self._relogio()
        while True:
            for atual in self.cliente.downloads():
                chave = (atual.candidato.usuario, atual.candidato.nome_arquivo)
                if chave in por_chave:
                    por_chave[chave] = atual
            lote.transferencias = list(por_chave.values())

            if ao_progredir:
                ao_progredir(lote)
            if lote.tudo_terminou:
                break
            if self._relogio() - inicio >= espera_max_s:
                break
            self._dormir(passo_s)

        return lote

    # ------------------------------------------------------------ organizar

    def achar_no_disco(self, nome_arquivo: str) -> Path | None:
        """Procura o arquivo baixado na área de passagem do slskd.

        Busca pelo nome em vez de montar o caminho: o slskd cria subpastas conforme a
        origem (a opção `destination.subdirectory`), e depender desse formato seria
        amarrar o nosso código a uma configuração que o usuário pode mudar.
        """
        if not self.pasta_de_passagem.is_dir():
            return None
        alvo = nome_arquivo.lower()
        for caminho in self.pasta_de_passagem.rglob("*"):
            if caminho.is_file() and caminho.name.lower() == alvo:
                return caminho
        return None

    def organizar(self, lote: Lote, pasta_destino: Path) -> list[Path]:
        """Move o que terminou para a pasta de destino. Devolve onde cada um ficou."""
        pasta_destino = Path(pasta_destino)
        pasta_destino.mkdir(parents=True, exist_ok=True)

        movidos = []
        for transferencia in lote.concluidas:
            origem = self.achar_no_disco(transferencia.candidato.nome_arquivo)
            if origem is None:
                continue
            destino = _destino_livre(pasta_destino / origem.name)
            try:
                shutil.move(str(origem), str(destino))
            except OSError:
                continue
            transferencia.caminho_local = str(destino)
            movidos.append(destino)
        return movidos


def _destino_livre(desejado: Path) -> Path:
    """Evita sobrescrever: `musica.flac` vira `musica (2).flac` se já houver uma.

    Nunca sobrescrever é regra, não preferência — baixar duas versões da mesma faixa
    para comparar é justamente o fluxo do app, e uma sobrescrevendo a outra acabaria
    com a comparação antes dela acontecer.
    """
    if not desejado.exists():
        return desejado
    raiz, extensao = desejado.stem, desejado.suffix
    numero = 2
    while True:
        candidato = desejado.with_name(f"{raiz} ({numero}){extensao}")
        if not candidato.exists():
            return candidato
        numero += 1
