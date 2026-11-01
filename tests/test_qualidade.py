"""Testes do filtro de qualidade e do ranking.

Lógica pura: não toca em rede, disco nem em nenhum dado real.
"""

import pytest

from modelos import Candidato
from qualidade import (
    Criterios,
    avaliar,
    bitrate_estimado_kbps,
    escolher_melhores,
    ranquear,
    reprovados,
)

TAMANHO_OK = 10_000_000
DURACAO = 250.0


def candidato(**ajustes) -> Candidato:
    """Um candidato plausível; cada teste muda só o que lhe interessa."""
    padrao = dict(
        usuario="fulano",
        caminho=r"@@abc\Music\Artista\faixa.flac",
        tamanho_bytes=TAMANHO_OK,
        duracao_s=DURACAO,
    )
    return Candidato(**{**padrao, **ajustes})


# ------------------------------------------------------------------ estimativa


@pytest.mark.parametrize(
    "tamanho, duracao, esperado",
    [
        (10_000_000, 250.0, 320),
        (5_000_000, 250.0, 160),
        (4_000_000, 250.0, 128),
    ],
)
def test_estima_bitrate_pelo_tamanho_e_duracao(tamanho, duracao, esperado):
    assert bitrate_estimado_kbps(tamanho, duracao) == esperado


@pytest.mark.parametrize("tamanho, duracao", [(0, 250.0), (10_000_000, None), (10_000_000, 0)])
def test_estimativa_devolve_nada_quando_falta_dado(tamanho, duracao):
    assert bitrate_estimado_kbps(tamanho, duracao) is None


# --------------------------------------------------------------------- aceite


def test_flac_entra_sem_precisar_de_bitrate():
    # Sem perda não passa por checagem de bitrate: um FLAC varia de 400 a 1400 kbps
    # conforme a música, e todos são o áudio original.
    avaliacao = avaliar(candidato(caminho="x/musica.flac", bitrate_kbps=None))
    assert avaliacao.aceito


@pytest.mark.parametrize("extensao", ["flac", "wav", "aiff", "aif"])
def test_todos_os_sem_perda_pedidos_entram(extensao):
    assert avaliar(candidato(caminho=f"x/musica.{extensao}")).aceito


def test_mp3_320_entra():
    avaliacao = avaliar(candidato(caminho="x/musica.mp3", bitrate_kbps=320))
    assert avaliacao.aceito
    assert avaliacao.bitrate_usado_kbps == 320


def test_mp3_319_entra_pela_tolerancia_de_arredondamento():
    # Quem informa 320 às vezes informa 319 — não é motivo para descartar.
    assert avaliar(candidato(caminho="x/musica.mp3", bitrate_kbps=319)).aceito


def test_mp3_128_e_barrado_com_motivo_legivel():
    avaliacao = avaliar(candidato(caminho="x/musica.mp3", bitrate_kbps=128))
    assert not avaliacao.aceito
    assert "bitrate abaixo do mínimo" in avaliacao.motivo
    assert "128" in avaliacao.motivo


def test_m4a_256_entra_porque_aac_rende_mais_por_bit():
    assert avaliar(candidato(caminho="x/musica.m4a", bitrate_kbps=256)).aceito


def test_m4a_128_nao_entra():
    assert not avaliar(candidato(caminho="x/musica.m4a", bitrate_kbps=128)).aceito


@pytest.mark.parametrize("extensao", ["ogg", "opus", "wma", "mp4", "jpg"])
def test_formato_fora_da_lista_e_barrado(extensao):
    avaliacao = avaliar(candidato(caminho=f"x/arquivo.{extensao}"))
    assert not avaliacao.aceito
    assert "formato não aceito" in avaliacao.motivo


def test_arquivo_sem_extensao_e_barrado_sem_explodir():
    avaliacao = avaliar(candidato(caminho="x/arquivo_sem_ponto"))
    assert not avaliacao.aceito
    assert "sem extensão" in avaliacao.motivo


def test_fila_comprida_demais_e_barrada():
    """Não é impaciência: é desvio de um defeito do slskd.

    Ele desiste de entrar numa fila remota depois de 180 s — e foi nesse caminho de
    desistência que quebrou com exceção fatal, levando o processo inteiro junto no
    meio de uma playlist. Fila de 677 (número real da rede) não anda nesse tempo.
    """
    avaliacao = avaliar(candidato(posicao_fila=677))
    assert not avaliacao.aceito
    assert "fila do usuário comprida demais" in avaliacao.motivo


