"""Testes da comparação com o acervo.

Aqui a pergunta não é "esse arquivo presta?" e sim "esse arquivo é melhor do que o que eu
já tenho?". Baixar um FLAC para substituir um FLAC gasta cota de busca, banda e o tempo do
usuário para terminar exatamente onde começou.
"""

from pathlib import Path

import pytest

from modelos import ArquivoLocal, Candidato, Comparacao, Faixa
from qualidade import (
    NIVEL_COM_PERDA_BOM,
    NIVEL_COM_PERDA_FRACO,
    NIVEL_DESCONHECIDO,
    NIVEL_SEM_PERDA,
    NIVEL_SEM_PERDA_24,
    NIVEL_SEM_PERDA_ALTA_TAXA,
    avaliar,
    filtrar_upgrades,
    nivel_de_qualidade,
    vale_a_pena_trocar,
)

FAIXA = Faixa(artista="Djavan", titulo="Se", duracao_s=250.0)


def local(nome="Djavan - Se.flac", **ajustes) -> ArquivoLocal:
    padrao = dict(
        caminho=Path("acervo") / nome,
        faixa=FAIXA,
        tamanho_bytes=30_000_000,
        duracao_s=250.0,
        origem="acervo",
    )
    return ArquivoLocal(**{**padrao, **ajustes})


def achado(nome="Djavan - Se.flac", **ajustes):
    padrao = dict(
        usuario="fulano",
        caminho=rf"@@abc\Music\{nome}",
        tamanho_bytes=30_000_000,
        duracao_s=250.0,
    )
    return avaliar(Candidato(**{**padrao, **ajustes}))


# --------------------------------------------------------------- degraus


@pytest.mark.parametrize(
    "formato, bitrate, bits, taxa, esperado",
    [
        ("flac", None, 16, 44100, NIVEL_SEM_PERDA),
        ("wav", None, 16, 44100, NIVEL_SEM_PERDA),
        ("aiff", None, 24, 44100, NIVEL_SEM_PERDA_24),
        ("flac", None, 24, 96000, NIVEL_SEM_PERDA_ALTA_TAXA),
        ("mp3", 320, None, 44100, NIVEL_COM_PERDA_BOM),
        ("mp3", 128, None, 44100, NIVEL_COM_PERDA_FRACO),
        ("m4a", 256, None, 44100, NIVEL_COM_PERDA_BOM),
        ("m4a", 128, None, 44100, NIVEL_COM_PERDA_FRACO),
        ("mp3", None, None, 44100, NIVEL_DESCONHECIDO),
        ("", None, None, None, NIVEL_DESCONHECIDO),
    ],
)
def test_cada_arquivo_cai_no_seu_degrau(formato, bitrate, bits, taxa, esperado):
    assert nivel_de_qualidade(formato, bitrate, bits, taxa) == esperado


def test_bitrate_nao_separa_os_sem_perda():
    # Um FLAC de 700 kbps e um de 1100 kbps carregam o mesmo áudio original — a diferença
    # é a densidade da música, não a qualidade.
    assert nivel_de_qualidade("flac", 700, 16, 44100) == nivel_de_qualidade("flac", 1100, 16, 44100)


def test_sem_perda_sempre_ganha_de_com_perda():
    assert nivel_de_qualidade("flac", None, 16, 44100) > nivel_de_qualidade("mp3", 320)


# ------------------------------------------------------ vale a pena trocar


def test_mp3_ruim_no_acervo_vale_trocar_por_flac():
    vale, motivo = vale_a_pena_trocar(local("a.mp3", bitrate_kbps=128), achado("a.flac"))
    assert vale
    assert "sobe de" in motivo


def test_mp3_ruim_vale_trocar_por_mp3_320():
    vale, _ = vale_a_pena_trocar(
        local("a.mp3", bitrate_kbps=128), achado("a.mp3", bitrate_kbps=320)
    )
    assert vale


def test_flac_no_acervo_nao_se_troca_por_mp3():
    vale, motivo = vale_a_pena_trocar(
        local("a.flac", profundidade_bits=16, taxa_amostragem_hz=44100),
        achado("a.mp3", bitrate_kbps=320),
    )
    assert not vale
    assert "seria piora" in motivo


def test_flac_igual_a_flac_nao_compensa():
    # O caso que a funcionalidade existe para evitar: terminar onde começou.
    atual = local("a.flac", profundidade_bits=16, taxa_amostragem_hz=44100)
    candidato = achado("a.flac", profundidade_bits=16, taxa_amostragem_hz=44100)

    vale, motivo = vale_a_pena_trocar(atual, candidato)
    assert not vale
    assert "mesma qualidade" in motivo


def test_flac_16_vale_trocar_por_flac_24():
    atual = local("a.flac", profundidade_bits=16, taxa_amostragem_hz=44100)
    candidato = achado("a.flac", profundidade_bits=24, taxa_amostragem_hz=96000)

    vale, _ = vale_a_pena_trocar(atual, candidato)
    assert vale


