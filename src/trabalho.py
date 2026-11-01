"""O trabalho pesado rodando **fora** da thread da janela.

Qt desenha e responde ao mouse numa thread só. Qualquer coisa demorada feita nela
congela a interface — e aqui "demorado" é a regra, não a exceção: uma playlist leva
horas, e o limitador de buscas às vezes dorme minutos de propósito.

Por isso tudo que fala com a rede vive aqui dentro, num `QThread`, conversando com a
tela só por sinais.

> **Armadilha do Qt já registrada neste projeto:** `lambda: self…` ligado a sinal de
> janela de topo pode abortar o Python na saída. Aqui os sinais são sempre ligados a
> **métodos**, nunca a lambdas que capturam `self`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtCore import QObject, QThread, Signal

import sistema
from baixador import Baixador
from buscador import Buscador, ResultadoDaBusca
from config import Config
from leitor_spotify import (
    ErroSpotify,
    LeitorSpotify,
    acesso_a_partir_do_refresh,
    autorizar_no_navegador,
    extrair_id_da_faixa,
)
from modelos import EstadoTransferencia, Faixa
from normalizador import nome_pasta_segura
from politica import Foco
from qualidade import Criterios
from slskd_cliente import ClienteSlskd, ErroSlskd


def criterios_de(config: Config) -> Criterios:
    padrao = Criterios()
    sem_perda = tuple(f for f in config.formatos_aceitos if f in padrao.formatos_sem_perda)
    com_perda = tuple(f for f in config.formatos_aceitos if f in padrao.formatos_com_perda)
    return Criterios(
        formatos_sem_perda=sem_perda or padrao.formatos_sem_perda,
        formatos_com_perda=com_perda or padrao.formatos_com_perda,
        minimo_mp3_kbps=config.minimo_mp3_kbps,
        minimo_aac_kbps=config.minimo_aac_kbps,
    )


@dataclass
class Andamento:
    """Uma foto do que está acontecendo, para a tela desenhar."""

    indice: int = 0
    total: int = 0
    faixa: str = ""
    recado: str = ""
    baixadas: list[str] = field(default_factory=list)
    #: O que esta baixando AGORA: (nome do arquivo, porcentagem). E a unica parte do
    #: andamento que encolhe — um arquivo sai daqui quando termina.
    baixando: list[tuple[str, int]] = field(default_factory=list)
    presas: list[str] = field(default_factory=list)
    nao_vieram: list[str] = field(default_factory=list)
    erros: list[str] = field(default_factory=list)

    @property
    def porcentagem(self) -> int:
        return int(self.indice / self.total * 100) if self.total else 0


class TarefaDeEntrada(QThread):
    """Entra na conta do Spotify abrindo o navegador."""

    terminou = Signal(bool, str)  # deu certo, recado

    def __init__(self, client_id: str):
        super().__init__()
        self.client_id = client_id
        self.refresh_token = ""

    def run(self) -> None:  # noqa: D102 - exigido pelo QThread
        try:
            tokens = autorizar_no_navegador(self.client_id, avisar=lambda *_a: None)
        except ErroSpotify as erro:
            self.terminou.emit(False, str(erro))
            return
        except Exception as erro:  # noqa: BLE001 — a janela não pode morrer por isto
            self.terminou.emit(False, f"{type(erro).__name__}: {erro}")
            return

        self.refresh_token = tokens.get("refresh_token", "")
        nome = ""
        try:
            eu = LeitorSpotify(tokens["access_token"])._get("https://api.spotify.com/v1/me")
            nome = eu.get("display_name") or eu.get("id") or ""
        except Exception:  # noqa: BLE001 — entrou; saber o nome é bônus
            pass
        self.terminou.emit(True, nome)


class TarefaDeDownload(QThread):
    """Baixa uma playlist inteira, ou uma faixa só, avisando a tela a cada passo."""

    #: Assim que a playlist e lida, ANTES de comecar a baixar. O usuario precisa ver
    #: o que vai ser feito; ate aqui a janela so mostrava a faixa da vez.
    playlist_lida = Signal(str, list)  # nome, [texto de cada faixa]
    progrediu = Signal(object)         # Andamento
    terminou = Signal(object, str)     # Andamento, pasta de destino
    falhou = Signal(str)

    def __init__(
        self,
        config: Config,
        entrada: str,
        foco: Foco,
        avulsa: bool = False,
        motor=None,
    ):
        super().__init__()
        self.config = config
        self.entrada = entrada.strip()
        self.foco = foco
        self.avulsa = avulsa
        #: Dono do processo do slskd. Com ele, a tarefa religa o motor quando ele
        #: morre em vez de perder a corrida. Sem ele, so sabe avisar.
        self.motor = motor
        self.religadas = 0
        self._parar = False

    def pedir_para_parar(self) -> None:
        """Pede para encerrar na próxima faixa. O que já baixou fica na pasta."""
        self._parar = True

    # ------------------------------------------------------------------ run

    def run(self) -> None:
        """Ponto de entrada da thread. **Nada** pode escapar daqui.

        Exceção que sai de `QThread.run()` não vira erro tratável: o Qt só imprime
        "Error calling Python override of QThread::run()" no terminal e a janela fica
        com os botões travados, esperando um fim que não vem. Para o usuário, parece
        que o programa congelou — foi exatamente o que aconteceu.
        """
        try:
            self._correr_tudo()
        except Exception as erro:  # noqa: BLE001 — último anteparo antes do Qt
            self.falhou.emit(f"{type(erro).__name__}: {erro}")

    def _correr_tudo(self) -> None:
        andamento = Andamento()
        try:
            nome, faixas = self._ler_entrada()
        except (ErroSpotify, ErroSlskd) as erro:
            self.falhou.emit(str(erro))
            return
        except Exception as erro:  # noqa: BLE001
            self.falhou.emit(f"{type(erro).__name__}: {erro}")
            return

        if not faixas:
            self.falhou.emit("Não achei nenhuma faixa nessa entrada.")
            return

        andamento.total = len(faixas)
        self.playlist_lida.emit(nome, [str(f) for f in faixas])
        destino = Path(self.config.pasta_mae_playlists) / nome_pasta_segura(nome)

        with ClienteSlskd(
            url=self.config.slskd_url, chave_api=self.config.slskd_api_key
        ) as cliente:
            try:
                if not cliente.conectado():
                    self.falhou.emit(
                        "O slskd respondeu, mas não está logado na rede Soulseek. "
                        "Ligue o motor e espere ele entrar."
                    )
                    return
            except ErroSlskd as erro:
                self.falhou.emit(str(erro))
                return

            self._correr(cliente, faixas, andamento, destino)

        self.terminou.emit(andamento, str(destino))

    # -------------------------------------------------------------- entrada

    def _ler_entrada(self) -> tuple[str, list[Faixa]]:
        """Descobre o que foi colado e devolve `(nome, faixas)`."""
        if self.avulsa and not extrair_id_da_faixa(self.entrada):
            from leitor_pasta import extrair_do_nome

            artista, titulo = extrair_do_nome(self.entrada)
            faixa = Faixa(artista=artista, titulo=titulo)
            return "Buscas avulsas", [faixa]

        acesso, refresh = acesso_a_partir_do_refresh(
            self.config.spotify_client_id, self.config.spotify_refresh_token
        )
        if refresh != self.config.spotify_refresh_token:
            self.config.spotify_refresh_token = refresh
            self.config.salvar()

        leitor = LeitorSpotify(acesso)
        if extrair_id_da_faixa(self.entrada):
            faixa = leitor.faixa_avulsa(self.entrada)
            return "Buscas avulsas", [faixa]
        return leitor.ler(self.entrada)

    # --------------------------------------------------------------- correr

    def _correr(self, cliente, faixas, andamento: Andamento, destino: Path) -> None:
        buscador = Buscador(
            cliente,
            criterios=criterios_de(self.config),
            quantidade_por_faixa=max(3, self.config.quantidade_por_faixa),
            foco=self.foco,
        )
        passagem = (sistema.encontrar_slskd() or Path()).parent / "dados" / "downloads"
        operario = Baixador(cliente, passagem)
        pendentes: dict[int, list] = {}

        for i, faixa in enumerate(faixas, 1):
            if self._parar:
                andamento.recado = "interrompido — o que já baixou está na pasta"
                break

            andamento.indice = i
            andamento.faixa = str(faixa)
            self.progrediu.emit(andamento)

            try:
                resultado = self._uma_faixa(faixa, buscador, operario, pendentes)
                self._anotar(andamento, resultado)
            except ErroSlskd as erro:
                # O slskd morre sozinho de vez em quando: ele tem um defeito conhecido
                # no caminho de desistir de entrar numa fila remota (exceção fatal que
                # leva o processo junto). Quando isso acontece, religar e seguir é
                # muito melhor que perder uma corrida de horas.
                if self._religar_motor(andamento):
                    try:
                        resultado = self._uma_faixa(faixa, buscador, operario, pendentes)
                        self._anotar(andamento, resultado)
                    except Exception as outra:  # noqa: BLE001
                        andamento.erros.append(f"{faixa} — {type(outra).__name__}: {outra}")
                else:
                    andamento.erros.append(f"{faixa} — {erro}")
            except Exception as erro:  # noqa: BLE001 — uma faixa não derruba a corrida
                andamento.erros.append(f"{faixa} — {type(erro).__name__}: {erro}")

            # Uma consulta cobre todos os pendentes (ver `conferir_varios`).
            self._recolher(operario, pendentes, destino, andamento, bloquear=False)
            self.progrediu.emit(andamento)

        self._recolher(operario, pendentes, destino, andamento, bloquear=True)

    def _religar_motor(self, andamento: Andamento) -> bool:
        """Religa o slskd se ele tiver morrido. Devolve se voltou ao ar.

        O slskd 0.26.2 tem um defeito que derruba o processo inteiro: ao desistir de
        entrar numa fila remota depois de 180 segundos, ele cancela um token já
        descartado e isso sobe como exceção fatal. Não é o nosso código, e não há
        versão nova que conserte — então o jeito é levantar e continuar.
        """
        from motor import porta_atende

        if porta_atende():
            return True  # não era o motor; o erro veio de outra coisa
        if self.motor is None:
            andamento.recado = "o motor caiu e não tenho como religá-lo daqui"
            return False

        self.religadas += 1
        andamento.recado = f"o motor caiu — religando ({self.religadas}ª vez)..."
        self.progrediu.emit(andamento)

        self.motor.ligar()
        voltou = self.motor.esperar_atender(espera_max_s=180).atende
        andamento.recado = "motor de volta" if voltou else "não consegui religar o motor"
        self.progrediu.emit(andamento)
        return voltou

    def _uma_faixa(self, faixa, buscador, operario, pendentes) -> ResultadoDaBusca:
        resultado = buscador.buscar_faixa(faixa)
        if resultado.escolhas:
            fila = operario.enfileirar(resultado.escolhidos)
            if fila.aceitos:
                pendentes[id(resultado)] = fila.aceitos
        return resultado

    @staticmethod
    def _anotar(andamento: Andamento, resultado: ResultadoDaBusca) -> None:
        if not resultado.escolhas:
            andamento.nao_vieram.append(resultado.resumo())

    def _recolher(self, operario, pendentes, destino, andamento, bloquear: bool) -> None:
        """Move o que terminou para a pasta. **Nunca levanta.**

        A proteção fica aqui dentro, e não em quem chama. Eu tinha protegido duas das
        três chamadas e esquecido a terceira — a de passagem, dentro do laço — e foi
        exatamente ela que derrubou a corrida quando o slskd morreu:

            File "trabalho.py", line 213, in _correr
              self._recolher(..., bloquear=False)
            ErroSlskd: Não consegui falar com o slskd... Ele está rodando?

        Guardar a função em vez das chamadas também protege a próxima chamada que
        alguém escrever sem lembrar disso.

        Falhar ao recolher não é motivo para derrubar nada: o que está pendente segue
        pendente, e o slskd retoma esses downloads sozinho quando voltar.
        """
        if not pendentes:
            return

        try:
            self._recolher_mesmo(operario, pendentes, destino, andamento, bloquear)
        except ErroSlskd as erro:
            if self._religar_motor(andamento):
                try:
                    self._recolher_mesmo(operario, pendentes, destino, andamento, bloquear)
                except ErroSlskd as outra:
                    andamento.recado = f"não consegui recolher: {outra}"
            else:
                andamento.recado = f"o motor caiu: {erro}"
        except Exception as erro:  # noqa: BLE001 — papel não derruba corrida
            andamento.recado = f"não consegui recolher: {type(erro).__name__}: {erro}"

    def _recolher_mesmo(self, operario, pendentes, destino, andamento, bloquear: bool) -> None:

        if bloquear:
            for chave in list(pendentes):
                lote = operario.acompanhar(pendentes[chave], espera_max_s=300)
                self._guardar(operario, lote, destino, andamento)
                del pendentes[chave]
            return

        andando: list[tuple[str, int]] = []
        for chave, lote in operario.conferir_varios(dict(pendentes)).items():
            self._guardar(operario, lote, destino, andamento)
            andando += [
                (t.candidato.nome_arquivo, int(t.progresso * 100))
                for t in lote.transferencias
                if t.estado is EstadoTransferencia.BAIXANDO
            ]
            if lote.tudo_terminou:
                del pendentes[chave]
        andamento.baixando = andando

    @staticmethod
    def _guardar(operario, lote, destino, andamento: Andamento) -> None:
        for caminho in operario.organizar(lote, destino):
            andamento.baixadas.append(caminho.name)
        andamento.presas = [
            t.candidato.nome_arquivo for t in lote.presas
        ] or andamento.presas
