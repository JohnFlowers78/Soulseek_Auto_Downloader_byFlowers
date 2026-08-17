"""Testes do gerador de variantes de busca.

Lógica pura: não toca em rede, disco nem em nenhum dado real.
"""

import pytest

from normalizador import (
    Variante,
    colapsa_espacos,
    gerar_variantes,
    nome_pasta_segura,
    palavras_marcantes,
    palavras_uteis,
    primeiro_artista,
    sem_acentos,
    sem_parenteses,
    sem_participacao,
    sem_pontuacao,
)


# --------------------------------------------------------------------------- acentos


@pytest.mark.parametrize(
    "entrada, esperado",
    [
        ("Não Vou Ficar", "Nao Vou Ficar"),
        ("Malemolência", "Malemolencia"),
        ("Você", "Voce"),
        ("Açaí", "Acai"),
        ("Sigur Rós", "Sigur Ros"),
        ("Hoppípolla", "Hoppipolla"),
        ("Björk", "Bjork"),
        ("Motörhead", "Motorhead"),
    ],
)
def test_tira_acento_de_todo_tipo(entrada, esperado):
    assert sem_acentos(entrada) == esperado


def test_tira_acento_de_letras_que_o_unicode_nao_decompoe():
    # ø, ł e ß não são "letra + acento" — precisam da tabela de tradução.
    assert sem_acentos("Søren") == "Soren"
    assert sem_acentos("Łódź") == "Lodz"
    assert sem_acentos("Straße") == "Strasse"


def test_texto_sem_acento_passa_intacto():
    assert sem_acentos("One More Time") == "One More Time"


# ------------------------------------------------------------------------ pontuação


def test_hifen_sempre_sai():
    # A regra mais importante do módulo: no Soulseek "-" é operador de EXCLUSÃO.
    assert "-" not in sem_pontuacao("Djavan - Se")
    assert sem_pontuacao("Djavan - Se") == "Djavan Se"


@pytest.mark.parametrize(
    "entrada, esperado",
    [
        ("Don't Stop", "Don t Stop"),
        ('Ela disse "sim"', "Ela disse sim"),
        ("Rock & Roll", "Rock Roll"),
        ("Sim/Não", "Sim/Não".replace("/", " ")),
        ("A.M.A.R", "A M A R"),
        ("50% Amor", "50 Amor"),
        ("R.E.M. — Losing", "R E M Losing"),
    ],
)
def test_pontuacao_vira_espaco(entrada, esperado):
    assert sem_pontuacao(entrada) == colapsa_espacos(esperado)


def test_pontuacao_preserva_acento():
    # sem_pontuacao não é para mexer em acento — cada função faz uma coisa só.
    assert sem_pontuacao("Não - Vou") == "Não Vou"


def test_numeros_sobrevivem():
    assert sem_pontuacao("Blink-182") == "Blink 182"


# ---------------------------------------------------------------------- participação


@pytest.mark.parametrize(
    "entrada, esperado",
    [
        ("Não Vou Ficar (feat. Alcione)", "Não Vou Ficar"),
        ("Song [ft. Someone]", "Song"),
        ("Track feat. Guest", "Track"),
        ("Track ft Guest", "Track"),
        ("Track featuring Guest", "Track"),
        ("Musica part. Fulano", "Musica"),
    ],
)
def test_remove_participacao(entrada, esperado):
    assert sem_participacao(entrada) == esperado


def test_participacao_solta_nao_come_o_mix_que_vem_depois():
    # "feat. X" solto para no próximo parêntese — "(Extended Mix)" tem que sobreviver.
    assert sem_participacao("Track feat. Guest (Extended Mix)") == "Track (Extended Mix)"


def test_with_e_com_nao_sao_participacao():
    # Removê-los quebraria títulos legítimos.
    assert sem_participacao("Dancing With Myself") == "Dancing With Myself"
    assert sem_participacao("Amor com Amor") == "Amor com Amor"


# ------------------------------------------------------------------------ parênteses


