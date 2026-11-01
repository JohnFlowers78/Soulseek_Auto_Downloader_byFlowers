"""Toda faixa tem que aparecer em exatamente UM lugar do relatório.

De 21 faixas, só 11 apareciam. As outras dez sumiam por dois motivos:

* `andamento.presas` era **sobrescrita** a cada volta em vez de acumulada, então só
  sobravam as presas do último lote conferido;
* faixa cujo download **falhou** não tinha lista nenhuma — nem baixada, nem presa,
  nem não-encontrada.

Estes testes existem para que isso não volte calado.
"""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6", reason="interface gráfica não instalada")

from PySide6.QtWidgets import QApplication  # noqa: E402

from config import Config  # noqa: E402
from modelos import Candidato, EstadoTransferencia, Transferencia  # noqa: E402
from politica import Foco  # noqa: E402
from trabalho import Andamento, TarefaDeDownload  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


class LoteFalso:
    def __init__(self, concluidas=(), presas=()):
        self.concluidas = list(concluidas)
        self.presas = list(presas)
        self.transferencias = self.concluidas + self.presas
        self.tudo_terminou = not self.presas


def transferencia(nome, estado, local="", fila=None) -> Transferencia:
    return Transferencia(
        candidato=Candidato(usuario="u", caminho=rf"x\{nome}", tamanho_bytes=1000),
        estado=estado,
        caminho_local=local,
        posicao_fila=fila,
    )


def tarefa(app) -> TarefaDeDownload:
    return TarefaDeDownload(Config(), "x", Foco.SEM_PERDA)


def registrar(t, chave, faixa, lote=None, sem_candidato=None, recusado=None):
    t._ficha[chave] = faixa
    if lote is not None:
        t._lotes[chave] = lote
    if sem_candidato is not None:
        t._sem_candidato[chave] = sem_candidato
    if recusado is not None:
        t._recusados[chave] = recusado


# ----------------------------------------------- nenhuma faixa se perde


def test_toda_faixa_aparece_em_exatamente_uma_lista(app):
    t = tarefa(app)
    registrar(t, 1, "A", LoteFalso(concluidas=[transferencia("a.flac", EstadoTransferencia.CONCLUIDA, "D:/a.flac")]))
    registrar(t, 2, "B", LoteFalso(presas=[transferencia("b.flac", EstadoTransferencia.NA_FILA, fila=5)]))
    registrar(t, 3, "C", LoteFalso())  # nem concluiu nem está presa: falhou
    registrar(t, 4, "D", sem_candidato="❌ D — nada na rede")
    registrar(t, 5, "E", recusado="o slskd recusou")

    andamento = Andamento(total=5)
    t._recalcular(andamento)

    total = len(andamento.baixadas) + len(andamento.presas) + len(andamento.nao_vieram)
    assert total == 5, "nenhuma faixa pode sumir do relatório"
    assert t.contabilizadas == 5


def test_as_presas_acumulam_em_vez_de_sobrescrever(app):
    """O bug exato: `andamento.presas = [...] or andamento.presas`.

    Cada volta trocava a lista pelas presas do último lote.
    """
    t = tarefa(app)
    for i in range(4):
        registrar(
            t, i, f"Faixa {i}",
            LoteFalso(presas=[transferencia(f"{i}.flac", EstadoTransferencia.NA_FILA)]),
        )

    andamento = Andamento(total=4)
    t._recalcular(andamento)

    assert len(andamento.presas) == 4


def test_download_que_falhou_nao_some(app):
    # Sem lista própria, a faixa evaporava: nem baixada, nem presa, nem não-achada.
    t = tarefa(app)
    registrar(t, 1, "Faixa que falhou", LoteFalso())

    andamento = Andamento(total=1)
    t._recalcular(andamento)

    assert len(andamento.nao_vieram) == 1
    assert "não completou" in andamento.nao_vieram[0]


def test_faixa_recusada_pelo_slskd_nao_some(app):
    # Achou, escolheu, e o slskd recusou TODAS as opções.
    t = tarefa(app)
    registrar(t, 1, "Recusada", recusado="HTTP 500: usuário offline")

    andamento = Andamento(total=1)
    t._recalcular(andamento)

    assert len(andamento.nao_vieram) == 1
    assert "usuário offline" in andamento.nao_vieram[0]


# ------------------------------------------------------- o que aparece


def test_a_baixada_mostra_a_faixa_e_o_arquivo(app):
    t = tarefa(app)
    registrar(
        t, 1, "Djavan — Flor de Lis",
        LoteFalso(concluidas=[transferencia("x.flac", EstadoTransferencia.CONCLUIDA, r"D:\13 Flor de Lis.flac")]),
    )

    andamento = Andamento(total=1)
    t._recalcular(andamento)

    (linha,) = andamento.baixadas
    assert "Djavan — Flor de Lis" in linha
    assert "13 Flor de Lis.flac" in linha


def test_a_presa_mostra_a_posicao_na_fila(app):
    t = tarefa(app)
    registrar(
        t, 1, "Tim Maia — Você",
        LoteFalso(presas=[transferencia("x.flac", EstadoTransferencia.NA_FILA, fila=14)]),
    )

    andamento = Andamento(total=1)
    t._recalcular(andamento)

    assert "posição 14" in andamento.presas[0]


def test_recalcular_nao_duplica_quando_chamado_varias_vezes(app):
    # É chamado a cada volta do laço — refazer do zero não pode acumular lixo.
    t = tarefa(app)
    registrar(t, 1, "A", LoteFalso(concluidas=[transferencia("a.flac", EstadoTransferencia.CONCLUIDA)]))

    andamento = Andamento(total=1)
    for _ in range(5):
        t._recalcular(andamento)

    assert len(andamento.baixadas) == 1


