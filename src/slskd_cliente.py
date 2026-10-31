"""Cliente da API REST do slskd — o motor de busca e download.

Escrito contra o que a API **devolve de verdade**, medido com buscas reais na rede, não
contra o que a documentação sugere. Três coisas que uma suposição teria errado:

* **`extension` vem sempre vazio.** Em toda resposta medida, de MP3 e de FLAC. A extensão
  tem que sair do `filename`.
* **`bitRate` só existe em arquivo com perda.** FLAC traz `bitDepth` e `sampleRate` e
  nenhum bitrate — o que é coerente, porque bitrate de FLAC não diz nada sobre qualidade.
* **`files` e `lockedFiles` são listas separadas.** Os travados são arquivos que o usuário
  tem mas **não compartilha com você**. Enfileirar um deles é download que nunca completa.

O transporte HTTP é injetável para os testes rodarem sem rede e sem slskd.

> **Por que não usar o pacote `slskd-api`:** são seis endpoints. Em troca de escrevê-los,
> ficamos sem mais uma dependência para instalar na outra máquina e para empacotar no
> `.exe`, com controle total sobre tempo-limite e sobre as mensagens de erro em português.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
import uuid
from typing import Any, Callable

from limitador import LimitadorDeBuscas
from modelos import Candidato, EstadoTransferencia, Transferencia

#: Estados de transferência do slskd mapeados para os nossos.
#: O slskd usa texto com vírgula ("Completed, Succeeded"), então a checagem é por trecho.
_ESTADOS = (
    ("Succeeded", EstadoTransferencia.CONCLUIDA),
    ("Cancelled", EstadoTransferencia.CANCELADA),
    ("Errored", EstadoTransferencia.FALHOU),
    ("TimedOut", EstadoTransferencia.FALHOU),
    ("Rejected", EstadoTransferencia.FALHOU),
    ("InProgress", EstadoTransferencia.BAIXANDO),
    ("Queued", EstadoTransferencia.NA_FILA),
    ("Requested", EstadoTransferencia.NA_FILA),
    ("Initializing", EstadoTransferencia.BAIXANDO),
)


class ErroSlskd(Exception):
    """Algo deu errado falando com o slskd. A mensagem é para aparecer na tela."""


def traduzir_estado(texto: str) -> EstadoTransferencia:
    """Converte o estado do slskd no nosso.

    A ordem importa: "Completed, Succeeded" contém as duas palavras, e o desfecho
    (Succeeded) é o que vale.
    """
    for trecho, estado in _ESTADOS:
        if trecho in (texto or ""):
            return estado
    return EstadoTransferencia.NA_FILA


def _candidato_de(resposta: dict, arquivo: dict) -> Candidato:
    """Junta os dados do usuário e do arquivo num `Candidato`.

    `queueLength` é o tamanho da fila **daquele usuário**, não a nossa posição nela — mas
    para ranquear é o que interessa: fila de 677 é fila que não anda.
    """
    return Candidato(
        usuario=resposta.get("username", ""),
        caminho=arquivo.get("filename", ""),
        tamanho_bytes=int(arquivo.get("size") or 0),
        duracao_s=float(arquivo["length"]) if arquivo.get("length") else None,
        bitrate_kbps=arquivo.get("bitRate"),
        taxa_amostragem_hz=arquivo.get("sampleRate"),
        profundidade_bits=arquivo.get("bitDepth"),
        slot_livre=bool(resposta.get("hasFreeUploadSlot")),
        posicao_fila=resposta.get("queueLength"),
        velocidade_bps=resposta.get("uploadSpeed"),
    )


def candidatos_das_respostas(respostas: list[dict]) -> list[Candidato]:
    """Achata as respostas em candidatos, **ignorando os arquivos travados**."""
    candidatos = []
    for resposta in respostas or []:
        for arquivo in resposta.get("files") or []:
            if arquivo.get("isLocked"):
                continue
            candidatos.append(_candidato_de(resposta, arquivo))
    return candidatos


class ClienteSlskd:
    """Conversa com o slskd por HTTP."""

    def __init__(
        self,
        url: str = "http://localhost:5030",
        chave_api: str = "",
        limitador: LimitadorDeBuscas | None = None,
        transporte: Callable[..., tuple[int, Any]] | None = None,
        dormir: Callable[[float], None] = time.sleep,
        tempo_limite_s: float = 30.0,
    ):
        self.base = f"{url.rstrip('/')}/api/v0"
        self.chave_api = chave_api
        self.limitador = limitador or LimitadorDeBuscas()
        self._transporte = transporte or self._http
        self._dormir = dormir
        self.tempo_limite_s = tempo_limite_s

    # ------------------------------------------------------------- transporte

    def _http(self, metodo: str, caminho: str, corpo: Any = None) -> tuple[int, Any]:
        dados = json.dumps(corpo).encode("utf-8") if corpo is not None else None
        cabecalhos = {"X-API-Key": self.chave_api}
        if dados:
            cabecalhos["Content-Type"] = "application/json"

        pedido = urllib.request.Request(
            f"{self.base}{caminho}", data=dados, headers=cabecalhos, method=metodo
        )
        try:
            with urllib.request.urlopen(pedido, timeout=self.tempo_limite_s) as resposta:
                bruto = resposta.read().decode("utf-8")
                return resposta.status, (json.loads(bruto) if bruto.strip() else None)
        except urllib.error.HTTPError as erro:
            if erro.code in (401, 403):
                raise ErroSlskd(
                    "O slskd recusou a chave de API. Confira se a chave do app é a mesma "
                    "que está no slskd.yml, e se o papel dela é 'readwrite'."
                ) from erro
            raise ErroSlskd(f"O slskd respondeu HTTP {erro.code} em {caminho}.") from erro
        except urllib.error.URLError as erro:
            raise ErroSlskd(
                f"Não consegui falar com o slskd em {self.base}. Ele está rodando? "
                f"({erro.reason})"
            ) from erro

    def _chamar(self, metodo: str, caminho: str, corpo: Any = None) -> Any:
        _, dados = self._transporte(metodo, caminho, corpo)
        return dados

    # ------------------------------------------------------------- aplicação

    def estado(self) -> dict:
        return self._chamar("GET", "/application") or {}

    def conectado(self) -> bool:
        """True quando o slskd está logado na rede Soulseek — não só de pé."""
        estado = (self.estado().get("server") or {}).get("state") or ""
        return "Connected" in estado and "LoggedIn" in estado

    def usuario_logado(self) -> str:
        return (self.estado().get("server") or {}).get("username") or ""

    # ----------------------------------------------------------------- busca

    def buscar(self, texto: str, espera_max_s: float = 25.0) -> list[Candidato]:
        """Faz uma busca completa e devolve os candidatos aproveitáveis.

        **Respeita o limitador**: se a cota da janela acabou, espera. É por isso que esta
        chamada pode demorar minutos em vez de segundos — e é de propósito, porque a
        alternativa é meia hora de banimento.
        """
        self.limitador.aguardar_vez()

        busca_id = str(uuid.uuid4())
        self._chamar("POST", "/searches", {"id": busca_id, "searchText": texto})
        try:
            self._esperar_terminar(busca_id, espera_max_s)
            respostas = self._chamar("GET", f"/searches/{busca_id}/responses") or []
            return candidatos_das_respostas(respostas)
        finally:
            # Buscas acumulam no slskd; limpar evita a lista crescer sem fim.
            try:
                self._chamar("DELETE", f"/searches/{busca_id}")
            except ErroSlskd:
                pass

    def _esperar_terminar(self, busca_id: str, espera_max_s: float) -> dict:
        """Fica consultando até a busca acabar ou o tempo estourar.

        Estourar o tempo **não é erro**: o que já chegou vale. Nas medições, uma busca
        trouxe 252 respostas em 5 segundos e ainda assim terminou como "TimedOut" —
        o resultado estava lá.
        """
        passo = 1.0
        gasto = 0.0
        estado: dict = {}
        while gasto < espera_max_s:
            estado = self._chamar("GET", f"/searches/{busca_id}") or {}
            if estado.get("isComplete"):
                return estado
            self._dormir(passo)
            gasto += passo
        return estado

    # ------------------------------------------------------------- downloads

    def enfileirar(self, candidato: Candidato) -> bool:
        """Põe um arquivo na fila de download."""
        corpo = [{"filename": candidato.caminho, "size": candidato.tamanho_bytes}]
        self._chamar("POST", f"/transfers/downloads/{candidato.usuario}", corpo)
        return True

    def downloads(self) -> list[Transferencia]:
        """Tudo que está baixando ou já baixou, convertido para o nosso modelo."""
        bruto = self._chamar("GET", "/transfers/downloads") or []
        transferencias = []
        for usuario in bruto:
            nome = usuario.get("username", "")
            for diretorio in usuario.get("directories") or []:
                for arquivo in diretorio.get("files") or []:
                    transferencias.append(self._transferencia_de(nome, arquivo))
        return transferencias

    @staticmethod
    def _transferencia_de(usuario: str, arquivo: dict) -> Transferencia:
        candidato = Candidato(
            usuario=usuario,
            caminho=arquivo.get("filename", ""),
            tamanho_bytes=int(arquivo.get("size") or 0),
        )
        return Transferencia(
            candidato=candidato,
            estado=traduzir_estado(arquivo.get("state", "")),
            bytes_transferidos=int(arquivo.get("bytesTransferred") or 0),
            posicao_fila=arquivo.get("placeInQueue"),
            erro=arquivo.get("exception") or "",
        )

    def cancelar(self, usuario: str, id_transferencia: str, remover: bool = False) -> bool:
        caminho = f"/transfers/downloads/{usuario}/{id_transferencia}"
        if remover:
            caminho += "?remove=true"
        self._chamar("DELETE", caminho)
        return True
