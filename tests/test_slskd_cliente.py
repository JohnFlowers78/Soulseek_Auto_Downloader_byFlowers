"""Testes do cliente do slskd.

As amostras de JSON aqui foram **copiadas de respostas reais** da rede Soulseek, medidas
com o slskd rodando. Não são inventadas — é o que diferencia um teste que protege de um
teste que confirma a suposição errada.

Nada toca a rede: o transporte HTTP é injetado.
"""

import pytest

from limitador import LimitadorDeBuscas
from modelos import EstadoTransferencia
from slskd_cliente import (
    ClienteSlskd,
    ErroSlskd,
    candidatos_das_respostas,
    traduzir_estado,
)

# --------------------------------------------------------------------------
# Amostras reais, medidas na rede em 31/10/2026
# --------------------------------------------------------------------------

ARQUIVO_MP3 = {
    "bitRate": 192,
    "code": 1,
    "extension": "",  # vem vazio SEMPRE — por isso a extensão sai do filename
    "filename": "@@soiae\\DOWNLOADS\\TIM MAIA\\6. PRA VOCÊ VOLTAR.mp3",
    "length": 225,
    "size": 5403074,
    "isLocked": False,
}

ARQUIVO_FLAC = {
    "bitDepth": 16,
    "code": 1,
    "extension": "",
    "filename": "@@pxqjv\\MP3\\Tim Maia - Discografia\\07 - Voce.flac",
    "length": 245,
    "sampleRate": 44100,
    "size": 28683056,
    "isLocked": False,
}

ARQUIVO_TRAVADO = {
    "bitDepth": 16,
    "code": 1,
    "extension": "",
    "filename": "@@mqmhz\\Music\\Daft Punk\\One More Time.flac",
    "length": 235,
    "sampleRate": 44100,
    "size": 29653558,
    "isLocked": True,
}

RESPOSTA = {
    "fileCount": 8,
    "hasFreeUploadSlot": True,
    "lockedFileCount": 0,
    "queueLength": 677,
    "token": 160,
    "uploadSpeed": 980084,
    "username": "Studio 560",
    "files": [ARQUIVO_MP3, ARQUIVO_FLAC],
}


class TransporteFalso:
    """Responde o que mandarem e guarda tudo que foi chamado.

    As rotas da busca são tratadas **explicitamente**, e não por prefixo, porque
    `/searches/{id}` e `/searches/{id}/responses` começam igual — casar por prefixo
    devolvia o dicionário de estado onde o código espera a lista de respostas.
    """

    def __init__(
        self,
        respostas: dict | None = None,
        busca_completa: bool = True,
        respostas_da_busca: list | None = None,
    ):
        self.respostas = respostas or {}
        self.busca_completa = busca_completa
        self.respostas_da_busca = respostas_da_busca if respostas_da_busca is not None else []
        self.chamadas: list[tuple[str, str, object]] = []

    def __call__(self, metodo: str, caminho: str, corpo=None):
        self.chamadas.append((metodo, caminho, corpo))

        if caminho.endswith("/responses"):
            return 200, self.respostas_da_busca
        if caminho.startswith("/searches/") and metodo == "GET":
            return 200, {"isComplete": self.busca_completa, "state": "InProgress"}

        for chave, valor in self.respostas.items():
            if caminho.startswith(chave):
                return 200, (valor() if callable(valor) else valor)
        return 200, None

    def caminhos(self, metodo: str | None = None) -> list[str]:
        return [c for m, c, _ in self.chamadas if metodo is None or m == metodo]


def cliente(transporte, limitador=None) -> ClienteSlskd:
    return ClienteSlskd(
        chave_api="chave",
        limitador=limitador or LimitadorDeBuscas(limite=100, janela_s=1),
        transporte=transporte,
        dormir=lambda _: None,
    )


# ------------------------------------------------------------- conversão


def test_cada_arquivo_vira_um_candidato():
    candidatos = candidatos_das_respostas([RESPOSTA])
    assert len(candidatos) == 2


def test_arquivo_travado_e_ignorado():
    # lockedFiles/isLocked = o usuário TEM o arquivo mas não compartilha com você.
    # Enfileirar um desses é download que nunca completa.
    resposta = {**RESPOSTA, "files": [ARQUIVO_MP3, ARQUIVO_TRAVADO]}
    candidatos = candidatos_das_respostas([resposta])

    assert len(candidatos) == 1
    assert candidatos[0].extensao == "mp3"


def test_a_extensao_sai_do_nome_porque_o_campo_vem_vazio():
    (mp3, flac) = candidatos_das_respostas([RESPOSTA])
    assert ARQUIVO_MP3["extension"] == ""  # a API é assim mesmo
    assert mp3.extensao == "mp3"
    assert flac.extensao == "flac"


