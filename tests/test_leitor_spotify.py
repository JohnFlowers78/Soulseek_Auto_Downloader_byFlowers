"""Testes do leitor do Spotify.

O que se testa aqui é tudo que **não** depende de rede: reconhecer o link, montar o
PKCE, e converter a resposta da API em `Faixa`. A dança do OAuth em si precisa de
navegador e conta — fica para o teste manual.
"""

import base64
import hashlib

import pytest

from leitor_spotify import (
    ESCOPOS,
    REDIRECIONAMENTO,
    ErroSpotify,
    LeitorSpotify,
    desafio_de,
    extrair_id_da_faixa,
    extrair_id_da_playlist,
    faixa_do_item,
    gerar_verificador,
    montar_url_de_autorizacao,
)

ID = "37i9dQZF1DXcBWIGoYBM5M"


# ------------------------------------------------------------------- links


@pytest.mark.parametrize(
    "entrada",
    [
        f"https://open.spotify.com/playlist/{ID}",
        f"https://open.spotify.com/playlist/{ID}?si=abc123",
        f"http://open.spotify.com/playlist/{ID}",
        f"spotify:playlist:{ID}",
        f"  https://open.spotify.com/playlist/{ID}  ",
        ID,
    ],
)
def test_reconhece_o_link_da_playlist_de_varias_formas(entrada):
    assert extrair_id_da_playlist(entrada) == ID


@pytest.mark.parametrize(
    "entrada", ["", "   ", "https://open.spotify.com/album/" + ID, "não é link", "abc"]
)
def test_o_que_nao_e_playlist_devolve_nada(entrada):
    assert extrair_id_da_playlist(entrada) is None


def test_reconhece_link_de_faixa():
    assert extrair_id_da_faixa(f"https://open.spotify.com/track/{ID}") == ID
    assert extrair_id_da_faixa(f"spotify:track:{ID}") == ID
    assert extrair_id_da_faixa(f"https://open.spotify.com/playlist/{ID}") is None


# -------------------------------------------------------------------- PKCE


def test_o_verificador_tem_o_tamanho_que_o_padrao_exige():
    # O PKCE pede entre 43 e 128 caracteres.
    for _ in range(20):
        assert 43 <= len(gerar_verificador()) <= 128


def test_cada_verificador_e_diferente():
    assert len({gerar_verificador() for _ in range(50)}) == 50


def test_o_desafio_e_o_sha256_em_base64url_sem_preenchimento():
    verificador = "um-verificador-de-teste-com-tamanho-suficiente-aqui"
    esperado = (
        base64.urlsafe_b64encode(hashlib.sha256(verificador.encode()).digest())
        .decode()
        .rstrip("=")
    )
    assert desafio_de(verificador) == esperado
    assert "=" not in desafio_de(verificador)


def test_a_url_de_autorizacao_nao_leva_o_verificador():
    # O ponto inteiro do PKCE: o segredo não trafega na primeira ida.
    verificador = gerar_verificador()
    url = montar_url_de_autorizacao("meu-client-id", verificador)

    assert verificador not in url
    assert desafio_de(verificador) in url


def test_a_url_leva_o_que_o_spotify_espera():
    url = montar_url_de_autorizacao("meu-client-id", gerar_verificador())

    assert url.startswith("https://accounts.spotify.com/authorize?")
    assert "client_id=meu-client-id" in url
    assert "code_challenge_method=S256" in url
    assert "response_type=code" in url
    for escopo in ESCOPOS.split():
        assert escopo in url


def test_o_redirecionamento_usa_o_endereco_numerico():
    # O Spotify exige HTTPS para nomes e só abre exceção para o loopback numérico —
    # "localhost" é recusado no cadastro do app.
    assert REDIRECIONAMENTO.startswith("http://127.0.0.1:")
    assert "localhost" not in REDIRECIONAMENTO


# ------------------------------------------------------- converter faixa


def item(**ajustes) -> dict:
    faixa = {
        "type": "track",
        "name": "Não Vou Ficar",
        "artists": [{"name": "Tim Maia"}],
        "album": {"name": "Tim Maia"},
        "duration_ms": 245000,
        "external_ids": {"isrc": "BRXXX7100001"},
    }
    faixa.update(ajustes)
    return {"track": faixa}


