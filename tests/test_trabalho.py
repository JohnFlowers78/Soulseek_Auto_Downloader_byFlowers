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


# ------------------------------------------------ fora da rede Soulseek


class ClienteFalso:
    """O motor de pé, mas fora da rede. A porta responde; a rede, não."""

    def __init__(self, volta=True):
        self.volta = volta
        self.esperas = 0

    def esperar_rede(self, espera_max_s=180.0, passo_s=5.0):
        self.esperas += 1
        return self.volta


def test_espera_a_rede_voltar_antes_de_mexer_no_motor(app, tmp_path):
    """Reiniciar o motor por uma queda que se resolve sozinha é estrago gratuito.

    O log mostra reconexões em menos de um segundo.
    """
    motor = MotorFalso()
    t = tarefa(app, motor=motor, tmp_path=tmp_path)
    cliente = ClienteFalso(volta=True)
    andamento = Andamento()

    assert t._esperar_a_rede(cliente, andamento)
    assert motor.ligou == 0, "a rede voltou sozinha — o motor não tinha que ser tocado"
    assert "de volta à rede" in andamento.recado


def test_rede_que_nao_volta_faz_reiniciar_o_motor(app, tmp_path):
    # Travado em "Disconnecting" por oito minutos: esperar mais não resolve.
    class MotorQueVolta(MotorFalso):
        def __init__(self):
            super().__init__()
            self.desligou = 0

        def desligar(self):
            self.desligou += 1

    motor = MotorQueVolta()
    t = tarefa(app, motor=motor, tmp_path=tmp_path)

    class ClienteQueVoltaDepois(ClienteFalso):
        def esperar_rede(self, espera_max_s=180.0, passo_s=5.0):
            self.esperas += 1
            return self.esperas > 1  # só volta depois do reinício

    assert t._esperar_a_rede(ClienteQueVoltaDepois(), Andamento())
    assert motor.desligou == 1 and motor.ligou == 1


def test_sem_motor_nao_tem_como_reiniciar(app, tmp_path):
    t = tarefa(app, motor=None, tmp_path=tmp_path)
    andamento = Andamento()

    assert not t._esperar_a_rede(ClienteFalso(volta=False), andamento)
    assert "não tenho como reiniciá-lo" in andamento.recado


def test_motor_de_fora_nao_e_reiniciado_mas_o_usuario_e_avisado(app, tmp_path):
    # slskd aberto à mão não é nosso para matar — mas calar deixaria a corrida parada
    # sem o usuário saber o que fazer.
    motor = MotorFalso()
    motor.fomos_nos = False
    t = tarefa(app, motor=motor, tmp_path=tmp_path)
    andamento = Andamento()

    assert not t._esperar_a_rede(ClienteFalso(volta=False), andamento)
    assert motor.ligou == 0
    assert "aba Motor" in andamento.recado


def test_conta_as_quedas_de_rede(app, tmp_path):
    t = tarefa(app, tmp_path=tmp_path)
    t._esperar_a_rede(ClienteFalso(), Andamento())
    t._esperar_a_rede(ClienteFalso(), Andamento())

    assert t.quedas_de_rede == 2


def test_sem_rede_a_corrida_para_em_vez_de_queimar_as_faixas(app, tmp_path, monkeypatch):
    """O defeito que custou uma playlist inteira.

    Sem rede nenhuma busca funciona. O app insistia faixa após faixa e marcava 14
    seguidas como "não vieram" — todas sem terem sido procuradas uma única vez. Agora
    ele para, e as faixas que sobraram continuam na lista "A fazer", que é a verdade.
    """
    from slskd_cliente import SemRedeSoulseek

    t = tarefa(app, tmp_path=tmp_path)
    monkeypatch.setattr(t, "_esperar_a_rede", lambda *_a: False)
    monkeypatch.setattr(t, "_recolher", lambda *_a, **_k: None)

    def cair(*_a):
        raise SemRedeSoulseek("fora da rede")

    monkeypatch.setattr(t, "_uma_faixa", cair)
    andamento = Andamento()

    t._correr(ClienteFalso(), [f"Faixa {i}" for i in range(1, 28)], andamento, tmp_path)

    assert andamento.indice == 1, "parou na primeira, não queimou as 27"
    assert t.contabilizadas == 0
    assert andamento.erros == [], "faixa não procurada não é faixa que falhou"
    assert "27 faixas restantes" in andamento.recado


def test_com_a_rede_de_volta_a_faixa_e_tentada_outra_vez(app, tmp_path, monkeypatch):
    from slskd_cliente import SemRedeSoulseek

    t = tarefa(app, tmp_path=tmp_path)
    monkeypatch.setattr(t, "_esperar_a_rede", lambda *_a: True)
    monkeypatch.setattr(t, "_recolher", lambda *_a, **_k: None)

    tentativas: list[str] = []

    def cair_so_na_primeira(chave, faixa, *_a):
        tentativas.append(str(faixa))
        if len(tentativas) == 1:
            raise SemRedeSoulseek("fora da rede")

    monkeypatch.setattr(t, "_uma_faixa", cair_so_na_primeira)
    andamento = Andamento()

    t._correr(ClienteFalso(), ["Faixa 1", "Faixa 2"], andamento, tmp_path)

    assert tentativas == ["Faixa 1", "Faixa 1", "Faixa 2"]
    assert andamento.erros == []