def test_mp3_traz_bitrate_e_flac_nao():
    (mp3, flac) = candidatos_das_respostas([RESPOSTA])
    assert mp3.bitrate_kbps == 192
    assert flac.bitrate_kbps is None
    # No FLAC o que vale é profundidade e taxa.
    assert flac.profundidade_bits == 16
    assert flac.taxa_amostragem_hz == 44100


def test_os_dados_do_usuario_vao_para_todos_os_arquivos_dele():
    for candidato in candidatos_das_respostas([RESPOSTA]):
        assert candidato.usuario == "Studio 560"
        assert candidato.slot_livre is True
        assert candidato.posicao_fila == 677
        assert candidato.velocidade_bps == 980084


def test_duracao_e_tamanho_vem_certos():
    (mp3, _) = candidatos_das_respostas([RESPOSTA])
    assert mp3.duracao_s == 225.0
    assert mp3.tamanho_bytes == 5403074


def test_nome_com_acento_e_barra_invertida_sobrevive():
    (mp3, _) = candidatos_das_respostas([RESPOSTA])
    assert mp3.nome_arquivo == "6. PRA VOCÊ VOLTAR.mp3"


@pytest.mark.parametrize("respostas", [[], None, [{}], [{"files": []}], [{"files": None}]])
def test_resposta_vazia_nao_explode(respostas):
    assert candidatos_das_respostas(respostas) == []


# --------------------------------------------------------------- estados


@pytest.mark.parametrize(
    "texto, esperado",
    [
        ("Completed, Succeeded", EstadoTransferencia.CONCLUIDA),
        ("Completed, Cancelled", EstadoTransferencia.CANCELADA),
        ("Completed, Errored", EstadoTransferencia.FALHOU),
        ("Completed, TimedOut", EstadoTransferencia.FALHOU),
        ("Completed, Rejected", EstadoTransferencia.FALHOU),
        ("InProgress", EstadoTransferencia.BAIXANDO),
        ("Queued, Remotely", EstadoTransferencia.NA_FILA),
        ("Requested", EstadoTransferencia.NA_FILA),
        ("", EstadoTransferencia.NA_FILA),
    ],
)
def test_traduz_o_estado_do_slskd(texto, esperado):
    assert traduzir_estado(texto) == esperado


def test_o_desfecho_ganha_do_completed():
    # "Completed, Succeeded" tem as duas palavras; o que vale é o desfecho.
    assert traduzir_estado("Completed, Succeeded") == EstadoTransferencia.CONCLUIDA


# ----------------------------------------------------------------- estado


def test_conectado_so_quando_logado_na_rede():
    for estado, esperado in (
        ("Connected, LoggedIn", True),
        ("Connected", False),  # de pé, mas não logado: não serve para buscar
        ("Disconnected", False),
        ("", False),
    ):
        transporte = TransporteFalso({"/application": {"server": {"state": estado}}})
        assert cliente(transporte).conectado() is esperado, estado


# ------------------------------------------------------------------ busca


def test_busca_completa_devolve_candidatos():
    chamadas = {"estado": 0}

    def transporte(metodo, caminho, corpo=None):
        if caminho.endswith("/responses"):
            return 200, [RESPOSTA]
        if caminho.startswith("/searches/"):
            chamadas["estado"] += 1
            return 200, {"isComplete": True}
        return 200, None

    assert len(cliente(transporte).buscar("tim maia voce")) == 2


def test_a_busca_manda_o_texto_certo():
    transporte = TransporteFalso()
    cliente(transporte).buscar("djavan nao vou ficar")

    (metodo, caminho, corpo) = transporte.chamadas[0]
    assert (metodo, caminho) == ("POST", "/searches")
    assert corpo["searchText"] == "djavan nao vou ficar"
    assert corpo["id"]


def test_a_busca_limpa_a_si_mesma_no_fim():
    # Buscas acumulam no slskd; sem o DELETE a lista cresce sem fim.
    transporte = TransporteFalso()
    cliente(transporte).buscar("x")
    assert any(c.startswith("/searches/") for c in transporte.caminhos("DELETE"))


def test_a_busca_limpa_a_si_mesma_mesmo_quando_da_erro():
    def transporte(metodo, caminho, corpo=None):
        if caminho.endswith("/responses"):
            raise ErroSlskd("caiu")
        return 200, {"isComplete": True}

    registradas = []

    def espiao(metodo, caminho, corpo=None):
        registradas.append((metodo, caminho))
        return transporte(metodo, caminho, corpo)

    with pytest.raises(ErroSlskd):
        cliente(espiao).buscar("x")

    assert any(m == "DELETE" for m, _ in registradas)