def test_converte_um_item_completo():
    faixa = faixa_do_item(item())

    assert faixa.artista == "Tim Maia"
    assert faixa.titulo == "Não Vou Ficar"
    assert faixa.album == "Tim Maia"
    assert faixa.duracao_s == 245.0
    assert faixa.isrc == "BRXXX7100001"


def test_varios_artistas_viram_uma_lista_separada_por_virgula():
    faixa = faixa_do_item(item(artists=[{"name": "Djavan"}, {"name": "Alcione"}]))
    assert faixa.artista == "Djavan, Alcione"


def test_faixa_removida_do_catalogo_e_ignorada():
    # Playlist antiga tem isso: o item fica, a faixa vira null.
    assert faixa_do_item({"track": None}) is None
    assert faixa_do_item({}) is None


def test_episodio_de_podcast_e_ignorado():
    assert faixa_do_item(item(type="episode")) is None


def test_faixa_sem_nome_e_ignorada():
    assert faixa_do_item(item(name="")) is None


def test_campos_ausentes_nao_explodem():
    faixa = faixa_do_item({"track": {"type": "track", "name": "Só o nome"}})
    assert faixa.titulo == "Só o nome"
    assert faixa.artista == ""
    assert faixa.duracao_s is None
    assert faixa.isrc == ""


# ------------------------------------------------------------- paginação


class HttpFalso:
    """Devolve as páginas na ordem, uma por chamada."""

    def __init__(self, paginas: list[dict], nome: str = "Minha Playlist"):
        self.paginas = list(paginas)
        self.nome = nome
        self.urls: list[str] = []
        self._proxima = 0

    def __call__(self, metodo, url, cabecalhos, corpo=None):
        self.urls.append(url)
        if "fields=name" in url:
            return {"name": self.nome}
        if self._proxima >= len(self.paginas):
            return {"items": [], "next": None}
        pagina = self.paginas[self._proxima]
        self._proxima += 1
        return pagina


def test_le_todas_as_paginas():
    paginas = [
        {"items": [item(), item(name="Segunda")], "next": "https://api/pagina2"},
        {"items": [item(name="Terceira")], "next": None},
    ]
    leitor = LeitorSpotify("token", HttpFalso(paginas))

    faixas = leitor.faixas_da_playlist(ID)
    assert [f.titulo for f in faixas] == ["Não Vou Ficar", "Segunda", "Terceira"]


def test_manda_o_token_no_cabecalho():
    registradas = []

    def http(metodo, url, cabecalhos, corpo=None):
        registradas.append(cabecalhos)
        return {"items": [], "next": None}

    LeitorSpotify("meu-token", http).faixas_da_playlist(ID)
    assert registradas[0]["Authorization"] == "Bearer meu-token"


def test_itens_invalidos_nao_entram_na_lista():
    paginas = [{"items": [item(), {"track": None}, item(type="episode")], "next": None}]
    assert len(LeitorSpotify("t", HttpFalso(paginas)).faixas_da_playlist(ID)) == 1


def test_ler_devolve_nome_e_faixas():
    paginas = [{"items": [item()], "next": None}]
    nome, faixas = LeitorSpotify("t", HttpFalso(paginas, "Set de Verão")).ler(
        f"https://open.spotify.com/playlist/{ID}"
    )
    assert nome == "Set de Verão"
    assert len(faixas) == 1


def test_link_invalido_explica_o_formato_esperado():
    with pytest.raises(ErroSpotify) as erro:
        LeitorSpotify("t", HttpFalso([])).ler("isso não é um link")
    assert "open.spotify.com/playlist" in str(erro.value)


def test_playlist_sem_nome_nao_fica_vazia():
    # O nome vira pasta no disco; vazio daria pasta sem nome.
    leitor = LeitorSpotify("t", HttpFalso([{"items": [], "next": None}], nome=""))
    assert leitor.nome_da_playlist(ID) == "Playlist sem nome"


def test_a_pagina_tem_um_teto_de_seguranca():
    # Um 'next' que aponta em círculo não pode prender o app para sempre.
    circular = {"items": [item()], "next": "https://api/mesma"}

    def http(metodo, url, cabecalhos, corpo=None):
        return circular

    faixas = LeitorSpotify("t", http).faixas_da_playlist(ID, limite_paginas=5)
    assert len(faixas) == 5
