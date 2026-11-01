"""Testes da tarefa que roda fora da thread da janela.

O assunto aqui é **sobrevivência**: o slskd morre sozinho (defeito dele, sem versão
que conserte), e nada disso pode derrubar uma corrida de horas nem travar a janela.

Nenhum teste inicia thread de verdade nem toca a rede — os métodos são exercitados
direto, com dubles.
"""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6", reason="interface gráfica não instalada")

from PySide6.QtWidgets import QApplication  # noqa: E402

from config import Config  # noqa: E402
from politica import Foco  # noqa: E402
from slskd_cliente import ErroSlskd  # noqa: E402
from trabalho import Andamento, TarefaDeDownload  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


class OperarioFalso:
    """Finge ser o Baixador. Pode quebrar quando mandarem."""

    def __init__(self, erro=None, erros_antes=0):
        self.erro = erro
        self.erros_antes = erros_antes
        self.conferidas = 0

    def conferir_varios(self, grupos):
        self.conferidas += 1
        if self.erro is not None and self.conferidas <= (self.erros_antes or 10**9):
            raise self.erro
        return {}

    def acompanhar(self, candidatos, espera_max_s=300):
        self.conferidas += 1
        if self.erro is not None and self.conferidas <= (self.erros_antes or 10**9):
            raise self.erro
        return _LoteVazio()

    def organizar(self, lote, destino):
        return []


class _LoteVazio:
    transferencias: list = []
    concluidas: list = []
    presas: list = []
    tudo_terminou = True


class MotorFalso:
    def __init__(self, volta=True):
        self.volta = volta
        self.ligou = 0

    def ligar(self):
        self.ligou += 1

    def esperar_atender(self, espera_max_s=180):
        from motor import EstadoDoMotor, Situacao

        return Situacao(
            EstadoDoMotor.RODANDO if self.volta else EstadoDoMotor.FALHOU
        )


def tarefa(app, motor=None, tmp_path=None) -> TarefaDeDownload:
    config = Config(pasta_mae_playlists=str(tmp_path or "."))
    return TarefaDeDownload(config, "qualquer coisa", Foco.SEM_PERDA, motor=motor)


@pytest.fixture(autouse=True)
def porta_fechada(monkeypatch):
    """Por padrão o motor está morto — é o cenário que interessa aqui."""
    import motor as modulo

    monkeypatch.setattr(modulo, "porta_atende", lambda *a, **k: False)


# --------------------------------------------------- recolher nunca levanta


def test_recolher_nao_levanta_quando_o_slskd_morre(app, tmp_path):
    """O erro que derrubou a corrida de verdade.

    Eu tinha protegido duas das três chamadas de `_recolher` e esquecido a de
    passagem, dentro do laço. A protecao mudou para DENTRO da funcao: assim a
    proxima chamada que alguem escrever ja nasce protegida.
    """
    t = tarefa(app, tmp_path=tmp_path)
    operario = OperarioFalso(erro=ErroSlskd("Não consegui falar com o slskd"))
    andamento = Andamento()

    t._recolher(operario, {1: ["x"]}, tmp_path, andamento, bloquear=False)

    assert "motor caiu" in andamento.recado


def test_recolher_bloqueante_tambem_nao_levanta(app, tmp_path):
    t = tarefa(app, tmp_path=tmp_path)
    operario = OperarioFalso(erro=ErroSlskd("caiu"))

    t._recolher(operario, {1: ["x"]}, tmp_path, Andamento(), bloquear=True)  # não levanta


def test_erro_inesperado_no_recolher_tambem_e_contido(app, tmp_path):
    t = tarefa(app, tmp_path=tmp_path)
    operario = OperarioFalso(erro=RuntimeError("algo muito estranho"))
    andamento = Andamento()

    t._recolher(operario, {1: ["x"]}, tmp_path, andamento, bloquear=False)

    assert "algo muito estranho" in andamento.recado


def test_sem_pendentes_nem_tenta(app, tmp_path):
    t = tarefa(app, tmp_path=tmp_path)
    operario = OperarioFalso(erro=ErroSlskd("caiu"))

    t._recolher(operario, {}, tmp_path, Andamento(), bloquear=False)
    assert operario.conferidas == 0


# ------------------------------------------------------- religar o motor


def test_religa_o_motor_e_tenta_de_novo(app, tmp_path):
    motor = MotorFalso(volta=True)
    t = tarefa(app, motor=motor, tmp_path=tmp_path)
    operario = OperarioFalso(erro=ErroSlskd("caiu"), erros_antes=1)
    andamento = Andamento()

    t._recolher(operario, {1: ["x"]}, tmp_path, andamento, bloquear=False)

    assert motor.ligou == 1
    assert operario.conferidas == 2, "tentou de novo depois de religar"
    assert t.religadas == 1


def test_sem_motor_so_avisa(app, tmp_path):
    # Sem o dono do processo, a tarefa nao tem como religar — mas nao pode quebrar.
    t = tarefa(app, motor=None, tmp_path=tmp_path)
    andamento = Andamento()

    assert not t._religar_motor(andamento)
    assert "não tenho como religá-lo" in andamento.recado


def test_motor_que_nao_volta_e_reportado(app, tmp_path):
    motor = MotorFalso(volta=False)
    t = tarefa(app, motor=motor, tmp_path=tmp_path)
    andamento = Andamento()

    assert not t._religar_motor(andamento)
    assert "não consegui religar" in andamento.recado


def test_se_a_porta_atende_nao_religa_nada(app, tmp_path, monkeypatch):
    # O erro veio de outra coisa; religar um motor vivo seria estrago gratuito.
    import motor as modulo

    monkeypatch.setattr(modulo, "porta_atende", lambda *a, **k: True)
    motor = MotorFalso()
    t = tarefa(app, motor=motor, tmp_path=tmp_path)

    assert t._religar_motor(Andamento())
    assert motor.ligou == 0


def test_conta_quantas_vezes_religou(app, tmp_path):
    motor = MotorFalso(volta=True)
    t = tarefa(app, motor=motor, tmp_path=tmp_path)

    t._religar_motor(Andamento())
    t._religar_motor(Andamento())

    assert t.religadas == 2


# ------------------------------------------------- run nunca deixa escapar


def test_run_nunca_deixa_excecao_escapar(app, tmp_path):
    """Exceção que sai de QThread.run() não vira erro tratável.

    O Qt só imprime "Error calling Python override of QThread::run()" no terminal e a
    janela fica com os botões travados, esperando um fim que não vem. Para o usuário,
    parece que o programa congelou — foi exatamente o que aconteceu.
    """
    t = tarefa(app, tmp_path=tmp_path)
    recados = []
    t.falhou.connect(recados.append)

    def explodir():
        raise RuntimeError("desastre")

    t._correr_tudo = explodir
    t.run()  # não levanta

    assert recados and "desastre" in recados[0]


def test_run_avisa_a_janela_em_vez_de_morrer_calado(app, tmp_path):
    t = tarefa(app, tmp_path=tmp_path)
    recados = []
    t.falhou.connect(recados.append)

    def explodir():
        raise ErroSlskd("o motor sumiu")

    t._correr_tudo = explodir
    t.run()

    assert len(recados) == 1
    assert "o motor sumiu" in recados[0]


# ----------------------------------------------------------------- parar


def test_pedir_para_parar_e_respeitado(app, tmp_path):
    t = tarefa(app, tmp_path=tmp_path)
    assert not t._parar

    t.pedir_para_parar()
    assert t._parar
