"""Lê uma playlist do Spotify pela API oficial.

Usa **Authorization Code com PKCE**. A consequência prática é boa: o fluxo não precisa
do *Client Secret* — só do *Client ID*, que é público por desenho. Um segredo a menos
para o usuário copiar, colar, guardar e eventualmente vazar.

> **O limite que define o desenho:** desde fevereiro de 2026 a API só entrega o
> **conteúdo** das playlists **do próprio usuário logado**. Playlist de terceiro devolve
> metadados e nada de faixas — e por isso existe o caminho alternativo pelo navegador.

O transporte HTTP é injetável para os testes não tocarem a rede.
"""

from __future__ import annotations

import base64
import hashlib
import http.server
import json
import re
import secrets
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from typing import Any, Callable

from modelos import Faixa

URL_AUTORIZACAO = "https://accounts.spotify.com/authorize"
URL_TOKEN = "https://accounts.spotify.com/api/token"
API = "https://api.spotify.com/v1"

#: Só leitura de playlist. Pedir menos do que se usa é o jeito certo de pedir acesso.
ESCOPOS = "playlist-read-private playlist-read-collaborative"

#: Tem que bater **exatamente** com o cadastrado no painel do Spotify. Use o endereço
#: numérico: o Spotify exige HTTPS para nomes e só abre exceção para o loopback — e
#: `localhost` não conta como loopback para essa regra.
REDIRECIONAMENTO = "http://127.0.0.1:8888/callback"


class ErroSpotify(Exception):
    """Algo deu errado com o Spotify. A mensagem é para aparecer na tela."""


# ---------------------------------------------------------------------------
# Links
# ---------------------------------------------------------------------------

_RE_PLAYLIST = re.compile(r"(?:playlist[/:])([A-Za-z0-9]{22})")
_RE_FAIXA = re.compile(r"(?:track[/:])([A-Za-z0-9]{22})")
_RE_ID_SOLTO = re.compile(r"^[A-Za-z0-9]{22}$")


def extrair_id_da_playlist(texto: str) -> str | None:
    """Aceita link do navegador, URI `spotify:` ou o id cru."""
    texto = (texto or "").strip()
    achado = _RE_PLAYLIST.search(texto)
    if achado:
        return achado.group(1)
    return texto if _RE_ID_SOLTO.match(texto) else None


def extrair_id_da_faixa(texto: str) -> str | None:
    achado = _RE_FAIXA.search((texto or "").strip())
    return achado.group(1) if achado else None


# ---------------------------------------------------------------------------
# PKCE
# ---------------------------------------------------------------------------


def gerar_verificador() -> str:
    """O segredo efêmero do PKCE: 43 a 128 caracteres, só desta autorização."""
    return secrets.token_urlsafe(64)[:128]


def desafio_de(verificador: str) -> str:
    """O que vai na URL: o SHA-256 do verificador, em base64url sem preenchimento.

    O verificador em si **nunca** trafega na primeira ida. É isso que impede quem
    interceptar o código de autorização de trocá-lo por um token.
    """
    digerido = hashlib.sha256(verificador.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digerido).decode("ascii").rstrip("=")


def montar_url_de_autorizacao(client_id: str, verificador: str, estado: str = "") -> str:
    parametros = {
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": REDIRECIONAMENTO,
        "scope": ESCOPOS,
        "code_challenge_method": "S256",
        "code_challenge": desafio_de(verificador),
    }
    if estado:
        parametros["state"] = estado
    return f"{URL_AUTORIZACAO}?{urllib.parse.urlencode(parametros)}"


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------


def _http(metodo: str, url: str, cabecalhos: dict, corpo: bytes | None = None) -> Any:
    pedido = urllib.request.Request(url, data=corpo, headers=cabecalhos, method=metodo)
    try:
        with urllib.request.urlopen(pedido, timeout=30) as resposta:
            bruto = resposta.read().decode("utf-8")
            return json.loads(bruto) if bruto.strip() else None
    except urllib.error.HTTPError as erro:
        detalhe = ""
        try:
            detalhe = erro.read().decode("utf-8")[:300]
        except Exception:  # noqa: BLE001
            pass
        if erro.code == 401:
            raise ErroSpotify("O Spotify recusou o acesso — entre de novo.") from erro
        if erro.code == 403:
            raise ErroSpotify(
                "O Spotify recusou (403). Desde fev/2026 a API só entrega o conteúdo das "
                "playlists do próprio usuário logado — se esta não é sua, marque a opção "
                "de ler pelo navegador."
            ) from erro
        if erro.code == 404:
            raise ErroSpotify("Playlist não encontrada. O link está certo?") from erro
        if erro.code == 429:
            raise ErroSpotify("O Spotify pediu para esperar (429). Tente em alguns minutos.") from erro
        raise ErroSpotify(f"O Spotify respondeu HTTP {erro.code}. {detalhe}") from erro
    except urllib.error.URLError as erro:
        raise ErroSpotify(f"Não consegui falar com o Spotify ({erro.reason}).") from erro


