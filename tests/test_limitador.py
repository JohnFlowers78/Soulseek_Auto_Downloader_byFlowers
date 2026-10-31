"""Testes do limitador de buscas.

Relógio e `sleep` são falsos: o tempo anda porque o teste manda, não porque esperou.
Sem isso, cada caso custaria 220 segundos reais — e um teste que ninguém roda não
protege de banimento nenhum.
"""

import threading

import pytest

from limitador import JANELA_PADRAO_S, LIMITE_PADRAO, LimitadorDeBuscas


class RelogioFalso:
    """Um relógio que só anda quando mandam, e um `sleep` que apenas adianta o relógio."""

    def __init__(self, inicio: float = 1000.0):
        self.agora = inicio
        self.dormidas: list[float] = []

    def __call__(self) -> float:
        return self.agora

    def dormir(self, segundos: float) -> None:
        self.dormidas.append(segundos)
        self.agora += segundos

    def avancar(self, segundos: float) -> None:
        self.agora += segundos


@pytest.fixture
def relogio():
    return RelogioFalso()


def criar(relogio, limite=3, janela_s=10.0) -> LimitadorDeBuscas:
    return LimitadorDeBuscas(
        limite=limite, janela_s=janela_s, relogio=relogio, dormir=relogio.dormir
    )


# ------------------------------------------------------------------ padrões


def test_os_padroes_sao_os_da_comunidade():
    # Mudar estes números sem pensar é o caminho mais curto para 30 minutos de banimento.
    limitador = LimitadorDeBuscas()
    assert limitador.limite == LIMITE_PADRAO == 34
    assert limitador.janela_s == JANELA_PADRAO_S == 220


@pytest.mark.parametrize("limite, janela", [(0, 10), (-1, 10), (3, 0), (3, -5)])
def test_configuracao_sem_sentido_e_recusada(limite, janela):
    with pytest.raises(ValueError):
        LimitadorDeBuscas(limite=limite, janela_s=janela)


# ------------------------------------------------------------------ contagem


def test_comeca_com_tudo_livre(relogio):
    limitador = criar(relogio)
    assert limitador.restantes == 3
    assert limitador.usadas == 0
    assert limitador.pode_buscar_agora


def test_cada_busca_consome_uma_vaga(relogio):
    limitador = criar(relogio)
    limitador.registrar()
    assert limitador.usadas == 1
    assert limitador.restantes == 2


def test_no_limite_nao_pode_mais_buscar(relogio):
    limitador = criar(relogio)
    for _ in range(3):
        limitador.registrar()

    assert limitador.restantes == 0
    assert not limitador.pode_buscar_agora


def test_a_vaga_volta_quando_a_busca_sai_da_janela(relogio):
    limitador = criar(relogio, limite=3, janela_s=10.0)
    for _ in range(3):
        limitador.registrar()
    assert limitador.restantes == 0

    relogio.avancar(10.1)
    assert limitador.restantes == 3
    assert limitador.pode_buscar_agora


def test_as_vagas_voltam_uma_a_uma_conforme_envelhecem(relogio):
    # As buscas foram feitas em momentos diferentes, então expiram em momentos diferentes.
    limitador = criar(relogio, limite=3, janela_s=10.0)
    limitador.registrar()
    relogio.avancar(4)
    limitador.registrar()
    relogio.avancar(4)
    limitador.registrar()
    assert limitador.restantes == 0

    relogio.avancar(2.1)  # a primeira completa 10.1s
    assert limitador.restantes == 1

    relogio.avancar(4)
    assert limitador.restantes == 2


# -------------------------------------------------------------- espera


def test_sem_estourar_o_limite_nao_ha_espera(relogio):
    limitador = criar(relogio)
    limitador.registrar()
    assert limitador.espera_necessaria_s() == 0.0


def test_a_espera_e_ate_a_mais_antiga_sair_da_janela(relogio):
    limitador = criar(relogio, limite=3, janela_s=10.0)
    for _ in range(3):
        limitador.registrar()

    relogio.avancar(4)
    # a mais antiga foi em t=0; sai da janela em t=10; agora é t=4 → faltam 6
    assert limitador.espera_necessaria_s() == pytest.approx(6.0)


def test_a_espera_nunca_e_negativa(relogio):
    limitador = criar(relogio, limite=1, janela_s=10.0)
    limitador.registrar()
    relogio.avancar(99)
    assert limitador.espera_necessaria_s() == 0.0


