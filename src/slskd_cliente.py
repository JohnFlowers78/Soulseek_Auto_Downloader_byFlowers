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
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Any, Callable

import sistema
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


def _corpo_do_erro(erro: urllib.error.HTTPError) -> str:
    """Lê o corpo de uma resposta de erro, sem deixar a leitura virar outro erro."""
    try:
        return (erro.read() or b"").decode("utf-8", "replace").strip()[:300]
    except Exception:  # noqa: BLE001
        return ""


def _na_url(texto: str) -> str:
    """Codifica um pedaço de caminho de URL.

    Nome de usuário do Soulseek é texto livre: ``Paul Kersey's Gun`` tem espaço e
    apóstrofo, e foi assim que um download real falhou com *URL can't contain control
    characters*. Nada que venha da rede entra numa URL sem passar por aqui.
    """
    return urllib.parse.quote(texto, safe="")


def ler_chave_do_yml(caminho: Path | None = None) -> str:
    """Pega a chave de API direto do `slskd.yml`.

    A chave estava sendo guardada em **dois** lugares — no `slskd.yml` e no nosso
    `config.json` — e duas cópias da mesma verdade sempre acabam divergindo. Aqui elas
    viram uma: o `slskd.yml` é o dono, e o app lê de lá quando o campo está vazio.

    Leitura por linha em vez de um analisador de YAML de verdade: é uma chave só, e
    somar uma dependência (e um item a empacotar no `.exe`) para ler uma linha não paga.
    O formato é o que o nosso próprio gerador escreve.
    """
    if caminho is None:
        executavel = sistema.encontrar_slskd()
        candidatos = []
        if executavel:
            candidatos.append(executavel.parent / "dados" / "slskd.yml")
        candidatos.append(sistema.pasta_de_dados_do_slskd() / "slskd.yml")
        caminho = next((c for c in candidatos if c.is_file()), None)
    if caminho is None or not Path(caminho).is_file():
        return ""

    try:
        linhas = Path(caminho).read_text(encoding="utf-8").splitlines()
    except OSError:
        return ""

    dentro_das_chaves = False
    for linha in linhas:
        sem_comentario = linha.split("#", 1)[0]
        limpa = sem_comentario.strip()
        if limpa.startswith("api_keys:"):
            dentro_das_chaves = True
            continue
        if dentro_das_chaves and limpa.startswith("key:"):
            return limpa.split(":", 1)[1].strip().strip("'\"")
        # Saiu do bloco: uma linha sem recuo que não está em branco.
        if dentro_das_chaves and sem_comentario and not sem_comentario[0].isspace():
            break
    return ""


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
        # Campo vazio? A chave mora no slskd.yml — não há motivo para o usuário copiar
        # e colar um segredo de um arquivo para outro.
        self.chave_api = chave_api or ler_chave_do_yml()
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
            # O corpo da resposta entra na mensagem. Sem ele, um HTTP 500 vira "deu
            # erro" e não há o que investigar — foi o que aconteceu num download real.
            #
            # Lido UMA vez só: é um fluxo, e a segunda leitura volta vazia. Chamar duas
            # vezes dentro da mesma expressão fazia a mensagem sair sempre sem o corpo.
            disse = _corpo_do_erro(erro)
            raise ErroSlskd(
                f"O slskd respondeu HTTP {erro.code} em {caminho}."
                + (f" Disse: {disse}" if disse else "")
            ) from erro
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

        busca_id = self._abrir_busca(texto)
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

    def _abrir_busca(self, texto: str, tentativas: int = 3) -> str:
        """Abre a busca no slskd, insistindo quando ele responde 409.

        O 409 apareceu numa playlist de verdade e **derrubou a corrida inteira na quarta
        faixa**. Ele significa conflito — na prática, o slskd ainda está ocupado com
        busca anterior. Não é erro permanente: esperar e repetir resolve.

        A cota do limitador **não** é consumida de novo: uma busca recusada não chegou
        a ser feita, e descontá-la encurtaria o ritmo sem motivo.
        """
        ultimo_erro: ErroSlskd | None = None
        for tentativa in range(tentativas):
            busca_id = str(uuid.uuid4())
            try:
                self._chamar("POST", "/searches", {"id": busca_id, "searchText": texto})
                return busca_id
            except ErroSlskd as erro:
                if "HTTP 409" not in str(erro):
                    raise
                ultimo_erro = erro
                self._limpar_buscas_terminadas()
                self._dormir(3.0 * (tentativa + 1))
        raise ultimo_erro or ErroSlskd("Não consegui abrir a busca no slskd.")

    def _limpar_buscas_terminadas(self) -> None:
        """Apaga do slskd as buscas que já acabaram.

        Buscas acumulam, e acumulada demais é a explicação mais provável do 409. Falhar
        aqui não importa: é faxina, não o trabalho.
        """
        try:
            for busca in self._chamar("GET", "/searches") or []:
                if busca.get("isComplete") and busca.get("id"):
                    self._chamar("DELETE", f"/searches/{busca['id']}")
        except (ErroSlskd, AttributeError, TypeError):
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
        self._chamar("POST", f"/transfers/downloads/{_na_url(candidato.usuario)}", corpo)
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
        caminho = f"/transfers/downloads/{_na_url(usuario)}/{_na_url(id_transferencia)}"
        if remover:
            caminho += "?remove=true"
        self._chamar("DELETE", caminho)
        return True