def trocar_codigo_por_token(client_id: str, codigo: str, verificador: str, http=_http) -> dict:
    """Primeira troca: o código que voltou no navegador vira token de acesso."""
    corpo = urllib.parse.urlencode(
        {
            "grant_type": "authorization_code",
            "code": codigo,
            "redirect_uri": REDIRECIONAMENTO,
            "client_id": client_id,
            "code_verifier": verificador,
        }
    ).encode("ascii")
    return http(
        "POST", URL_TOKEN, {"Content-Type": "application/x-www-form-urlencoded"}, corpo
    ) or {}


def renovar_token(client_id: str, refresh_token: str, http=_http) -> dict:
    """Troca o refresh token por um acesso novo.

    O Spotify **às vezes devolve um refresh token novo** nesta resposta, e às vezes não.
    Quem chama tem que guardar o novo quando vier, senão a sessão morre sem explicação
    depois de algumas semanas.
    """
    corpo = urllib.parse.urlencode(
        {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": client_id,
        }
    ).encode("ascii")
    return http(
        "POST", URL_TOKEN, {"Content-Type": "application/x-www-form-urlencoded"}, corpo
    ) or {}


# ---------------------------------------------------------------------------
# A dança do navegador
# ---------------------------------------------------------------------------

_PAGINA_OK = """<!doctype html><meta charset="utf-8">
<title>Pronto</title>
<body style="font-family:system-ui;background:#121212;color:#eee;text-align:center;padding:4rem">
<h1>✅ Autorizado</h1>
<p>Pode fechar esta aba e voltar para o terminal.</p>
</body>"""

_PAGINA_ERRO = """<!doctype html><meta charset="utf-8">
<title>Não deu</title>
<body style="font-family:system-ui;background:#121212;color:#eee;text-align:center;padding:4rem">
<h1>❌ Não autorizado</h1>
<p>Volte ao terminal para ver o motivo.</p>
</body>"""


class _Coletor(http.server.BaseHTTPRequestHandler):
    """Atende **uma** requisição: a que o Spotify manda de volta com o código."""

    recebido: dict = {}

    def do_GET(self) -> None:  # noqa: N802 — nome exigido pela biblioteca
        partes = urllib.parse.urlparse(self.path)
        parametros = {k: v[0] for k, v in urllib.parse.parse_qs(partes.query).items()}
        type(self).recebido = parametros

        deu_certo = "code" in parametros
        corpo = (_PAGINA_OK if deu_certo else _PAGINA_ERRO).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)

    def log_message(self, *_args) -> None:
        """Silencia o log do servidor — ele sujaria a saída do nosso comando."""


def autorizar_no_navegador(
    client_id: str,
    abrir=webbrowser.open,
    porta: int = 8888,
    espera_max_s: float = 300.0,
    avisar=print,
) -> dict:
    """Abre o navegador, espera a autorização e troca o código por tokens.

    Devolve o que o Spotify respondeu: `access_token`, `refresh_token`, `expires_in`.

    O `state` é conferido na volta. Sem isso, qualquer página aberta no navegador
    poderia chamar o nosso endereço local com um código próprio e ligar a conta dela
    à sua sessão.
    """
    if not client_id.strip():
        raise ErroSpotify("Falta o Client ID do Spotify nas Configurações.")

    verificador = gerar_verificador()
    estado = secrets.token_urlsafe(16)
    url = montar_url_de_autorizacao(client_id, verificador, estado)

    _Coletor.recebido = {}
    try:
        servidor = http.server.HTTPServer(("127.0.0.1", porta), _Coletor)
    except OSError as erro:
        raise ErroSpotify(
            f"Não consegui escutar em 127.0.0.1:{porta} ({erro}). "
            "Alguma coisa já está usando essa porta?"
        ) from erro

    servidor.timeout = espera_max_s
    try:
        avisar(f"Abrindo o navegador para você autorizar...\n\nSe não abrir, use este link:\n{url}\n")
        abrir(url)
        servidor.handle_request()
    finally:
        servidor.server_close()

    recebido = _Coletor.recebido
    if not recebido:
        raise ErroSpotify(f"Ninguém voltou do navegador em {espera_max_s:.0f}s.")
    if recebido.get("error"):
        raise ErroSpotify(f"Você (ou o Spotify) recusou: {recebido['error']}")
    if recebido.get("state") != estado:
        raise ErroSpotify(
            "O 'state' que voltou não é o que eu mandei. Por segurança, não vou "
            "continuar — tente de novo."
        )
    if not recebido.get("code"):
        raise ErroSpotify("O Spotify não mandou o código de autorização.")

    tokens = trocar_codigo_por_token(client_id, recebido["code"], verificador)
    if not tokens.get("access_token"):
        raise ErroSpotify(f"A troca pelo token falhou: {tokens}")
    return tokens