def test_sem_nada_registrado_as_listas_ficam_vazias(app):
    andamento = Andamento(total=0)
    tarefa(app)._recalcular(andamento)

    assert andamento.baixadas == []
    assert andamento.presas == []
    assert andamento.nao_vieram == []


def test_uma_faixa_que_passou_a_concluida_sai_das_presas(app):
    # O lote é substituído pela foto nova; a faixa muda de lista, não entra em duas.
    t = tarefa(app)
    registrar(t, 1, "A", LoteFalso(presas=[transferencia("a.flac", EstadoTransferencia.NA_FILA)]))
    andamento = Andamento(total=1)
    t._recalcular(andamento)
    assert len(andamento.presas) == 1

    t._lotes[1] = LoteFalso(concluidas=[transferencia("a.flac", EstadoTransferencia.CONCLUIDA)])
    t._recalcular(andamento)

    assert andamento.presas == []
    assert len(andamento.baixadas) == 1


def test_a_ordem_do_relatorio_e_a_ordem_da_playlist(app):
    # Com a ordem estável, a tela troca texto no lugar em vez de reembaralhar a lista.
    t = tarefa(app)
    for i in (1, 2, 3):
        registrar(t, i, f"Faixa {i}", sem_candidato=f"Faixa {i} — nada na rede")

    andamento = Andamento(total=3)
    t._recalcular(andamento)

    assert andamento.nao_vieram == [
        "Faixa 1 — nada na rede",
        "Faixa 2 — nada na rede",
        "Faixa 3 — nada na rede",
    ]


def test_chave_sem_ficha_ainda_aparece(app):
    # Deixar de fora quem não tem ficha seria repetir o defeito por outro caminho.
    t = tarefa(app)
    t._lotes[99] = LoteFalso(concluidas=[transferencia("x.flac", EstadoTransferencia.CONCLUIDA)])

    andamento = Andamento(total=1)
    t._recalcular(andamento)

    assert len(andamento.baixadas) == 1


# ------------------------------------------- a chave nao pode ser reaproveitada


class ResultadoFalso:
    def __init__(self, faixa):
        self.faixa = faixa
        self.escolhas: list = []

    def resumo(self):
        return f"{self.faixa} — nada na rede"


class BuscadorFalso:
    def __init__(self, escolhas=()):
        self._escolhas = list(escolhas)

    def buscar_faixa(self, faixa):
        # Objeto novo a cada chamada, descartado logo depois — era aqui que o
        # `id()` reaproveitava endereço e uma faixa apagava a outra.
        r = ResultadoFalso(faixa)
        r.escolhas = list(self._escolhas)
        r.escolhidos = list(self._escolhas)
        return r


class OperarioFalso:
    def __init__(self, aceita=True):
        self.aceita = aceita

    def enfileirar(self, escolhidos):
        class Fila:
            pass

        fila = Fila()
        fila.aceitos = list(escolhidos) if self.aceita else []
        fila.recusados = [] if self.aceita else [(c, "usuário offline") for c in escolhidos]
        return fila


def test_cada_faixa_tem_sua_propria_chave(app):
    """A chave era `id(resultado)`, e o resultado virava lixo na linha seguinte.

    O CPython reaproveita o endereço de um objeto recolhido, então duas faixas
    diferentes recebiam a MESMA chave e uma sobrescrevia o registro da outra. Com 30
    faixas de uma playlist real, isso era perda garantida. A chave agora é a posição
    da faixa na playlist.
    """
    t = tarefa(app)
    for i in range(1, 31):
        t._uma_faixa(i, f"Faixa {i}", BuscadorFalso(), None, {})

    assert len(t._ficha) == 30
    assert t.contabilizadas == 30

    andamento = Andamento(total=30)
    t._recalcular(andamento)
    assert len(andamento.nao_vieram) == 30


def test_a_segunda_tentativa_apaga_o_registro_da_primeira(app):
    """O motor cai, religa, e a MESMA faixa é tentada de novo.

    Sem limpar o registro anterior, a tentativa que falhou ficaria somada à que deu
    certo e a faixa apareceria em duas colunas.
    """
    t = tarefa(app)
    pendentes: dict = {}

    t._uma_faixa(7, "Djavan — Se", BuscadorFalso(["a.flac"]), OperarioFalso(aceita=False), pendentes)
    assert 7 in t._recusados

    t._uma_faixa(7, "Djavan — Se", BuscadorFalso(["a.flac"]), OperarioFalso(aceita=True), pendentes)

    assert 7 not in t._recusados, "o recusado da primeira tentativa ficou para trás"
    assert pendentes[7] == ["a.flac"]
    assert t.contabilizadas == 0, "ainda não tem desfecho — está baixando"

    andamento = Andamento(total=1)
    t._recalcular(andamento)
    assert andamento.nao_vieram == []


def test_a_segunda_tentativa_limpa_o_sem_candidato(app):
    t = tarefa(app)
    pendentes: dict = {}

    t._uma_faixa(3, "Céu — Malemolência", BuscadorFalso(), OperarioFalso(), pendentes)
    assert 3 in t._sem_candidato

    t._uma_faixa(3, "Céu — Malemolência", BuscadorFalso(["b.aiff"]), OperarioFalso(), pendentes)

    assert 3 not in t._sem_candidato
    assert pendentes[3] == ["b.aiff"]