def test_a_busca_respeita_o_limitador():
    # O ponto mais importante deste módulo: estourar o limite = 30 min de banimento.
    limitador = LimitadorDeBuscas(limite=2, janela_s=100, relogio=lambda: 0.0, dormir=lambda s: None)
    transporte = TransporteFalso()
    c = cliente(transporte, limitador=limitador)

    c.buscar("a")
    c.buscar("b")

    assert limitador.usadas == 2
    assert not limitador.pode_buscar_agora


def test_busca_que_estoura_o_tempo_ainda_devolve_o_que_chegou():
    # Medido na rede: uma busca trouxe 252 respostas em 5s e terminou "TimedOut".
    # O resultado estava lá — desistir dele seria jogar fora busca boa.
    def transporte(metodo, caminho, corpo=None):
        if caminho.endswith("/responses"):
            return 200, [RESPOSTA]
        if caminho.startswith("/searches/"):
            return 200, {"isComplete": False, "state": "InProgress"}
        return 200, None

    assert len(cliente(transporte).buscar("x", espera_max_s=3)) == 2


# -------------------------------------------------------------- downloads


def test_enfileirar_manda_nome_e_tamanho():
    transporte = TransporteFalso()
    (candidato,) = candidatos_das_respostas([{**RESPOSTA, "files": [ARQUIVO_MP3]}])
    cliente(transporte).enfileirar(candidato)

    (metodo, caminho, corpo) = transporte.chamadas[0]
    assert metodo == "POST"
    assert caminho == "/transfers/downloads/Studio 560"
    assert corpo == [{"filename": ARQUIVO_MP3["filename"], "size": 5403074}]


def test_downloads_achata_usuario_pasta_arquivo():
    bruto = [
        {
            "username": "joao",
            "directories": [
                {
                    "files": [
                        {
                            "filename": "x\\a.mp3",
                            "size": 1000,
                            "bytesTransferred": 500,
                            "state": "InProgress",
                            "placeInQueue": 3,
                        },
                        {
                            "filename": "x\\b.flac",
                            "size": 2000,
                            "bytesTransferred": 2000,
                            "state": "Completed, Succeeded",
                        },
                    ]
                }
            ],
        }
    ]
    transferencias = cliente(TransporteFalso({"/transfers/downloads": bruto})).downloads()

    assert len(transferencias) == 2
    baixando, pronta = transferencias
    assert baixando.estado == EstadoTransferencia.BAIXANDO
    assert baixando.progresso == 0.5
    assert baixando.posicao_fila == 3
    assert pronta.estado == EstadoTransferencia.CONCLUIDA
    assert pronta.terminou


def test_downloads_vazio_nao_explode():
    assert cliente(TransporteFalso({"/transfers/downloads": []})).downloads() == []


def test_cancelar_monta_o_caminho_certo():
    transporte = TransporteFalso()
    cliente(transporte).cancelar("joao", "abc-123", remover=True)

    (metodo, caminho, _) = transporte.chamadas[0]
    assert metodo == "DELETE"
    assert caminho == "/transfers/downloads/joao/abc-123?remove=true"


# -------------------------------------------------------------- erros


@pytest.mark.parametrize("codigo", [401, 403])
def test_chave_recusada_explica_o_que_conferir(monkeypatch, codigo):
    import urllib.error

    import slskd_cliente

    def recusar(*_args, **_kwargs):
        raise urllib.error.HTTPError("url", codigo, "Unauthorized", {}, None)

    monkeypatch.setattr(slskd_cliente.urllib.request, "urlopen", recusar)

    with pytest.raises(ErroSlskd) as erro:
        ClienteSlskd(chave_api="errada")._http("GET", "/application")

    # A mensagem tem que dizer ONDE conferir, não só que deu errado.
    assert "slskd.yml" in str(erro.value)
    assert "readwrite" in str(erro.value)


def test_slskd_fora_do_ar_sugere_a_causa_provavel(monkeypatch):
    import urllib.error

    import slskd_cliente

    def recusar(*_args, **_kwargs):
        raise urllib.error.URLError("conexão recusada")

    monkeypatch.setattr(slskd_cliente.urllib.request, "urlopen", recusar)

    with pytest.raises(ErroSlskd) as erro:
        ClienteSlskd()._http("GET", "/application")

    assert "Ele está rodando?" in str(erro.value)


def test_outro_erro_http_diz_o_codigo_e_o_caminho(monkeypatch):
    import urllib.error

    import slskd_cliente

    def recusar(*_args, **_kwargs):
        raise urllib.error.HTTPError("url", 500, "Erro", {}, None)

    monkeypatch.setattr(slskd_cliente.urllib.request, "urlopen", recusar)

    with pytest.raises(ErroSlskd) as erro:
        ClienteSlskd()._http("GET", "/searches")

    assert "500" in str(erro.value)
    assert "/searches" in str(erro.value)
