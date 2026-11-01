"""Testes do buscador — a peça que decide quantas buscas gastar por faixa.

Cliente falso: nada toca a rede. O que se testa aqui é **economia de cota**, que é o
recurso mais escasso do app (34 buscas por 220 s).
"""

import pytest

from buscador import Buscador, ResultadoDaBusca
from modelos import Candidato, Faixa

FAIXA = Faixa(artista="Djavan", titulo="Não Vou Ficar", duracao_s=250.0)


def arquivo(nome="a.flac", usuario="joao", **ajustes) -> Candidato:
    # O caminho traz "Djavan" porque a conferência de artista (testada mais abaixo)
    # reprova o que não bate — e aqui o assunto é outro.
    padrao = dict(
        usuario=usuario,
        caminho=rf"@@abc\Music\Djavan\{nome}",
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


# -------------------------------------------- conferência do artista
#
# O episódio que criou esta seção: pedindo "Djavan — Não Vou Ficar", as variantes com
# o artista voltaram vazias, a `so_titulo` buscou só "Nao Vou Ficar", e o app baixou
# Kid Abelha e Tim Maia. Arquivos bons, nome certo, faixa errada.


def de_outro(nome, pasta, usuario="outro") -> Candidato:
    return arquivo(nome, usuario, caminho=rf"@@abc\musica\{pasta}\{nome}")


def test_nao_baixa_a_musica_certa_do_artista_errado():
    cliente = ClienteFalso(
        por_consulta={
            "Nao Vou Ficar": [
                de_outro("04 - Nao vou ficar.flac", r"Kid Abelha\Tudo é permitido (1991)"),
                de_outro("05 - Nao Vou Ficar.flac", r"Tim Maia\1971 - Tim Maia"),
            ]
        }
    )
    resultado = Buscador(cliente).buscar_faixa(FAIXA)

    assert not resultado.achou
    assert len(resultado.de_outro_artista) == 2


def test_aceita_quando_o_artista_bate():
    cliente = ClienteFalso(
        por_consulta={"Nao Vou Ficar": [de_outro("04 - Nao Vou Ficar.flac", r"Djavan\Luz")]}
    )
    resultado = Buscador(cliente).buscar_faixa(FAIXA)

    assert resultado.achou
    assert resultado.de_outro_artista == []


def test_a_conferencia_nao_impede_de_tentar_a_proxima_variante():
    # Se tudo que veio é de outro artista, a busca continua: outra grafia pode achar.
    cliente = ClienteFalso(
        por_consulta={
            "Djavan Não Vou Ficar": [de_outro("x.flac", "Kid Abelha")],
            "Djavan Nao Vou Ficar": [de_outro("y.flac", "Djavan")],
        }
    )
    resultado = Buscador(cliente).buscar_faixa(FAIXA)

    assert resultado.achou
    assert resultado.variante_que_acertou.estrategia == "sem_acentos"
    assert len(resultado.de_outro_artista) == 1


def test_o_resumo_distingue_artista_errado_de_nada_achado():
    cliente = ClienteFalso(padrao=[de_outro("x.flac", "Kid Abelha")])
    resumo = Buscador(cliente).buscar_faixa(FAIXA).resumo()

    assert "de outro artista" in resumo


def test_nao_baixa_outra_musica_do_artista_certo():
    """O segundo caso real: 'Djavan ficar' trouxe 'Tenho Medo de Ficar Só'.

    A variante `artista_palavra_chave` encurta o título a uma ou duas palavras. O
    artista bate, e sem conferir o título o app baixa a faixa errada do cantor certo.
    """
    outra = arquivo("04 - Tenho medo de ficar só.flac", "nas")
    cliente = ClienteFalso(por_consulta={"Djavan ficar": [outra]})
    resultado = Buscador(cliente).buscar_faixa(FAIXA)

    assert not resultado.achou
    assert len(resultado.de_outra_musica) == 1
    assert resultado.de_outro_artista == []


def test_a_variante_fiel_nao_sofre_conferencia_de_titulo():
    # Nela a consulta já levou o título inteiro — quem filtrou foi o servidor do
    # Soulseek. Conferir de novo só reprovaria arquivo com nome abreviado.
    curto = arquivo("NaoVouFicar.flac")
    cliente = ClienteFalso(por_consulta={"Djavan Não Vou Ficar": [curto]})
    resultado = Buscador(cliente).buscar_faixa(FAIXA)

    assert resultado.achou


def test_o_resumo_distingue_outra_musica_de_outro_artista():
    cliente = ClienteFalso(
        por_consulta={"Djavan ficar": [arquivo("Tenho medo de ficar só.flac")]}
    )
    assert "de outra música" in Buscador(cliente).buscar_faixa(FAIXA).resumo()


def test_da_para_desligar_a_conferencia():
    # Fica configurável porque acervo mal catalogado (sem pasta de artista) seria
    # reprovado por inteiro — e aí o usuário decide o que prefere.
    cliente = ClienteFalso(padrao=[de_outro("x.flac", "Kid Abelha")])
    resultado = Buscador(cliente, conferir_nomes=False).buscar_faixa(FAIXA)

    assert resultado.achou


def test_faixa_sem_artista_nao_sofre_conferencia():
    cliente = ClienteFalso(padrao=[de_outro("x.flac", "Qualquer Um")])
    resultado = Buscador(cliente).buscar_faixa(Faixa(artista="", titulo="Não Vou Ficar"))

    assert resultado.achou


def test_entre_dois_aprovados_o_nome_mais_limpo_vem_primeiro():
    """O caso real do 'Flor de Lis': os dois eram FLAC e os dois foram aprovados.

    Um era a faixa; o outro, um pot-pourri ao vivo que contém o título. Qualidade
    igual, probabilidade bem diferente.
    """
    faixa = Faixa(artista="Djavan", titulo="Flor de Lis", duracao_s=250.0)
    medley = arquivo("08_Limão  Avião  Flor De Lis - Ao Vivo.flac", "revco")
    limpo = arquivo("13 Flor de Lis.flac", "eduardo")

    cliente = ClienteFalso(padrao=[medley, limpo])
    resultado = Buscador(cliente).buscar_faixa(faixa)

    assert resultado.aprovados[0].candidato.nome_arquivo == "13 Flor de Lis.flac"


def test_a_proximidade_nao_passa_na_frente_da_qualidade():
    # 30 pontos desempatam entre iguais; não fazem um MP3 ganhar de um FLAC.
    faixa = Faixa(artista="Djavan", titulo="Flor de Lis", duracao_s=250.0)
    mp3_limpo = arquivo("Flor de Lis.mp3", "a", bitrate_kbps=320)
    flac_sujo = arquivo("08_Limão Avião Flor De Lis Ao Vivo.flac", "b")

    resultado = Buscador(ClienteFalso(padrao=[mp3_limpo, flac_sujo])).buscar_faixa(faixa)

    assert resultado.aprovados[0].candidato.extensao == "flac"


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
    # Ambas do mesmo artista do candidato falso, senão a conferência de artista
    # reprova a segunda — e ela tem testes próprios logo acima.
    cliente = ClienteFalso(padrao=[arquivo()])
    faixas = [FAIXA, Faixa(artista="Djavan", titulo="Flor de Lis", duracao_s=250.0)]
    resultados = Buscador(cliente).buscar_varias(faixas)

    assert len(resultados) == 2
    assert all(r.achou for r in resultados)
    assert [r.faixa.titulo for r in resultados] == ["Não Vou Ficar", "Flor de Lis"]


def test_estimativa_soma_a_espera_do_limite_com_o_tempo_das_buscas():
    from limitador import LimitadorDeBuscas

    class ComLimitador(ClienteFalso):
        limitador = LimitadorDeBuscas()

    # 100 faixas × 1.6 = 160 buscas → 880 s de espera + 160 × 12 s de busca
    assert Buscador(ComLimitador()).tempo_estimado_s(100) == pytest.approx(880.0 + 1920.0)


def test_lista_curta_nao_estima_zero():
    """'~0 min' para 14 faixas era um número inútil.

    Só a espera do limitador dava zero, porque as 34 primeiras buscas saem sem
    esperar — mas cada busca ainda leva o tempo dela na rede.
    """
    from limitador import LimitadorDeBuscas

    class ComLimitador(ClienteFalso):
        limitador = LimitadorDeBuscas()

    segundos = Buscador(ComLimitador()).tempo_estimado_s(14)
    assert segundos > 120, "14 faixas não levam menos de dois minutos"


def test_resultado_vazio_nao_explode():
    vazio = ResultadoDaBusca(faixa=FAIXA)
    assert not vazio.achou
    assert vazio.buscas_gastas == 0
    assert vazio.resumo().startswith("❌")
