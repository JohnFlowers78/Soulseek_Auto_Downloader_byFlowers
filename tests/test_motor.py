"""Testes do motor — o slskd rodando sem janela de terminal.

Nenhum teste inicia o slskd de verdade: o lançador de processo é injetado. É
importante que continue assim — pode haver uma playlist do usuário baixando, e subir
um segundo slskd com a mesma conta faria as duas sessões se expulsarem em loop.
"""

from pathlib import Path

import pytest

from motor import EstadoDoMotor, Motor, Situacao


class ProcessoFalso:
    def __init__(self, vivo=True, codigo=0, linhas=()):
        self._vivo = vivo
        self.returncode = codigo
        self.stdout = iter(linhas)
        self.terminado = False
        self.matado = False

    def poll(self):
        return None if self._vivo else self.returncode

    def terminate(self):
        self.terminado = True
        self._vivo = False

    def kill(self):
        self.matado = True
        self._vivo = False

    def wait(self, timeout=None):
        self._vivo = False
        return self.returncode


def motor(tmp_path, porta_ocupada=False, processo=None, **ajustes) -> Motor:
    criados = []

    def iniciar(*args, **kwargs):
        criados.append((args, kwargs))
        return processo or ProcessoFalso()

    exe = tmp_path / "slskd.exe"
    exe.write_bytes(b"\0")

    m = Motor(
        executavel=exe,
        pasta_de_dados=tmp_path / "dados",
        iniciar_processo=iniciar,
        dormir=lambda _: None,
        **ajustes,
    )
    m._criados = criados  # type: ignore[attr-defined]
    m._porta_ocupada = porta_ocupada  # type: ignore[attr-defined]
    return m


@pytest.fixture(autouse=True)
def porta_fechada(monkeypatch):
    """Por padrão a porta está livre; cada teste que precisar muda isso."""
    import motor as modulo

    monkeypatch.setattr(modulo, "porta_atende", lambda *a, **k: False)
    return modulo


def ocupar_porta(monkeypatch):
    import motor as modulo

    monkeypatch.setattr(modulo, "porta_atende", lambda *a, **k: True)


# ------------------------------------------------------------------ estado


def test_comeca_parado(tmp_path):
    assert motor(tmp_path).situacao().estado is EstadoDoMotor.PARADO


def test_sem_executavel_diz_que_nao_achou(monkeypatch):
    # Sem caminho explícito o motor procura sozinho — e nesta máquina ACHA. Para
    # testar a máquina sem slskd é preciso apagar a busca.
    import sistema

    monkeypatch.setattr(sistema, "encontrar_slskd", lambda: None)

    situacao = Motor(executavel=None).situacao()
    assert situacao.estado is EstadoDoMotor.PARADO
    assert "não encontrado" in situacao.detalhe


def test_sem_caminho_explicito_ele_procura_sozinho(monkeypatch, tmp_path):
    import sistema

    achado = tmp_path / "slskd.exe"
    achado.write_bytes(b"\0")
    monkeypatch.setattr(sistema, "encontrar_slskd", lambda: achado)

    m = Motor(executavel=None)
    assert m.executavel == achado
    # E a pasta de dados vem junto, ao lado do executável.
    assert m.pasta_de_dados == achado.parent / "dados"


def test_porta_ocupada_por_outro_e_reconhecida(tmp_path, monkeypatch):
    # Pode ser um slskd que o próprio usuário abriu à mão.
    ocupar_porta(monkeypatch)
    situacao = motor(tmp_path).situacao()

    assert situacao.estado is EstadoDoMotor.DE_FORA
    assert situacao.atende


# ------------------------------------------------------------------- ligar


def test_ligar_inicia_o_processo(tmp_path):
    m = motor(tmp_path)
    m.ligar()

    assert len(m._criados) == 1
    (args, kwargs) = m._criados[0]
    assert "--app-dir" in args[0]


def test_ligar_pede_para_nao_abrir_janela(tmp_path):
    # O pedido que originou este módulo: nada de console piscando na tela.
    m = motor(tmp_path)
    m.ligar()

    (_, kwargs) = m._criados[0]
    assert "creationflags" in kwargs


