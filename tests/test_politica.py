"""Testes da política de quantas versões baixar, e quais.

A razão de existir é de pista de dança: tocar sempre o mesmo formato, para a diferença
de qualidade não aparecer no meio do set. Então a política tem que **garantir** um de
cada tipo, e dar a vaga extra ao formato que vai tocar.
"""

import pytest

from modelos import Candidato
from politica import Escolha, Foco, escolher_por_politica, resumir_politica
from qualidade import avaliar, ranquear


def arquivo(nome, usuario, **ajustes) -> Candidato:
    padrao = dict(
        usuario=usuario,
        caminho=rf"@@x\Music\Artista\{nome}",
        tamanho_bytes=30_000_000,
        duracao_s=250.0,
        slot_livre=True,
    )
    return Candidato(**{**padrao, **ajustes})


def aprovados_variados() -> list:
    return ranquear(
        [
            arquivo("a.flac", "ana"),
            arquivo("b.flac", "bruno"),
            arquivo("c.aiff", "carla"),
            arquivo("d.mp3", "davi", bitrate_kbps=320),
            arquivo("e.mp3", "elis", bitrate_kbps=320),
            arquivo("f.wav", "fabio"),
        ]
    )


# ------------------------------------------------- os dois formatos sempre


def test_traz_sempre_um_sem_perda_e_um_mp3():
    escolhidas = escolher_por_politica(aprovados_variados(), Foco.SEM_PERDA)
    papeis = [e.papel for e in escolhidas]

    assert "sem perda" in papeis
    assert "MP3 320" in papeis


def test_o_foco_ganha_a_vaga_extra_sem_perda():
    escolhidas = escolher_por_politica(aprovados_variados(), Foco.SEM_PERDA)
    extensoes = [e.avaliacao.candidato.extensao for e in escolhidas]

    assert len(escolhidas) == 3
    # dois sem perda + um mp3
    assert sum(1 for x in extensoes if x in ("flac", "aiff", "wav")) == 2
    assert extensoes.count("mp3") == 1


def test_o_foco_ganha_a_vaga_extra_mp3():
    escolhidas = escolher_por_politica(aprovados_variados(), Foco.MP3)
    extensoes = [e.avaliacao.candidato.extensao for e in escolhidas]

    assert extensoes.count("mp3") == 2
    assert sum(1 for x in extensoes if x in ("flac", "aiff", "wav")) == 1


def test_o_papel_da_vaga_extra_diz_que_e_o_foco():
    escolhidas = escolher_por_politica(aprovados_variados(), Foco.MP3)
    assert any("foco" in e.papel for e in escolhidas)


# -------------------------------------------------- quando a rede não tem


def test_sem_mp3_na_rede_a_vaga_vai_para_o_melhor_restante():
    # A vaga não se perde: uma lacuna não ajuda ninguém, uma segunda boa sim.
    so_sem_perda = ranquear(
        [arquivo("a.flac", "ana"), arquivo("b.wav", "bruno"), arquivo("c.aiff", "carla")]
    )
    escolhidas = escolher_por_politica(so_sem_perda, Foco.SEM_PERDA)

    assert len(escolhidas) == 3
    assert all(e.avaliacao.candidato.extensao != "mp3" for e in escolhidas)


def test_sem_sem_perda_na_rede_so_vem_mp3():
    so_mp3 = ranquear(
        [
            arquivo("a.mp3", "ana", bitrate_kbps=320),
            arquivo("b.mp3", "bruno", bitrate_kbps=320),
        ]
    )
    escolhidas = escolher_por_politica(so_mp3, Foco.SEM_PERDA)

    assert len(escolhidas) == 2
    assert all(e.avaliacao.candidato.extensao == "mp3" for e in escolhidas)


def test_uma_opcao_so_devolve_uma():
    um = ranquear([arquivo("a.flac", "ana")])
    assert len(escolher_por_politica(um, Foco.SEM_PERDA)) == 1


def test_nada_aprovado_devolve_nada():
    assert escolher_por_politica([], Foco.SEM_PERDA) == []


# --------------------------------------------------- diversificar usuário


def test_prefere_usuarios_diferentes():
    # Duas do mesmo usuário caem juntas se ele sair do ar — e aí a garantia de ter
    # os dois formatos some junto.
    escolhidas = escolher_por_politica(aprovados_variados(), Foco.SEM_PERDA)
    usuarios = [e.avaliacao.candidato.usuario for e in escolhidas]
    assert len(set(usuarios)) == len(usuarios)


def test_repete_usuario_so_quando_nao_ha_mais_ninguem():
    do_mesmo = ranquear(
        [
            arquivo("a.flac", "unico"),
            arquivo("b.wav", "unico"),
            arquivo("c.mp3", "unico", bitrate_kbps=320),
        ]
    )
    escolhidas = escolher_por_politica(do_mesmo, Foco.SEM_PERDA, quantidade=3)

    assert len(escolhidas) == 3


def test_nunca_escolhe_o_mesmo_arquivo_duas_vezes():
    escolhidas = escolher_por_politica(aprovados_variados(), Foco.SEM_PERDA)
    caminhos = [e.avaliacao.candidato.caminho for e in escolhidas]
    assert len(set(caminhos)) == len(caminhos)


def test_respeita_a_quantidade_pedida():
    assert len(escolher_por_politica(aprovados_variados(), Foco.MP3, quantidade=2)) == 2
    assert len(escolher_por_politica(aprovados_variados(), Foco.MP3, quantidade=5)) <= 5


# ------------------------------------------------------------- resumo


def test_o_resumo_avisa_o_que_a_rede_nao_tinha():
    so_mp3 = ranquear([arquivo("a.mp3", "ana", bitrate_kbps=320)])
    escolhidas = escolher_por_politica(so_mp3, Foco.SEM_PERDA)

    texto = resumir_politica(escolhidas, Foco.SEM_PERDA)
    assert "a rede não tinha" in texto
    assert "sem perda" in texto


def test_o_resumo_nao_reclama_quando_esta_tudo_la():
    texto = resumir_politica(
        escolher_por_politica(aprovados_variados(), Foco.MP3), Foco.MP3
    )
    assert "a rede não tinha" not in texto
    assert "MP3 320" in texto


def test_resumo_de_nada():
    assert resumir_politica([], Foco.MP3) == "nada escolhido"


@pytest.mark.parametrize("foco", list(Foco))
def test_todo_foco_tem_rotulo_legivel(foco):
    assert foco.rotulo and not foco.rotulo.islower() or "MP3" in foco.rotulo


def test_a_escolha_se_descreve():
    (uma,) = escolher_por_politica(ranquear([arquivo("a.flac", "ana")]), Foco.SEM_PERDA)
    assert isinstance(uma, Escolha)
    assert "sem perda" in str(uma)