# -------------------------------------------------------------- aguardar


def test_aguardar_nao_dorme_quando_ha_vaga(relogio):
    limitador = criar(relogio)
    esperou = limitador.aguardar_vez()

    assert esperou == 0.0
    assert relogio.dormidas == []
    assert limitador.usadas == 1


def test_aguardar_dorme_o_necessario_e_depois_registra(relogio):
    limitador = criar(relogio, limite=2, janela_s=10.0)
    limitador.aguardar_vez()
    limitador.aguardar_vez()
    assert relogio.dormidas == []

    esperou = limitador.aguardar_vez()

    assert esperou == pytest.approx(10.0)
    assert relogio.dormidas == [pytest.approx(10.0)]
    assert limitador.usadas == 1  # as duas antigas saíram da janela


def test_uma_sequencia_longa_respeita_o_ritmo(relogio):
    # 7 buscas com limite 3 e janela 10: as 3 primeiras saem na hora, e depois o
    # limitador segura o passo.
    limitador = criar(relogio, limite=3, janela_s=10.0)
    inicio = relogio.agora
    for _ in range(7):
        limitador.aguardar_vez()

    decorrido = relogio.agora - inicio
    assert decorrido == pytest.approx(20.0)
    assert limitador.usadas <= 3


def test_o_limitador_nunca_deixa_passar_do_limite_na_janela(relogio):
    # A garantia que não pode falhar: em qualquer instante, nunca mais que `limite`
    # buscas dentro de uma janela.
    limitador = criar(relogio, limite=3, janela_s=10.0)
    horarios = []
    for _ in range(12):
        limitador.aguardar_vez()
        horarios.append(relogio.agora)

    for i, momento in enumerate(horarios):
        na_janela = [h for h in horarios[: i + 1] if h > momento - 10.0]
        assert len(na_janela) <= 3, f"estourou em t={momento}: {na_janela}"


def test_duas_threads_nao_estouram_o_limite():
    # Com relógio real e janela curta: o que importa é não passar do limite.
    limitador = LimitadorDeBuscas(limite=4, janela_s=0.4)
    contador = {"feitas": 0}
    trava = threading.Lock()

    def trabalhar():
        for _ in range(6):
            limitador.aguardar_vez()
            with trava:
                contador["feitas"] += 1

    fios = [threading.Thread(target=trabalhar) for _ in range(3)]
    for fio in fios:
        fio.start()
    for fio in fios:
        fio.join(timeout=20)

    assert contador["feitas"] == 18
    assert limitador.usadas <= 4


# ------------------------------------------------------- estimativa de tempo


def test_estimativa_zero_quando_tudo_cabe_de_uma_vez(relogio):
    limitador = criar(relogio, limite=3, janela_s=10.0)
    assert limitador.tempo_estimado_s(3) == 0.0
    assert limitador.tempo_estimado_s(0) == 0.0


def test_estimativa_de_uma_janela_a_mais(relogio):
    limitador = criar(relogio, limite=3, janela_s=10.0)
    assert limitador.tempo_estimado_s(4) == pytest.approx(10.0)
    assert limitador.tempo_estimado_s(6) == pytest.approx(10.0)


def test_estimativa_de_varias_janelas(relogio):
    limitador = criar(relogio, limite=3, janela_s=10.0)
    assert limitador.tempo_estimado_s(7) == pytest.approx(20.0)


def test_estimativa_conta_as_vagas_ja_gastas(relogio):
    limitador = criar(relogio, limite=3, janela_s=10.0)
    limitador.registrar()
    limitador.registrar()
    # só 1 vaga livre; faltam 2 → precisa de uma janela
    assert limitador.tempo_estimado_s(3) == pytest.approx(10.0)


def test_estimativa_com_os_numeros_reais_da_rede():
    """O aviso que o usuário precisa ver ANTES de mandar uma playlist grande.

    100 faixas × 3 variantes = 300 buscas. As 34 primeiras saem sem espera; as 266
    restantes custam 8 janelas de 220 s = 1760 s ≈ 29 minutos **só de espera**.

    É um piso, não uma previsão: cada busca ainda leva o tempo dela na rede (o
    `searchTimeout` padrão do slskd é 15 s), e isso entra por cima.
    """
    limitador = LimitadorDeBuscas()
    assert limitador.tempo_estimado_s(300) == pytest.approx(1760.0)
    assert 29 < limitador.tempo_estimado_s(300) / 60 < 30
