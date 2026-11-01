"""Sobe e derruba o slskd **sem janela de terminal**.

Pedido direto do usuário: *"quero o motor do software sem necessitar de um terminal
aberto"*. Até aqui, usar o app exigia deixar uma janela de console aberta a sessão
inteira — e fechá-la por engano derrubava tudo no meio de uma playlist.

Três cuidados que o código precisa ter:

* **Não subir um segundo slskd.** Se a porta já atende, alguém já está lá — pode ser
  um que o próprio usuário abriu à mão. Matar ou duplicar seria péssimo: duas sessões
  da mesma conta Soulseek se expulsam em loop.
* **Não deixar órfão.** Processo iniciado pela janela morre com ela.
* **Guardar o log.** Sem console, a saída do slskd não vai para lugar nenhum — e é
  onde aparece "Logged in to the Soulseek server as fulano".
"""

from __future__ import annotations

import socket
import subprocess
import threading
import time
from collections import deque
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Callable

import sistema

PORTA_PADRAO = 5030

#: No Windows, impede o console preto de piscar na tela. Em outros sistemas não existe
#: e o valor vira 0, que é "sem sinalizador".
_SEM_JANELA = getattr(subprocess, "CREATE_NO_WINDOW", 0)


class EstadoDoMotor(str, Enum):
    PARADO = "parado"
    SUBINDO = "subindo"
    RODANDO = "rodando"
    DE_FORA = "de fora"      # alguém já estava na porta — não fomos nós
    FALHOU = "falhou"


@dataclass
class Situacao:
    """O que mostrar na tela sobre o motor."""

    estado: EstadoDoMotor
    detalhe: str = ""

    @property
    def atende(self) -> bool:
        return self.estado in (EstadoDoMotor.RODANDO, EstadoDoMotor.DE_FORA)

    def __str__(self) -> str:
        return f"{self.estado.value}{f' — {self.detalhe}' if self.detalhe else ''}"


def porta_atende(porta: int = PORTA_PADRAO, espera_s: float = 0.4) -> bool:
    """Checa a porta com tempo-limite curto.

    No Windows, um `connect` em 127.0.0.1 sem ninguém escutando leva ~2 segundos para
    falhar. Sem o tempo-limite curto, cada conferência trava a interface por esse tanto.
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(espera_s)
            return s.connect_ex(("127.0.0.1", porta)) == 0
    except OSError:
        return False


class Motor:
    """Dono do processo do slskd enquanto a janela estiver aberta."""

    def __init__(
        self,
        executavel: Path | None = None,
        pasta_de_dados: Path | None = None,
        porta: int = PORTA_PADRAO,
        iniciar_processo: Callable[..., subprocess.Popen] | None = None,
        relogio: Callable[[], float] = time.monotonic,
        dormir: Callable[[float], None] = time.sleep,
    ):
        self.executavel = executavel or sistema.encontrar_slskd()
        self.porta = porta
        self.pasta_de_dados = pasta_de_dados or (
            self.executavel.parent / "dados" if self.executavel else None
        )
        self._iniciar_processo = iniciar_processo or subprocess.Popen
        self._relogio = relogio
        self._dormir = dormir

        self._processo: subprocess.Popen | None = None
        #: As últimas linhas do log. Sem console, é o único lugar onde elas existem.
        self.log: deque[str] = deque(maxlen=400)

    # ------------------------------------------------------------------ estado

    def situacao(self) -> Situacao:
        if self._processo and self._processo.poll() is None:
            if porta_atende(self.porta):
                return Situacao(EstadoDoMotor.RODANDO, "iniciado por este app")
            return Situacao(EstadoDoMotor.SUBINDO, "montando o cache de compartilhamento")

        if self._processo and self._processo.poll() is not None:
            codigo = self._processo.returncode
            return Situacao(EstadoDoMotor.FALHOU, f"o slskd saiu com código {codigo}")

        if porta_atende(self.porta):
            return Situacao(EstadoDoMotor.DE_FORA, "já havia um slskd rodando")

        if not self.executavel:
            return Situacao(EstadoDoMotor.PARADO, "slskd não encontrado nesta máquina")
        return Situacao(EstadoDoMotor.PARADO)

    @property
    def fomos_nos(self) -> bool:
        """Só derrubamos o que nós mesmos subimos."""
        return self._processo is not None and self._processo.poll() is None

    # ------------------------------------------------------------------ ligar

    def ligar(self) -> Situacao:
        """Sobe o slskd em segundo plano. Não faz nada se já houver um atendendo."""
        if porta_atende(self.porta):
            # Pode ser um que o usuário abriu à mão. Subir outro faria as duas sessões
            # da mesma conta Soulseek se expulsarem em loop.
            return self.situacao()

        if not self.executavel or not Path(self.executavel).is_file():
            return Situacao(EstadoDoMotor.PARADO, "slskd não encontrado nesta máquina")

        comando = [str(self.executavel)]
        if self.pasta_de_dados:
            comando += ["--app-dir", str(self.pasta_de_dados)]

        try:
            self._processo = self._iniciar_processo(
                comando,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                creationflags=_SEM_JANELA,
            )
        except OSError as erro:
            return Situacao(EstadoDoMotor.FALHOU, f"não consegui iniciar: {erro}")

        self._ler_log_em_segundo_plano()
        return self.situacao()

    def _ler_log_em_segundo_plano(self) -> None:
        """Vai guardando a saída do slskd numa fila.

        Precisa ser lida de propósito: um cano cheio que ninguém esvazia trava o
        processo que escreve nele. E, sem console, é a única janela para o que o
        slskd está dizendo.
        """
        processo = self._processo
        if processo is None or processo.stdout is None:
            return

        def ler() -> None:
            for linha in processo.stdout:  # type: ignore[union-attr]
                self.log.append(linha.rstrip())

        threading.Thread(target=ler, daemon=True, name="log-do-slskd").start()

    def esperar_atender(self, espera_max_s: float = 180.0) -> Situacao:
        """Espera a porta abrir.

        O tempo-limite é generoso porque a **primeira** execução varre a pasta
        compartilhada inteira antes de abrir a porta — com acervo grande isso passa de
        um minuto e parece travamento. Das próximas vezes sobe em ~2 segundos.
        """
        inicio = self._relogio()
        while self._relogio() - inicio < espera_max_s:
            situacao = self.situacao()
            if situacao.atende or situacao.estado is EstadoDoMotor.FALHOU:
                return situacao
            self._dormir(1.0)
        return Situacao(EstadoDoMotor.FALHOU, f"a porta não abriu em {espera_max_s:.0f}s")

    # ---------------------------------------------------------------- desligar

    def desligar(self, espera_s: float = 10.0) -> Situacao:
        """Derruba **apenas** o processo que nós subimos."""
        if not self.fomos_nos:
            return self.situacao()

        processo = self._processo
        assert processo is not None
        processo.terminate()
        try:
            processo.wait(timeout=espera_s)
        except subprocess.TimeoutExpired:
            processo.kill()
        self._processo = None
        return self.situacao()

    def log_recente(self, quantas: int = 20) -> list[str]:
        return list(self.log)[-quantas:]

    def usuario_logado(self) -> str:
        """Pesca do log o nome com que o slskd entrou na rede."""
        marca = "Logged in to the Soulseek server as "
        for linha in reversed(self.log):
            if marca in linha:
                return linha.split(marca, 1)[1].strip()
        return ""