@pytest.mark.parametrize(
    "entrada, esperado",
    [
        ("One More Time (Original Mix)", "One More Time"),
        ("Song [Remastered 2011]", "Song"),
        ("Song {Bonus Track}", "Song"),
        ("A (x) B [y]", "A B"),
    ],
)
def test_remove_parenteses(entrada, esperado):
    assert sem_parenteses(entrada) == esperado


# --------------------------------------------------------------------------- artista


@pytest.mark.parametrize(
    "entrada, esperado",
    [
        ("Djavan, Alcione", "Djavan"),
        ("Djavan & Alcione", "Djavan"),
        ("Djavan feat. Alcione", "Djavan"),
        ("Djavan; Alcione", "Djavan"),
        ("Djavan", "Djavan"),
    ],
)
def test_pega_o_artista_principal(entrada, esperado):
    assert primeiro_artista(entrada) == esperado


def test_e_comercial_dentro_do_nome_da_banda_ainda_e_cortado():
    # Limitação conhecida e aceita: "Earth, Wind & Fire" vira "Earth".
    # Só afeta a variante mais permissiva, e o nome completo continua nas variantes 1-5.
    assert primeiro_artista("Earth, Wind & Fire") == "Earth"


# ------------------------------------------------------------------- palavras úteis


def test_palavras_uteis_descarta_vazias_e_de_uma_letra():
    assert palavras_uteis("A Noite de São João") == ["noite", "sao", "joao"]


def test_palavras_uteis_normaliza_tudo():
    assert palavras_uteis("Não - Vou (Ficar)") == ["nao", "vou", "ficar"]


def test_palavra_marcante_e_a_mais_longa_quando_ela_discrimina():
    assert palavras_marcantes(["nao", "vou", "ficar"]) == ["ficar"]
    assert palavras_marcantes(["ceu", "malemolencia"]) == ["malemolencia"]


def test_palavras_marcantes_viram_duas_quando_todas_sao_curtas():
    # "more" sozinho aparece em meio mundo de arquivo — precisa de companhia.
    assert palavras_marcantes(["one", "more", "time"]) == ["more", "time"]


def test_palavras_marcantes_respeitam_a_ordem_do_titulo():
    assert palavras_marcantes(["time", "more", "one"]) == ["time", "more"]


def test_palavras_marcantes_com_lista_vazia():
    assert palavras_marcantes([]) == []


# ---------------------------------------------------------------- gerador completo


def test_nenhuma_variante_contem_hifen():
    # A garantia que não pode falhar nunca.
    casos = [
        ("Djavan", "Se - Ao Vivo"),
        ("Blink-182", "All the Small Things"),
        ("AC-DC", "Back in Black - Remaster"),
        ("Jay-Z", "99 Problems"),
    ]
    for artista, titulo in casos:
        for v in gerar_variantes(artista, titulo):
            assert "-" not in v.consulta, f"hífen sobrou em {v!r}"


def test_variantes_sao_unicas():
    variantes = gerar_variantes("Tim Maia", "Você")
    consultas = [v.consulta.casefold() for v in variantes]
    assert len(consultas) == len(set(consultas))


def test_ordem_vai_da_mais_fiel_para_a_mais_permissiva():
    variantes = gerar_variantes("Djavan", "Não Vou Ficar (feat. Alcione)")
    estrategias = [v.estrategia for v in variantes]

    assert estrategias[0] == "fiel"
    assert "Não" in variantes[0].consulta  # a primeira preserva o acento

    # cada estratégia presente respeita a ordem canônica
    ordem = [
        "fiel", "sem_acentos", "sem_participacao", "sem_parenteses",
        "so_titulo", "artista_palavra_chave", "nucleo",
    ]
    posicoes = [ordem.index(e) for e in estrategias]
    assert posicoes == sorted(posicoes)


def test_caso_completo_do_djavan():
    variantes = {v.estrategia: v.consulta for v in gerar_variantes("Djavan", "Não Vou Ficar (feat. Alcione)")}

    assert variantes["fiel"] == "Djavan Não Vou Ficar feat Alcione"
    assert variantes["sem_acentos"] == "Djavan Nao Vou Ficar feat Alcione"
    assert variantes["sem_participacao"] == "Djavan Nao Vou Ficar"
    assert variantes["so_titulo"] == "Nao Vou Ficar"