def test_nao_sobe_um_segundo_slskd(tmp_path, monkeypatch):
    # Duas sessões da mesma conta Soulseek se expulsam em loop. Nunca duplicar.
    ocupar_porta(monkeypatch)
    m = motor(tmp_path)
    situacao = m.ligar()

    assert m._criados == []
    assert situacao.estado is EstadoDoMotor.DE_FORA


def test_executavel_que_nao_existe_falha_com_recado(tmp_path):
    m = Motor(executavel=tmp_path / "nao_existe.exe", iniciar_processo=lambda *a, **k: None)
    situacao = m.ligar()

    assert situacao.estado is EstadoDoMotor.PARADO
    assert "não encontrado" in situacao.detalhe


def test_erro_ao_iniciar_vira_situacao_e_nao_excecao(tmp_path):
    def explodir(*_a, **_k):
        raise OSError("acesso negado")

    exe = tmp_path / "slskd.exe"
    exe.write_bytes(b"\0")
    m = Motor(executavel=exe, iniciar_processo=explodir)

    situacao = m.ligar()
    assert situacao.estado is EstadoDoMotor.FALHOU
    assert "acesso negado" in situacao.detalhe


def test_subindo_enquanto_a_porta_nao_abre(tmp_path):
    # A primeira execução varre a pasta compartilhada antes de abrir a porta: isso
    # parece travamento e precisa de um estado próprio.
    m = motor(tmp_path)
    m.ligar()
    assert m.situacao().estado is EstadoDoMotor.SUBINDO


def test_processo_que_morreu_vira_falhou(tmp_path):
    m = motor(tmp_path, processo=ProcessoFalso(vivo=False, codigo=1))
    m.ligar()

    situacao = m.situacao()
    assert situacao.estado is EstadoDoMotor.FALHOU
    assert "código 1" in situacao.detalhe


# ---------------------------------------------------------------- desligar


def test_desliga_o_que_nos_subimos(tmp_path):
    processo = ProcessoFalso()
    m = motor(tmp_path, processo=processo)
    m.ligar()
    m.desligar()

    assert processo.terminado


def test_nao_derruba_slskd_que_nao_e_nosso(tmp_path, monkeypatch):
    ocupar_porta(monkeypatch)
    m = motor(tmp_path)
    m.desligar()

    assert m._criados == []  # nem subimos, nem derrubamos


def test_processo_teimoso_e_morto(tmp_path):
    import subprocess

    class Teimoso(ProcessoFalso):
        def wait(self, timeout=None):
            raise subprocess.TimeoutExpired("slskd", timeout or 0)

    processo = Teimoso()
    m = motor(tmp_path, processo=processo)
    m.ligar()
    m.desligar()

    assert processo.matado


# --------------------------------------------------------------------- log


def test_guarda_o_log_do_slskd(tmp_path):
    # Sem console, é o único lugar onde essas linhas existem.
    linhas = ["[INF] Application started", "[INF] Logged in to the Soulseek server as joaoflores"]
    m = motor(tmp_path, processo=ProcessoFalso(linhas=linhas))
    m.ligar()

    import time as _t

    for _ in range(50):
        if len(m.log) >= 2:
            break
        _t.sleep(0.01)

    assert m.usuario_logado() == "joaoflores"
    assert len(m.log_recente()) == 2


def test_sem_log_nao_ha_usuario_logado(tmp_path):
    assert motor(tmp_path).usuario_logado() == ""


# ---------------------------------------------------------------- situação


def test_a_situacao_se_descreve():
    assert "parado" in str(Situacao(EstadoDoMotor.PARADO))
    assert "— x" in str(Situacao(EstadoDoMotor.FALHOU, "x"))


def test_esperar_atender_desiste_no_tempo_limite(tmp_path):
    relogio = {"t": 0.0}

    def andar():
        relogio["t"] += 1.0
        return relogio["t"]

    m = motor(tmp_path, relogio=andar)
    m.ligar()
    situacao = m.esperar_atender(espera_max_s=5)

    assert situacao.estado is EstadoDoMotor.FALHOU
    assert "não abriu" in situacao.detalhe
