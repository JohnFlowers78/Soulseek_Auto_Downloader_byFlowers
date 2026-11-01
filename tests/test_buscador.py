"""Testes do buscador — a peça que decide quantas buscas gastar por faixa.

Cliente falso: nada toca a rede. O que se testa aqui é **economia de cota**, que é o
recurso mais escasso do app (34 buscas por 220 s).
"""

import pytest

from buscador import Buscador, ResultadoDaBusca
from modelos import Candidato, Faixa

FAIXA = Faixa(artista="Djavan", titulo="Não Vou Ficar", duracao_s=250.0)


def arquivo(nome="a.flac", usuario="joao", **ajustes) -> Candidato:
    padrao = dict(
        usuario=usuario,
        caminho=rf"@@abc\Music\{nome}",
        tamanho_bytes=30_000_000,
        duracao_s=250.0,
        slot_livre=True,
    )
    return Candidato(**{**padrao, **ajustes})


class ClienteFalso:
    """Devolve o que foi programado por consulta, e anota tudo que foi perguntado."""

    def __init__(self, por_consulta: dict[str, list[Candidato]] | None = None, padrao=None):
        self.por_consulta = por_consulta or {}
        self.padrao = padrao if padrao is not None else []
        self.consultas: list[str] = []

    def buscar(self, consulta: str, **_):
        self.consultas.append(consulta)
        return self.por_consulta.get(consulta, self.padrao)


# ------------------------------------------------------- economia de cota


def test_para_na_primeira_variante_que_acerta():
    # A regra que define o tempo de uma playlist inteira.
    cliente = ClienteFalso(padrao=[arquivo()])
    resultado = Buscador(cliente).buscar_faixa(FAIXA)

    assert resultado.achou
    assert resultado.buscas_gastas == 1
    assert len(cliente.consultas) == 1


def test_tenta_a_proxima_variante_quando_nao_vem_nada():
    cliente = ClienteFalso(por_consulta={"Djavan Nao Vou Ficar": [arquivo()]})
    resultado = Buscador(cliente).buscar_faixa(FAIXA)

    assert resultado.achou
    assert resultado.buscas_gastas > 1
    assert resultado.variante_que_acertou.consulta == "Djavan Nao Vou Ficar"


def test_tenta_a_proxima_quando_acha_mas_nada_presta():
    # Achou arquivos ruins: outra grafia pode trazer gente com acervo melhor.
    ruim = arquivo("a.mp3", bitrate_kbps=96)
    bom = arquivo("b.flac", usuario="maria")
    cliente = ClienteFalso(
        por_consulta={
            "Djavan Não Vou Ficar": [ruim],
            "Djavan Nao Vou Ficar": [bom],
        }
    )
    resultado = Buscador(cliente).buscar_faixa(FAIXA)

    assert resultado.achou
    assert resultado.escolhidos[0].candidato.extensao == "flac"


def test_desiste_depois_do_maximo_de_variantes():
    cliente = ClienteFalso(padrao=[])
    resultado = Buscador(cliente, max_variantes=2).buscar_faixa(FAIXA)

    assert not resultado.achou
    assert resultado.buscas_gastas == 2


def test_nunca_gasta_mais_buscas_que_o_maximo():
    cliente = ClienteFalso(padrao=[])
    Buscador(cliente, max_variantes=3).buscar_faixa(FAIXA)
    assert len(cliente.consultas) <= 3


def test_as_consultas_nunca_tem_hifen():
    # A garantia que atravessa o app: no Soulseek "-" é operador de exclusão.
    cliente = ClienteFalso(padrao=[])
    Buscador(cliente, max_variantes=7).buscar_faixa(
        Faixa(artista="Blink-182", titulo="All the Small Things - Remaster")
    )
    for consulta in cliente.consultas:
        assert "-" not in consulta


# ------------------------------------------------------------- resultado


def test_guarda_as_variantes_tentadas_em_ordem():
    cliente = ClienteFalso(por_consulta={"Djavan Nao Vou Ficar": [arquivo()]})
    resultado = Buscador(cliente).buscar_faixa(FAIXA)

    etiquetas = [v.estrategia for v in resultado.variantes_tentadas]
    assert etiquetas == ["fiel", "sem_acentos"]


def test_escolhe_a_quantidade_pedida():
    cliente = ClienteFalso(
        padrao=[arquivo("a.flac", "joao"), arquivo("b.flac", "maria"), arquivo("c.flac", "ana")]
    )
    resultado = Buscador(cliente, quantidade_por_faixa=2).buscar_faixa(FAIXA)
    assert len(resultado.escolhidos) == 2


def test_guarda_os_descartados_com_motivo():
    # É o que responde "mas não tinha nada mesmo?".
    cliente = ClienteFalso(padrao=[arquivo("a.flac"), arquivo("b.ogg", "maria")])
    resultado = Buscador(cliente).buscar_faixa(FAIXA)

    assert resultado.descartados
    assert all(d.motivo for d in resultado.descartados)


def test_faixa_com_duracao_filtra_versao_errada():
    # O remix de 7 minutos com o mesmo nome não entra.
    cliente = ClienteFalso(padrao=[arquivo("remix.flac", duracao_s=420.0)])
    resultado = Buscador(cliente, max_variantes=1).buscar_faixa(FAIXA)

    assert not resultado.achou
    assert any("duração" in d.motivo for d in resultado.descartados)


# ----------------------------------------------------------------- resumo


def test_resumo_de_sucesso_diz_a_estrategia_e_o_custo():
    cliente = ClienteFalso(padrao=[arquivo()])
    resumo = Buscador(cliente).buscar_faixa(FAIXA).resumo()

    assert resumo.startswith("✅")
    assert "fiel" in resumo
    assert "1 busca" in resumo


def test_resumo_distingue_nada_achado_de_nada_aproveitavel():
    nada = Buscador(ClienteFalso(padrao=[])).buscar_faixa(FAIXA).resumo()
    assert nada.startswith("❌")
    assert "nada na rede" in nada

    ruim = Buscador(ClienteFalso(padrao=[arquivo("a.ogg")])).buscar_faixa(FAIXA).resumo()
    assert ruim.startswith("⚠️")
    assert "nenhum passou no filtro" in ruim


# -------------------------------------------------------------- várias


def test_busca_uma_lista_inteira():
    # As duas faixas com a mesma duração do candidato falso: aqui o que se testa é o
    # laço, não o filtro de duração (que tem teste próprio logo acima).
    cliente = ClienteFalso(padrao=[arquivo()])
    faixas = [FAIXA, Faixa(artista="Tim Maia", titulo="Você", duracao_s=250.0)]
    resultados = Buscador(cliente).buscar_varias(faixas)

    assert len(resultados) == 2
    assert all(r.achou for r in resultados)
    assert [r.faixa.titulo for r in resultados] == ["Não Vou Ficar", "Você"]


def test_estimativa_de_tempo_usa_o_limitador():
    from limitador import LimitadorDeBuscas

    class ComLimitador(ClienteFalso):
        limitador = LimitadorDeBuscas()

    # 100 faixas × 1.6 variantes = 160 buscas
    segundos = Buscador(ComLimitador()).tempo_estimado_s(100)
    assert segundos > 0
    assert segundos == pytest.approx(880.0)


def test_resultado_vazio_nao_explode():
    vazio = ResultadoDaBusca(faixa=FAIXA)
    assert not vazio.achou
    assert vazio.buscas_gastas == 0
    assert vazio.resumo().startswith("❌")
