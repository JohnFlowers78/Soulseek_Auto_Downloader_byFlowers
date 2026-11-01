"""Busca que não terminou devolve vazio — e vazio assim não é "não existe".

Medido no slskd em corrida, 01/11/2026:

    completa=False | ele diz 5 respostas / 9 arquivos | /responses devolve 0

O app esperava 25 s e lia assim mesmo, com um comentário meu dizendo que "o que já
chegou vale". Não vale: vem lista vazia. E o tempo real das buscas, do `startedAt` ao
`endedAt` que o próprio slskd grava, era quase sempre MAIOR que 25 s —
`Josh Butler Hap Hazard` levou 38,7 s e `Fcukers Bon Bon`, 41,4 s. O app relatou
"nada na rede" com 42 arquivos guardados dentro do motor.
"""

import pytest

from buscador import Buscador
from limitador import LimitadorDeBuscas
from modelos import Faixa
from slskd_cliente import ClienteSlskd


class TransporteLento:
    """A busca só fica completa depois de `voltas` consultas de estado."""

    def __init__(self, voltas: int, arquivos: list | None = None):
        self.voltas = voltas
        self.arquivos = arquivos or []
        self.consultas = 0

    def __call__(self, metodo, caminho, corpo=None):
        if caminho.endswith("/responses"):
            # O slskd só entrega resposta com a busca fechada. Antes disso, vazio.
            completa = self.consultas >= self.voltas
            return 200, (self.arquivos if completa else [])
        if caminho.startswith("/searches/") and metodo == "GET":
            self.consultas += 1
            return 200, {"isComplete": self.consultas >= self.voltas}
        return 200, None


RESPOSTA = {
    "username": "DJRemix2025",
    "hasFreeUploadSlot": True,
    "queueLength": 2,
    "uploadSpeed": 900000,
    "files": [
        {
            "filename": r"@@x\03-josh_butler-hap_hazard_(original_mix).mp3",
            "size": 11942151,
            "bitRate": 320,
            "length": 294,
            "extension": "",
            "code": 1,
            "isLocked": False,
        }
    ],
}


def cliente(transporte, **kw) -> ClienteSlskd:
    return ClienteSlskd(
        chave_api="chave",
        limitador=LimitadorDeBuscas(limite=100, janela_s=1),
        transporte=transporte,
        dormir=lambda _s: None,
        **kw,
    )


def test_espera_a_busca_terminar_antes_de_ler():
    # 10 voltas de 1 s: com o limite antigo de 25 s passava; o ponto é que ESPERA.
    transporte = TransporteLento(voltas=10, arquivos=[RESPOSTA])
    achados = cliente(transporte).buscar("Josh Butler Hap Hazard")

    assert len(achados) == 1
    assert achados[0].nome_arquivo.endswith(".mp3")


def test_o_tempo_limite_cobre_a_busca_mais_lenta_medida():
    """A mais lenta medida levou 41,4 s. O limite antigo era 25."""
    assert ClienteSlskd.ESPERA_PELA_BUSCA_S >= 41.4 * 1.5


def test_busca_que_nao_terminou_e_marcada():
    transporte = TransporteLento(voltas=999, arquivos=[RESPOSTA])
    c = cliente(transporte)

    assert c.buscar("Josh Butler Hap Hazard", espera_max_s=3) == []
    assert not c.ultima_busca_terminou


def test_busca_que_terminou_fica_marcada_como_terminada():
    c = cliente(TransporteLento(voltas=1, arquivos=[RESPOSTA]))
    c.buscar("Josh Butler Hap Hazard")

    assert c.ultima_busca_terminou


# ------------------------------------------------- o relatório não pode mentir


class ClienteQueNaoTermina:
    ultima_busca_terminou = False
    limitador = None

    def buscar(self, texto, espera_max_s=None):
        return []


class ClienteQueTerminaVazio:
    ultima_busca_terminou = True
    limitador = None

    def buscar(self, texto, espera_max_s=None):
        return []


def test_sem_tempo_o_relatorio_diz_que_nao_deu_tempo():
    """"Nada na rede" com 42 arquivos no motor é mentira, e foi o que o app disse."""
    resultado = Buscador(ClienteQueNaoTermina()).buscar_faixa(
        Faixa(artista="Josh Butler", titulo="Hap Hazard")
    )

    assert resultado.buscas_incompletas
    assert "não terminou a tempo" in resultado.resumo()
    assert "nada na rede" not in resultado.resumo()


def test_busca_que_terminou_vazia_continua_sendo_nada_na_rede():
    # Aqui "não existe" é a leitura certa — e precisa continuar sendo.
    resultado = Buscador(ClienteQueTerminaVazio()).buscar_faixa(
        Faixa(artista="New Cassettes", titulo="Queen of the Quotation")
    )

    assert resultado.buscas_incompletas == 0
    assert "nada na rede" in resultado.resumo()