def test_mantem_o_mix_nas_primeiras_variantes_e_so_tira_depois():
    variantes = gerar_variantes("Daft Punk", "One More Time (Extended Mix)")
    por_estrategia = {v.estrategia: v.consulta for v in variantes}

    # "Extended Mix" sobrevive nas primeiras — para DJ isso distingue a faixa certa.
    assert "Extended" in variantes[0].consulta
    # ...e só cai quando a estratégia é justamente remover os parênteses.
    assert "Extended" not in por_estrategia["sem_parenteses"]


def test_faixa_sem_acento_nao_repete_a_consulta_so_para_ter_a_etiqueta():
    # "Daft Punk One More Time Extended Mix" sai igual em 'fiel' e 'sem_acentos'.
    # Repetir a consulta seria queimar cota do limite de 34 buscas/220 s à toa,
    # então fica só a primeira — com a etiqueta da estratégia mais fiel.
    variantes = gerar_variantes("Daft Punk", "One More Time (Extended Mix)")
    estrategias = [v.estrategia for v in variantes]

    assert "sem_acentos" not in estrategias
    assert estrategias[0] == "fiel"


def test_variante_de_palavra_chave_pega_a_palavra_mais_longa():
    variantes = {v.estrategia: v.consulta for v in gerar_variantes("Céu", "Malemolência Suave")}
    assert variantes["artista_palavra_chave"] == "Ceu malemolencia"


def test_nucleo_nao_aparece_quando_sobraria_pouca_coisa():
    # "Sim" sozinho traria lixo demais — a variante não é oferecida.
    estrategias = {v.estrategia for v in gerar_variantes("A", "Sim")}
    assert "nucleo" not in estrategias


def test_faixa_sem_acento_nem_pontuacao_gera_poucas_variantes():
    # Nada a normalizar: as variantes repetidas são descartadas.
    variantes = gerar_variantes("Radiohead", "Creep")
    assert [v.consulta for v in variantes] == ["Radiohead Creep", "Creep"]


@pytest.mark.parametrize("artista, titulo", [("", ""), (None, None), ("  ", " ")])
def test_entrada_vazia_nao_explode(artista, titulo):
    assert gerar_variantes(artista, titulo) == []


def test_so_titulo_sem_artista_funciona():
    variantes = gerar_variantes("", "Bohemian Rhapsody")
    assert variantes
    assert all(v.consulta for v in variantes)


def test_variante_e_imutavel_e_comparavel():
    a = Variante("x", "fiel")
    assert a == Variante("x", "fiel")
    with pytest.raises(Exception):
        a.consulta = "y"  # type: ignore[misc]


# ----------------------------------------------------------------- nome de pasta


@pytest.mark.parametrize(
    "entrada, esperado",
    [
        ("Set de Verão 2026", "Set de Verão 2026"),
        ("Rock/Metal: os melhores", "Rock Metal os melhores"),
        ('Playlist "top" <3', "Playlist top 3"),
        ("Favoritas | 2026", "Favoritas 2026"),
        ("Nome com ponto final.", "Nome com ponto final"),
        ("Espaço no fim   ", "Espaço no fim"),
    ],
)
def test_nome_de_pasta_fica_valido_no_windows(entrada, esperado):
    assert nome_pasta_segura(entrada) == esperado


def test_nome_de_pasta_nunca_volta_vazio():
    # Uma pasta sem nome faria o app gravar na raiz do destino — precisa de rede de proteção.
    assert nome_pasta_segura("///") == "Playlist sem nome"
    assert nome_pasta_segura("") == "Playlist sem nome"
    assert nome_pasta_segura("...") == "Playlist sem nome"


def test_nome_de_pasta_e_cortado_sem_deixar_ponto_no_fim():
    resultado = nome_pasta_segura("A" * 200)
    assert len(resultado) == 120
    assert not resultado.endswith((".", " "))


def test_nome_de_pasta_mantem_acento():
    # Acento em nome de pasta o Windows aceita numa boa — não há motivo para tirar.
    assert nome_pasta_segura("Coração Selvagem") == "Coração Selvagem"
