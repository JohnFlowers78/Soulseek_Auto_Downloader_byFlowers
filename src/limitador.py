"""O limitador de buscas — a peça que evita 30 minutos de banimento.

O servidor do Soulseek **bane por 30 minutos** quem busca demais em pouco tempo. O número
de referência, usado pelas ferramentas consolidadas da comunidade, é **34 buscas a cada
220 segundos**.

Isso não é detalhe de implementação: é o que dita o ritmo do app inteiro. Uma playlist de
100 faixas × 3 variantes são 300 buscas — **mais de meia hora no melhor caso**, mesmo que
tudo dê certo.

O relógio e o `sleep` são **injetáveis** de propósito. Sem isso, testar o limitador
exigiria esperar 220 segundos de verdade a cada caso — e aí ninguém testa, e aí o
banimento acontece em produção.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from typing import Callable

#: Padrões da comunidade. Subir o limite ou encurtar a janela é pedir banimento.
LIMITE_PADRAO = 34
JANELA_PADRAO_S = 220


class LimitadorDeBuscas:
    """Segura a fila para não passar de `limite` buscas a cada `janela_s` segundos.

    É seguro usar da thread de trabalho enquanto a tela lê `restantes` e
    `espera_necessaria_s()` da thread principal — tudo que toca a fila de horários está
    sob trava.
    """

    def __init__(
        self,
        limite: int = LIMITE_PADRAO,
        janela_s: float = JANELA_PADRAO_S,
        relogio: Callable[[], float] = time.monotonic,
        dormir: Callable[[float], None] = time.sleep,
    ):
        if limite < 1:
            raise ValueError("o limite precisa ser pelo menos 1")
        if janela_s <= 0:
            raise ValueError("a janela precisa ser positiva")

        self.limite = limite
        self.janela_s = janela_s
        self._relogio = relogio
        self._dormir = dormir
        self._horarios: deque[float] = deque()
        self._trava = threading.Lock()

    # ------------------------------------------------------------------ estado

    def _descartar_antigas(self, agora: float) -> None:
        """Tira da fila as buscas que já saíram da janela. Chamar com a trava tomada."""
        limite_inferior = agora - self.janela_s
        while self._horarios and self._horarios[0] <= limite_inferior:
            self._horarios.popleft()

    @property
    def usadas(self) -> int:
        """Quantas buscas contam dentro da janela agora."""
        with self._trava:
            self._descartar_antigas(self._relogio())
            return len(self._horarios)

    @property
    def restantes(self) -> int:
        """Quantas buscas ainda cabem sem esperar."""
        return max(0, self.limite - self.usadas)

    def espera_necessaria_s(self) -> float:
        """Quantos segundos faltam até caber outra busca. Zero quando já cabe.

        É este número que a tela mostra como "aguardando X s" — sem ele o app parece
        travado e o usuário mata o processo no meio de uma playlist.
        """
        with self._trava:
            agora = self._relogio()
            self._descartar_antigas(agora)
            if len(self._horarios) < self.limite:
                return 0.0
            return max(0.0, self._horarios[0] + self.janela_s - agora)

    @property
    def pode_buscar_agora(self) -> bool:
        return self.espera_necessaria_s() == 0.0

    # ------------------------------------------------------------------ uso

    def registrar(self) -> None:
        """Anota que uma busca foi feita agora.

        Separado de `aguardar_vez()` para o caso de quem chama já ter esperado por conta
        própria (a tela, por exemplo, mostrando contagem regressiva).
        """
        with self._trava:
            agora = self._relogio()
            self._descartar_antigas(agora)
            self._horarios.append(agora)

    def aguardar_vez(self) -> float:
        """Espera o tempo necessário, anota a busca, e devolve quanto esperou.

        O laço existe porque entre calcular a espera e terminar de dormir outra thread
        pode ter tomado a vaga. Dormir uma vez e sair seria uma corrida — e o preço de
        perder essa corrida é meia hora de banimento.
        """
        total_esperado = 0.0
        while True:
            espera = self.espera_necessaria_s()
            if espera <= 0:
                with self._trava:
                    agora = self._relogio()
                    self._descartar_antigas(agora)
                    if len(self._horarios) < self.limite:
                        self._horarios.append(agora)
                        return total_esperado
                # Alguém passou na frente enquanto não estávamos olhando: volta ao laço.
                continue
            self._dormir(espera)
            total_esperado += espera

    def tempo_estimado_s(self, quantas_buscas: int) -> float:
        """Quanto tempo, no mínimo, levam `quantas_buscas` a partir de agora.

        Serve para avisar **antes de começar**: uma pasta com 200 músicas são mais de uma
        hora, e o usuário precisa saber disso de cara, não no meio.
        """
        if quantas_buscas <= 0:
            return 0.0
        livres = self.restantes
        if quantas_buscas <= livres:
            return 0.0
        faltam = quantas_buscas - livres
        # Cada janela cheia libera `limite` buscas. A última leva o resto de uma janela.
        janelas_cheias, resto = divmod(faltam, self.limite)
        total = janelas_cheias * self.janela_s
        if resto:
            total += self.janela_s
        return float(total)