def test_fila_curta_passa():
    assert avaliar(candidato(posicao_fila=10)).aceito


def test_sem_informacao_de_fila_nao_reprova():
    assert avaliar(candidato(posicao_fila=None)).aceito


def test_o_teto_da_fila_e_configuravel():
    apertado = Criterios(fila_maxima=5)
    assert not avaliar(candidato(posicao_fila=10), criterios=apertado).aceito


def test_arquivo_pequeno_demais_e_barrado():
    # Capa de álbum, pedaço de download, arquivo quebrado.
    avaliacao = avaliar(candidato(tamanho_bytes=50_000))
    assert not avaliacao.aceito
    assert "pequeno demais" in avaliacao.motivo


# ------------------------------------------------------------------- duração


def test_duracao_muito_diferente_reprova():
    # É esta checagem que separa a faixa certa do remix de mesmo nome.
    avaliacao = avaliar(candidato(duracao_s=400.0), duracao_esperada_s=DURACAO)
    assert not avaliacao.aceito
    assert "duração fora do esperado" in avaliacao.motivo


def test_duracao_dentro_da_tolerancia_passa():
    assert avaliar(candidato(duracao_s=253.0), duracao_esperada_s=DURACAO).aceito


def test_sem_duracao_esperada_a_checagem_e_pulada():
    # Playlist lida pelo navegador nem sempre traz duração — melhor arriscar do que
    # descartar tudo.
    assert avaliar(candidato(duracao_s=400.0), duracao_esperada_s=None).aceito


def test_candidato_sem_duracao_nao_reprova_por_duracao():
    assert avaliar(candidato(duracao_s=None), duracao_esperada_s=DURACAO).aceito


# ---------------------------------------------------- bitrate estimado (SoulseekQt)


def test_estima_o_bitrate_quando_o_motor_nao_informa():
    # O caso do SoulseekQt: a tela dá nome e tamanho, mais nada.
    avaliacao = avaliar(candidato(caminho="x/musica.mp3", bitrate_kbps=None))
    assert avaliacao.aceito
    assert avaliacao.bitrate_estimado
    assert avaliacao.bitrate_usado_kbps == 320


def test_estimativa_tambem_reprova_o_que_e_ruim():
    avaliacao = avaliar(
        candidato(caminho="x/musica.mp3", bitrate_kbps=None, tamanho_bytes=4_000_000)
    )
    assert not avaliacao.aceito
    assert "estimado" in avaliacao.motivo


def test_sem_bitrate_e_sem_duracao_nao_da_para_julgar():
    avaliacao = avaliar(candidato(caminho="x/musica.mp3", bitrate_kbps=None, duracao_s=None))
    assert not avaliacao.aceito
    assert "não dá para saber a qualidade" in avaliacao.motivo


def test_bitrate_estimado_perde_para_o_declarado_no_empate():
    declarado = avaliar(candidato(caminho="x/a.mp3", bitrate_kbps=320, usuario="a"))
    estimado = avaliar(candidato(caminho="x/b.mp3", bitrate_kbps=None, usuario="b"))
    assert declarado.pontos > estimado.pontos


# -------------------------------------------------------------------- ranking


def test_sem_perda_ganha_de_com_perda():
    lista = [
        candidato(caminho="x/a.mp3", bitrate_kbps=320, usuario="a"),
        candidato(caminho="x/b.flac", usuario="b"),
    ]
    melhor = ranquear(lista)[0]
    assert melhor.candidato.extensao == "flac"


def test_flac_ganha_de_wav_por_preferencia():
    lista = [
        candidato(caminho="x/a.wav", usuario="a"),
        candidato(caminho="x/b.flac", usuario="b"),
    ]
    assert ranquear(lista)[0].candidato.extensao == "flac"


def test_slot_livre_desempata_entre_iguais():
    lista = [
        candidato(caminho="x/a.flac", usuario="ocupado", slot_livre=False, posicao_fila=10),
        candidato(caminho="x/b.flac", usuario="livre", slot_livre=True),
    ]
    assert ranquear(lista)[0].candidato.usuario == "livre"


