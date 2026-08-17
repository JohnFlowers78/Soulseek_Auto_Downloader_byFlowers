"""Testes do vocabulário comum aos dois motores."""

import pytest

from modelos import (
    Candidato,
    EstadoTransferencia,
    Faixa,
    ResultadoDaFaixa,
    Transferencia,
)


def candidato(caminho: str = r"@@abc\Music\faixa.flac") -> Candidato:
    return Candidato(usuario="fulano", caminho=caminho, tamanho_bytes=10_000_000)


# ------------------------------------------------------------------- caminho


@pytest.mark.parametrize(
    "caminho, esperado",
    [
        (r"@@abc\Music\Artista\faixa.mp3", "faixa.mp3"),          # Windows, o normal
        ("/home/fulano/Music/faixa.flac", "faixa.flac"),          # quem compartilha do Linux
        (r"@@abc\Music/Misturado\faixa.wav", "faixa.wav"),        # as duas barras juntas
        ("faixa.aiff", "faixa.aiff"),                             # sem pasta nenhuma
    ],
)
def test_extrai_o_nome_do_arquivo_de_qualquer_barra(caminho, esperado):
    assert candidato(caminho).nome_arquivo == esperado


@pytest.mark.parametrize(
    "caminho, esperado",
    [
        (r"x\faixa.MP3", "mp3"),
        (r"x\faixa.FLAC", "flac"),
        (r"x\faixa_sem_ponto", ""),
        (r"x\pasta.com.ponto\faixa.wav", "wav"),
    ],
)
def test_extensao_vem_minuscula_e_nao_explode_sem_ponto(caminho, esperado):
    assert candidato(caminho).extensao == esperado


def test_pasta_com_ponto_nao_confunde_arquivo_sem_extensao():
    # "x/album.2011/faixa" não tem extensão — o ponto está na PASTA.
    assert candidato(r"x\album.2011\faixa").extensao == ""


# --------------------------------------------------------------- transferência


def test_progresso_e_uma_fracao():
    t = Transferencia(candidato=candidato(), bytes_transferidos=5_000_000)
    assert t.progresso == 0.5


def test_progresso_nao_passa_de_um():
    # Alguns clientes reportam mais bytes que o tamanho anunciado.
    t = Transferencia(candidato=candidato(), bytes_transferidos=99_000_000)
    assert t.progresso == 1.0


def test_progresso_com_tamanho_desconhecido_nao_divide_por_zero():
    vazio = Candidato(usuario="x", caminho="x/a.mp3", tamanho_bytes=0)
    assert Transferencia(candidato=vazio, bytes_transferidos=100).progresso == 0.0


@pytest.mark.parametrize(
    "estado, terminou",
    [
        (EstadoTransferencia.NA_FILA, False),
        (EstadoTransferencia.BAIXANDO, False),
        (EstadoTransferencia.CONCLUIDA, True),
        (EstadoTransferencia.FALHOU, True),
        (EstadoTransferencia.CANCELADA, True),
    ],
)
def test_saber_se_terminou(estado, terminou):
    assert Transferencia(candidato=candidato(), estado=estado).terminou is terminou


# ------------------------------------------------- as três listas da tela


def faixa() -> Faixa:
    return Faixa(artista="Djavan", titulo="Não Vou Ficar", duracao_s=250.0)


def transferencia(estado: EstadoTransferencia) -> Transferencia:
    return Transferencia(candidato=candidato(), estado=estado)


def test_faixa_sem_nenhuma_transferencia_e_nao_encontrada():
    resultado = ResultadoDaFaixa(faixa=faixa())
    assert resultado.nao_encontrada
    assert not resultado.baixou
    assert not resultado.preso_na_fila


def test_faixa_com_download_concluido_conta_como_baixada():
    resultado = ResultadoDaFaixa(
        faixa=faixa(),
        transferencias=[transferencia(EstadoTransferencia.CONCLUIDA)],
    )
    assert resultado.baixou
    assert not resultado.preso_na_fila
    assert not resultado.nao_encontrada


def test_faixa_so_na_fila_e_o_caso_do_seeder_offline():
    resultado = ResultadoDaFaixa(
        faixa=faixa(),
        transferencias=[transferencia(EstadoTransferencia.NA_FILA)],
    )
    assert resultado.preso_na_fila
    assert not resultado.baixou


def test_uma_concluida_entre_varias_ja_tira_da_lista_de_presas():
    # Baixamos duas opções: uma terminou, a outra ficou na fila. A faixa está resolvida.
    resultado = ResultadoDaFaixa(
        faixa=faixa(),
        transferencias=[
            transferencia(EstadoTransferencia.NA_FILA),
            transferencia(EstadoTransferencia.CONCLUIDA),
        ],
    )
    assert resultado.baixou
    assert not resultado.preso_na_fila


def test_todas_falharam_nao_e_preso_nem_baixado():
    resultado = ResultadoDaFaixa(
        faixa=faixa(),
        transferencias=[transferencia(EstadoTransferencia.FALHOU)],
    )
    assert not resultado.baixou
    assert not resultado.preso_na_fila
    # Achou algo (tentou), então não é "não encontrada" — é falha de download.
    assert not resultado.nao_encontrada


def test_as_tres_listas_sao_mutuamente_exclusivas():
    casos = [
        ResultadoDaFaixa(faixa=faixa()),
        ResultadoDaFaixa(faixa=faixa(), transferencias=[transferencia(EstadoTransferencia.NA_FILA)]),
        ResultadoDaFaixa(faixa=faixa(), transferencias=[transferencia(EstadoTransferencia.CONCLUIDA)]),
    ]
    for resultado in casos:
        marcados = [resultado.baixou, resultado.preso_na_fila, resultado.nao_encontrada]
        assert sum(marcados) <= 1, "uma faixa não pode estar em duas listas ao mesmo tempo"


def test_faixa_se_apresenta_legivel():
    assert str(faixa()) == "Djavan — Não Vou Ficar"