def test_mp3_320_igual_a_mp3_320_nao_compensa():
    vale, _ = vale_a_pena_trocar(
        local("a.mp3", bitrate_kbps=320), achado("a.mp3", bitrate_kbps=320)
    )
    assert not vale


def test_arquivo_suspeito_no_acervo_vale_trocar_mesmo_pelo_mesmo_degrau():
    # O "MP3 320" que corta em 16 kHz: o degrau declarado dele não vale nada.
    atual = local("a.mp3", bitrate_kbps=320, corte_hz=16000, suspeito=True)
    vale, motivo = vale_a_pena_trocar(atual, achado("a.mp3", bitrate_kbps=320))

    assert vale
    assert "suspeito" in motivo


def test_suspeito_nao_justifica_baixar_coisa_ruim():
    atual = local("a.mp3", bitrate_kbps=320, suspeito=True)
    # Um 128 é reprovado antes mesmo de chegar na comparação.
    vale, _ = vale_a_pena_trocar(atual, achado("a.mp3", bitrate_kbps=128))
    assert not vale


def test_qualidade_desconhecida_no_acervo_vale_comparar():
    # Sem ffmpeg, ou com arquivo que não informa nada: melhor baixar e olhar o gráfico.
    vale, motivo = vale_a_pena_trocar(local("a.mp3", bitrate_kbps=None), achado("a.flac"))
    assert vale
    assert "não dá para saber" in motivo


def test_candidato_reprovado_nao_chega_a_ser_comparado():
    vale, motivo = vale_a_pena_trocar(
        local("a.mp3", bitrate_kbps=128), achado("a.ogg", bitrate_kbps=320)
    )
    assert not vale
    assert "reprovado antes da comparação" in motivo


def test_o_motivo_sempre_vem_escrito():
    # Quando o app NÃO baixa, o usuário precisa saber que foi decisão e não falha.
    casos = [
        (local("a.flac"), achado("a.mp3", bitrate_kbps=320)),
        (local("a.mp3", bitrate_kbps=128), achado("a.flac")),
        (local("a.mp3", bitrate_kbps=320), achado("a.mp3", bitrate_kbps=320)),
    ]
    for atual, candidato in casos:
        _, motivo = vale_a_pena_trocar(atual, candidato)
        assert motivo.strip()


# ------------------------------------------------------------ filtragem


def test_filtrar_separa_os_que_melhoram_dos_que_nao():
    atual = local("a.mp3", bitrate_kbps=128)
    aprovados = [
        achado("a.flac", usuario="joao"),
        achado("a.mp3", bitrate_kbps=320, usuario="maria"),
    ]
    valem, descartados = filtrar_upgrades(atual, aprovados)

    assert len(valem) == 2
    assert descartados == []


def test_filtrar_devolve_o_motivo_de_cada_descarte():
    atual = local("a.flac", profundidade_bits=16, taxa_amostragem_hz=44100)
    aprovados = [achado("a.mp3", bitrate_kbps=320), achado("a.flac")]
    valem, descartados = filtrar_upgrades(atual, aprovados)

    assert valem == []
    assert len(descartados) == 2
    assert all(motivo for _, motivo in descartados)


def test_filtrar_com_lista_vazia():
    assert filtrar_upgrades(local(), []) == ([], [])


# --------------------------------------------------------- comparação


def test_comparacao_separa_acervo_de_baixadas():
    comparacao = Comparacao(
        faixa=FAIXA,
        versoes=[
            local("minha.flac", origem="acervo"),
            local("dele.flac", origem="baixada de joao"),
            local("dela.wav", origem="baixada de maria"),
        ],
    )
    assert len(comparacao.do_acervo) == 1
    assert len(comparacao.baixadas) == 2


def test_comparacao_aguenta_mais_de_duas_de_cada_lado():
    # Foi o pedido explícito: mais de 2 na mesma pasta E mais de duas baixadas.
    comparacao = Comparacao(
        faixa=FAIXA,
        versoes=[
            local("a.flac", origem="acervo"),
            local("b.wav", origem="acervo"),
            local("c.mp3", origem="acervo"),
            local("d.flac", origem="baixada de joao"),
            local("e.flac", origem="baixada de maria"),
            local("f.aiff", origem="baixada de pedro"),
        ],
    )
    assert len(comparacao.do_acervo) == 3
    assert len(comparacao.baixadas) == 3
    assert comparacao.tem_o_que_comparar


def test_uma_versao_sozinha_nao_e_comparacao():
    comparacao = Comparacao(faixa=FAIXA, versoes=[local("a.flac")])
    assert not comparacao.tem_o_que_comparar


def test_comparacao_vazia_nao_explode():
    comparacao = Comparacao(faixa=FAIXA)
    assert comparacao.versoes == []
    assert not comparacao.tem_o_que_comparar