def test_vinte_e_quatro_bits_desempata_entre_iguais():
    lista = [
        candidato(caminho="x/a.flac", usuario="a"),
        candidato(caminho="x/b.flac", usuario="b", profundidade_bits=24, taxa_amostragem_hz=96_000),
    ]
    assert ranquear(lista)[0].candidato.usuario == "b"


def test_ranquear_devolve_so_os_aprovados():
    lista = [
        candidato(caminho="x/a.flac", usuario="a"),
        candidato(caminho="x/b.ogg", usuario="b"),
        candidato(caminho="x/c.mp3", bitrate_kbps=96, usuario="c"),
    ]
    aprovados = ranquear(lista)
    assert len(aprovados) == 1
    assert all(a.aceito for a in aprovados)


def test_ranquear_com_lista_vazia():
    assert ranquear([]) == []


def test_reprovados_explicam_cada_descarte():
    lista = [
        candidato(caminho="x/a.flac", usuario="a"),
        candidato(caminho="x/b.ogg", usuario="b"),
        candidato(caminho="x/c.mp3", bitrate_kbps=96, usuario="c"),
    ]
    motivos = [a.motivo for a in reprovados(lista)]
    assert len(motivos) == 2
    assert all(motivo for motivo in motivos)


# ------------------------------------------------------------------- escolha


def test_escolhe_de_usuarios_diferentes():
    # Duas opções do mesmo usuário não são duas chances: se ele cair, caem juntas.
    aprovados = ranquear([
        candidato(caminho="x/a.flac", usuario="joao", slot_livre=True),
        candidato(caminho="x/b.flac", usuario="joao"),
        candidato(caminho="x/c.mp3", bitrate_kbps=320, usuario="maria"),
    ])
    escolhidos = escolher_melhores(aprovados, quantidade=2)
    assert {e.candidato.usuario for e in escolhidos} == {"joao", "maria"}


def test_repete_usuario_so_quando_nao_ha_mais_ninguem():
    aprovados = ranquear([
        candidato(caminho="x/a.flac", usuario="joao", slot_livre=True),
        candidato(caminho="x/b.flac", usuario="joao"),
    ])
    escolhidos = escolher_melhores(aprovados, quantidade=2)
    assert len(escolhidos) == 2
    assert all(e.candidato.usuario == "joao" for e in escolhidos)


def test_escolha_respeita_a_ordem_de_qualidade():
    aprovados = ranquear([
        candidato(caminho="x/a.mp3", bitrate_kbps=320, usuario="a"),
        candidato(caminho="x/b.flac", usuario="b"),
    ])
    assert escolher_melhores(aprovados, quantidade=1)[0].candidato.extensao == "flac"


def test_escolha_sem_diversificar_pega_os_melhores_puros():
    aprovados = ranquear([
        candidato(caminho="x/a.flac", usuario="joao", slot_livre=True),
        candidato(caminho="x/b.flac", usuario="joao"),
        candidato(caminho="x/c.mp3", bitrate_kbps=320, usuario="maria"),
    ])
    escolhidos = escolher_melhores(aprovados, quantidade=2, diversificar_por_usuario=False)
    assert all(e.candidato.usuario == "joao" for e in escolhidos)


def test_escolher_zero_devolve_vazio():
    assert escolher_melhores([], quantidade=0) == []
    assert escolher_melhores([avaliar(candidato())], quantidade=0) == []


def test_pedir_mais_do_que_existe_devolve_o_que_ha():
    aprovados = ranquear([candidato(caminho="x/a.flac", usuario="a")])
    assert len(escolher_melhores(aprovados, quantidade=5)) == 1


# ----------------------------------------------------------------- critérios


def test_criterios_podem_ser_afrouxados():
    # A configuração do app vai mexer nisso — o módulo não pode ter regra cravada.
    frouxo = Criterios(minimo_mp3_kbps=192)
    assert avaliar(candidato(caminho="x/a.mp3", bitrate_kbps=192), criterios=frouxo).aceito
    assert not avaliar(candidato(caminho="x/a.mp3", bitrate_kbps=192)).aceito


def test_criterios_podem_aceitar_outro_formato():
    com_ogg = Criterios(formatos_com_perda=("mp3", "m4a", "aac", "ogg"))
    assert avaliar(candidato(caminho="x/a.ogg", bitrate_kbps=320), criterios=com_ogg).aceito
