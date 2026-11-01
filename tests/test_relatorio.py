"""Testes do relatório final da playlist.

Importa o comando de linha direto: o relatório é a única coisa que sobra depois de
uma corrida de horas, e precisa de rede de proteção tanto quanto o resto.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from baixar_playlist import _montar_relatorio, _relatorio  # noqa: E402
from baixador import Lote  # noqa: E402
from buscador import ResultadoDaBusca  # noqa: E402
from modelos import Candidato, EstadoTransferencia, Faixa, Transferencia  # noqa: E402


def faixa(titulo="Não Vou Ficar") -> Faixa:
    return Faixa(artista="Djavan", titulo=titulo, duracao_s=250.0)


def transferencia(estado, nome="musica.flac", local="") -> Transferencia:
    return Transferencia(
        candidato=Candidato(usuario="joao", caminho=rf"x\{nome}", tamanho_bytes=1000),
        estado=estado,
        caminho_local=local,
    )


def com_lote(resultado, lote, lotes):
    lotes[id(resultado)] = lote
    return resultado


def test_separa_as_tres_listas(tmp_path):
    lotes = {}
    baixou = com_lote(
        ResultadoDaBusca(faixa=faixa("Baixou")),
        Lote([transferencia(EstadoTransferencia.CONCLUIDA, local=str(tmp_path / "a.flac"))]),
        lotes,
    )
    presa = com_lote(
        ResultadoDaBusca(faixa=faixa("Presa")),
        Lote([transferencia(EstadoTransferencia.NA_FILA)]),
        lotes,
    )
    sumida = ResultadoDaBusca(faixa=faixa("Sumida"))

    texto = "\n".join(
        _montar_relatorio("Minha Lista", [baixou, presa, sumida], lotes, tmp_path)
    )

    assert "✅ BAIXADAS (1)" in texto
    assert "⏳ PRESAS NA FILA (1)" in texto
    assert "❌ NÃO ENCONTRADAS (1)" in texto


def test_diz_por_que_cada_faixa_nao_veio(tmp_path):
    de_outro = ResultadoDaBusca(
        faixa=faixa("De outro"),
        de_outro_artista=[Candidato(usuario="x", caminho="a.flac", tamanho_bytes=1)],
    )
    outra_musica = ResultadoDaBusca(
        faixa=faixa("Outra música"),
        de_outra_musica=[Candidato(usuario="x", caminho="b.flac", tamanho_bytes=1)],
    )
    texto = "\n".join(_montar_relatorio("L", [de_outro, outra_musica], {}, tmp_path))

    assert "1 de outro artista" in texto
    assert "1 de outra música do artista" in texto


def test_as_falhas_entram_com_o_motivo(tmp_path):
    falhas = [(faixa("Quebrou"), "ErroSlskd: HTTP 409")]
    texto = "\n".join(_montar_relatorio("L", [], {}, tmp_path, falhas))

    assert "💥 DERAM ERRO (1)" in texto
    assert "HTTP 409" in texto


def test_grava_o_relatorio_ao_lado_das_musicas(tmp_path):
    # Numa corrida de horas o histórico do terminal rola e a janela fecha. De manhã,
    # o arquivo é o que sobra.
    destino = tmp_path / "Minha Playlist"
    _relatorio("Minha Playlist", [], {}, destino)

    arquivo = destino / "_relatorio.txt"
    assert arquivo.is_file()
    assert "PLAYLIST TERMINADA" in arquivo.read_text(encoding="utf-8")


def test_o_relatorio_tem_data_e_hora(tmp_path):
    destino = tmp_path / "x"
    _relatorio("x", [], {}, destino)
    texto = (destino / "_relatorio.txt").read_text(encoding="utf-8")

    # Sem data, dois relatórios de noites diferentes viram o mesmo papel.
    assert any(c.isdigit() for c in texto.splitlines()[2])


def test_nao_conseguir_gravar_nao_derruba_a_corrida(tmp_path, monkeypatch):
    # Uma corrida que deu certo não pode terminar em traceback por causa do papel.
    def recusar(*_args, **_kwargs):
        raise OSError("disco cheio")

    monkeypatch.setattr(Path, "write_text", recusar)
    _relatorio("x", [], {}, tmp_path / "y")  # não levanta


def test_acentos_sobrevivem_no_arquivo(tmp_path):
    destino = tmp_path / "Tirar pira no Violão"
    resultado = ResultadoDaBusca(faixa=Faixa(artista="Céu", titulo="Malemolência"))
    _relatorio("Tirar pira no Violão", [resultado], {}, destino)

    texto = (destino / "_relatorio.txt").read_text(encoding="utf-8")
    assert "Malemolência" in texto
    assert "Violão" in texto