# ---------------------------------------------------------------------------
# Leitura
# ---------------------------------------------------------------------------


def lista_de_itens(corpo: Any) -> list[dict]:
    """Acha a lista de itens dentro do que a API devolveu, nas formas que ela usa.

    Medido ao vivo: `GET /playlists/{id}` traz **`items` como objeto de paginação**
    (`href, items, limit, next, offset, previous, total`), com a lista de verdade
    aninhada lá dentro. A forma antiga chamava esse objeto de `tracks`, e um endpoint
    de página devolve o objeto de paginação direto.

    Em vez de escolher uma e torcer — foi assim que errei duas vezes aqui —, esta
    função aceita as três.
    """
    if not isinstance(corpo, dict):
        return []

    for chave in ("items", "tracks"):
        valor = corpo.get(chave)
        if isinstance(valor, list):
            return [i for i in valor if isinstance(i, dict)]
        if isinstance(valor, dict) and isinstance(valor.get("items"), list):
            return [i for i in valor["items"] if isinstance(i, dict)]
    return []


def proxima_pagina(corpo: Any) -> str:
    """O endereço da próxima página, venha ele na raiz ou dentro da paginação."""
    if not isinstance(corpo, dict):
        return ""
    if isinstance(corpo.get("next"), str):
        return corpo["next"]
    for chave in ("items", "tracks"):
        valor = corpo.get(chave)
        if isinstance(valor, dict) and isinstance(valor.get("next"), str):
            return valor["next"]
    return ""


def faixa_do_item(item: dict) -> Faixa | None:
    """Converte um item da playlist em `Faixa`. `None` para o que não é música.

    Playlist tem lixo previsível: faixa removida do catálogo vira nulo, e episódio de
    podcast vem com `type: "episode"`. Os dois chegam como item normal.

    A faixa vem em `track` (forma antiga) ou em `item` (a renomeação de fev/2026).
    Aceitar as duas custa uma linha e evita a terceira rodada de adivinhação.
    """
    bruto = item or {}
    faixa = bruto.get("track") or bruto.get("item") or {}
    if not isinstance(faixa, dict):
        return None
    if not faixa or faixa.get("type") == "episode":
        return None

    titulo = (faixa.get("name") or "").strip()
    if not titulo:
        return None

    artistas = [a.get("name", "").strip() for a in faixa.get("artists") or []]

    return Faixa(
        artista=", ".join(a for a in artistas if a),
        titulo=titulo,
        album=((faixa.get("album") or {}).get("name") or "").strip(),
        duracao_s=_duracao_em_segundos(faixa),
        isrc=((faixa.get("external_ids") or {}).get("isrc") or "").strip(),
    )


def _duracao_em_segundos(faixa: dict) -> float | None:
    """A duração da faixa, aceitando os nomes de campo que a API já usou.

    Sem duração, o filtro que compara o tamanho da gravação fica **desligado** — e é
    ele que separa a faixa certa de um remix, de uma versão ao vivo ou de uma
    sinfonia de doze minutos com o mesmo nome no caminho. Vale tentar mais de um nome
    antes de desistir dela.
    """
    for chave in ("duration_ms", "durationMs"):
        valor = faixa.get(chave)
        if isinstance(valor, (int, float)) and valor > 0:
            return valor / 1000
    valor = faixa.get("duration")
    if isinstance(valor, (int, float)) and valor > 0:
        # Alguns formatos trazem segundos aqui; acima de 1000 só pode ser milissegundo
        # (nenhuma faixa de música tem 16 minutos por acidente de unidade).
        return valor / 1000 if valor > 1000 else float(valor)
    return None


def acesso_a_partir_do_refresh(
    client_id: str, refresh_token: str, http=_http
) -> tuple[str, str]:
    """Devolve `(token de acesso, refresh token a guardar)`.

    O segundo valor existe porque o Spotify **às vezes** devolve um refresh token novo
    nesta troca e às vezes repete o antigo. Guardar sempre o que volta — ou o antigo,
    quando não vier nada — é o que impede a sessão de morrer sem explicação semanas
    depois.
    """
    if not refresh_token:
        raise ErroSpotify("Você ainda não entrou na sua conta. Rode: python entrar_spotify.py")

    resposta = renovar_token(client_id, refresh_token, http)
    acesso = resposta.get("access_token")
    if not acesso:
        raise ErroSpotify(
            "Não consegui renovar o acesso ao Spotify. Entre de novo: "
            "python entrar_spotify.py"
        )
    return acesso, (resposta.get("refresh_token") or refresh_token)


class LeitorSpotify:
    def __init__(self, token_de_acesso: str, http: Callable[..., Any] = _http):
        self.token = token_de_acesso
        self._http = http
        #: Qual endereço de faixas respondeu — útil no diagnóstico e para saber quando
        #: dá para parar de tentar os dois.
        self.caminho_que_funcionou = ""

    def _get(self, url: str) -> dict:
        return self._http("GET", url, {"Authorization": f"Bearer {self.token}"}) or {}

    def nome_da_playlist(self, id_playlist: str) -> str:
        dados = self._get(f"{API}/playlists/{id_playlist}?fields=name")
        return (dados.get("name") or "").strip() or "Playlist sem nome"

    #: Os dois nomes que o endereço das faixas já teve, na ordem em que vale tentar.
    #:
    #: Eu tinha cravado `items` sozinho, a partir de uma leitura de que `tracks` fora
    #: aposentado. Na prática, `items` respondeu 200 e **não trouxe faixa nenhuma** numa
    #: playlist com 14 — enquanto o nome da playlist vinha certo pelo outro endereço.
    #: Em vez de trocar um palpite por outro, o código tenta os dois e usa o que
    #: responder. Custa uma chamada a mais só quando o primeiro falha.
    CAMINHOS_DAS_FAIXAS = ("tracks", "items")

    def faixas_da_playlist(self, id_playlist: str, limite_paginas: int = 100) -> list[Faixa]:
        """Lê todas as faixas, seguindo a paginação.

        Começa pela **própria playlist**, e não por um sub-endereço: medido ao vivo,
        `GET /playlists/{id}` já traz a primeira página das faixas embutida. Uma chamada
        a menos, e é o caminho que comprovadamente responde nesta conta. Os
        sub-endereços ficam como reserva.
        """
        base = f"{API}/playlists/{id_playlist}"
        for rotulo, url in (
            ("playlist", base),
            ("tracks", f"{base}/tracks?limit=100"),
            ("items", f"{base}/items?limit=100"),
        ):
            try:
                faixas = self._ler_paginas(url, limite_paginas)
            except ErroSpotify:
                continue  # este endereço não serve; tenta o próximo
            if faixas:
                self.caminho_que_funcionou = rotulo
                return faixas
        return []

    def _ler_paginas(self, url: str, limite_paginas: int) -> list[Faixa]:
        """Segue o `next` até acabar. `limite_paginas` protege de um `next` circular."""
        faixas: list[Faixa] = []
        vistos = 0
        while url and vistos < limite_paginas:
            pagina = self._get(url)
            for item in lista_de_itens(pagina):
                faixa = faixa_do_item(item)
                if faixa:
                    faixas.append(faixa)
            url = proxima_pagina(pagina)
            vistos += 1
        return faixas

    def ler(self, link_ou_id: str) -> tuple[str, list[Faixa]]:
        """Devolve `(nome da playlist, faixas)`."""
        id_playlist = extrair_id_da_playlist(link_ou_id)
        if not id_playlist:
            raise ErroSpotify(
                "Não reconheci esse link de playlist. Espero algo como "
                "https://open.spotify.com/playlist/<id>"
            )
        return self.nome_da_playlist(id_playlist), self.faixas_da_playlist(id_playlist)
