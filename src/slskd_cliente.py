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

import errno
import http.client
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


class SemRedeSoulseek(ErroSlskd):
    """O motor está de pé, mas **fora da rede Soulseek**.

    É um erro completamente diferente dos outros, e confundir os dois custou uma
    playlist inteira. O slskd responde **HTTP 409** nos dois casos:

    * ocupado com uma busca anterior → esperar 3 segundos e repetir resolve;
    * desconectado do servidor Soulseek → repetir é inútil, e **toda** busca feita
      nesse estado volta vazia.

    Só o corpo da resposta distingue. Sem distinguir, o app tratou "fora da rede" como
    "ocupado": insistiu três vezes por faixa, desistiu, e marcou 14 faixas seguidas como
    "não vieram" — quando a verdade é que nenhuma delas chegou a ser procurada.
    """


#: Como o slskd diz, no corpo do 409, que não está na rede. A frase vem da biblioteca
#: Soulseek.NET (`SoulseekClient.SearchAsync`), não do slskd, e por isso é estável.
_FORA_DA_REDE = "must be connected and logged in"


#: Códigos de erro de socket que querem dizer "o sistema está sem fôlego, espere".
#: 10055 é o WSAENOBUFS do Windows — sem espaço de buffer ou fila cheia. Ele apareceu
#: numa playlist de 425 faixas e derrubou a corrida pela metade.
_SEM_FOLEGO = {10055, 10048, 10051, 10052, 10053, 10054, 10060, errno.ENOBUFS}


class _ConexaoViva:
    """Uma conexão HTTP mantida aberta entre as chamadas.

    Existe por causa de um erro real: `WinError 10055 — o sistema não tinha espaço
    suficiente no buffer`. Cada chamada abria um socket novo; numa playlist de 425
    faixas isso vira dezenas de milhares de conexões em `TIME_WAIT`, até o Windows
    ficar sem portas efêmeras e **parar de conectar em qualquer coisa**.

    Reaproveitar a conexão resolve na origem. Quando ela cai — e cai, por tempo ocioso
    ou pelo outro lado —, reconecta e tenta de novo **uma** vez: a falha é esperada,
    não excepcional.
    """

    def __init__(self, base: str, tempo_limite_s: float):
        partes = urllib.parse.urlsplit(base)
        self.host = partes.hostname or "localhost"
        self.porta = partes.port or (443 if partes.scheme == "https" else 80)
        self.https = partes.scheme == "https"
        self.prefixo = partes.path.rstrip("/")
        self.tempo_limite_s = tempo_limite_s
        self._conexao: http.client.HTTPConnection | None = None

    def _abrir(self) -> http.client.HTTPConnection:
        if self._conexao is None:
            classe = http.client.HTTPSConnection if self.https else http.client.HTTPConnection
            self._conexao = classe(self.host, self.porta, timeout=self.tempo_limite_s)
        return self._conexao

    def fechar(self) -> None:
        if self._conexao is not None:
            try:
                self._conexao.close()
            except Exception:  # noqa: BLE001 — fechar não pode falhar o chamador
                pass
            self._conexao = None

    def pedir(self, metodo: str, caminho: str, corpo: bytes | None, cabecalhos: dict):
        """Devolve `(status, bytes)`. Reconecta uma vez se a conexão tiver morrido."""
        for tentativa in (1, 2):
            try:
                conexao = self._abrir()
                conexao.request(metodo, f"{self.prefixo}{caminho}", body=corpo, headers=cabecalhos)
                resposta = conexao.getresponse()
                dados = resposta.read()  # precisa ser lido todo para a conexão servir de novo
                return resposta.status, dados
            except (http.client.HTTPException, OSError) as erro:
                self.fechar()
                sem_folego = isinstance(erro, OSError) and (
                    getattr(erro, "winerror", None) in _SEM_FOLEGO or erro.errno in _SEM_FOLEGO
                )
                if tentativa == 2 or sem_folego:
                    raise
        raise RuntimeError("inalcançável")


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
        tentativas_sem_folego: int = 4,
        espera_sem_folego_s: float = 5.0,
    ):
        self.base = f"{url.rstrip('/')}/api/v0"
        # Campo vazio? A chave mora no slskd.yml — não há motivo para o usuário copiar
        # e colar um segredo de um arquivo para outro.
        self.chave_api = chave_api or ler_chave_do_yml()
        self.limitador = limitador or LimitadorDeBuscas()
        self._transporte = transporte or self._http
        self._dormir = dormir
        self.tempo_limite_s = tempo_limite_s
        self.tentativas_sem_folego = tentativas_sem_folego
        self.espera_sem_folego_s = espera_sem_folego_s
        self._conexao = _ConexaoViva(self.base, tempo_limite_s)
        #: Buscas que estouraram o tempo e não puderam ser apagadas na hora.
        self._deixadas_para_tras = 0
        #: A última busca chegou ao fim? Vazio sem ter terminado não é "não existe".
        self.ultima_busca_terminou = True

    #: De quantas em quantas buscas deixadas para trás vale rodar a faxina.
    FAXINA_A_CADA = 10

    def fechar(self) -> None:
        """Encerra a conexão. Chamar ao terminar — sobretudo em corridas longas."""
        self._conexao.fechar()

    def __enter__(self) -> "ClienteSlskd":
        return self

    def __exit__(self, *_erro) -> None:
        self.fechar()

    # ------------------------------------------------------------- transporte

    def _http(self, metodo: str, caminho: str, corpo: Any = None) -> tuple[int, Any]:
        dados = json.dumps(corpo).encode("utf-8") if corpo is not None else None
        cabecalhos = {"X-API-Key": self.chave_api, "Accept": "application/json"}
        if dados:
            cabecalhos["Content-Type"] = "application/json"

        for tentativa in range(self.tentativas_sem_folego):
            try:
                status, bruto = self._conexao.pedir(metodo, caminho, dados, cabecalhos)
                break
            except OSError as erro:
                codigo = getattr(erro, "winerror", None) or erro.errno
                if codigo not in _SEM_FOLEGO or tentativa == self.tentativas_sem_folego - 1:
                    raise ErroSlskd(
                        f"Não consegui falar com o slskd em {self.base}. "
                        f"Ele está rodando? ({erro})"
                    ) from erro
                # Sem fôlego de socket: o sistema precisa de tempo para liberar portas.
                # Insistir na hora só piora; esperar resolve.
                self._conexao.fechar()
                self._dormir(self.espera_sem_folego_s * (tentativa + 1))
        else:  # pragma: no cover - o laço sempre sai pelo break ou pelo raise
            raise ErroSlskd("Não consegui falar com o slskd.")

        texto = bruto.decode("utf-8", "replace").strip()

        if status in (401, 403):
            raise ErroSlskd(
                "O slskd recusou a chave de API. Confira se a chave do app é a mesma "
                "que está no slskd.yml, e se o papel dela é 'readwrite'."
            )
        if status >= 400:
            # O corpo da resposta entra na mensagem. Sem ele, um HTTP 500 vira "deu
            # erro" e não há o que investigar — foi o que aconteceu num download real.
            recado = f"O slskd respondeu HTTP {status} em {caminho}." + (
                f" Disse: {texto[:300]}" if texto else ""
            )
            # Ler o CORPO é o que separa "ocupado" de "fora da rede". Os dois são 409.
            if _FORA_DA_REDE in texto:
                raise SemRedeSoulseek(
                    "O motor está de pé, mas saiu da rede Soulseek — nenhuma busca "
                    f"funciona enquanto ele não voltar. ({recado})"
                )
            raise ErroSlskd(recado)

        return status, (json.loads(texto) if texto else None)

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

    def esperar_rede(self, espera_max_s: float = 180.0, passo_s: float = 5.0) -> bool:
        """Espera o motor voltar para a rede Soulseek. Devolve se voltou.

        O slskd reconecta sozinho na maioria das quedas — o log do usuário mostra várias
        reconexões em segundos. Esperar é quase sempre melhor que desistir da faixa:
        cada faixa que morre aqui é uma faixa que *existia* na rede e não foi procurada.

        Mas nem sempre volta. No dia 01/11 ele ficou preso em "Disconnecting" por mais
        de oito minutos, sem nunca se desconectar de fato nem reconectar. Por isso há
        tempo-limite, e por isso quem chama precisa saber reiniciar o motor.
        """
        gasto = 0.0
        while gasto < espera_max_s:
            try:
                if self.conectado():
                    return True
            except ErroSlskd:
                pass  # o motor pode estar subindo; insistir é o certo aqui
            self._dormir(passo_s)
            gasto += passo_s
        try:
            return self.conectado()
        except ErroSlskd:
            return False

    # ----------------------------------------------------------------- busca

    #: Quanto esperar uma busca terminar. **Medido** numa corrida real de 01/11/2026,
    #: do `startedAt` ao `endedAt` que o próprio slskd grava:
    #:
    #:     Josh Butler Hap Hazard   38,7 s      Fcukers Bon Bon       41,4 s
    #:     Josh Butler hazard       31,3 s      Julius Strieder...    30,3 s
    #:     Silva Bumpa Riordan...   27,5 s      Hap Hazard            26,1 s
    #:
    #: O valor antigo era **25 s** — abaixo de quase toda busca de verdade. E como o
    #: slskd não entrega resultado parcial, desistir um segundo antes do fim é o mesmo
    #: que não ter buscado: o app relatava "nada na rede" com 42 arquivos guardados
    #: dentro do motor. Setenta e cinco cobre a mais lenta medida com folga de 80%.
    ESPERA_PELA_BUSCA_S = 75.0

    def buscar(self, texto: str, espera_max_s: float | None = None) -> list[Candidato]:
        """Faz uma busca completa e devolve os candidatos aproveitáveis.

        **Respeita o limitador**: se a cota da janela acabou, espera. É por isso que esta
        chamada pode demorar minutos em vez de segundos — e é de propósito, porque a
        alternativa é meia hora de banimento.
        """
        self.limitador.aguardar_vez()
        if espera_max_s is None:
            espera_max_s = self.ESPERA_PELA_BUSCA_S

        busca_id = self._abrir_busca(texto)
        terminou = False
        try:
            terminou = bool(self._esperar_terminar(busca_id, espera_max_s).get("isComplete"))
            #: Busca que não terminou devolve lista vazia, e vazio aqui **não** quer
            #: dizer "não existe na rede". Quem chama precisa da diferença para não
            #: relatar uma mentira.
            self.ultima_busca_terminou = terminou
            respostas = self._chamar("GET", f"/searches/{busca_id}/responses") or []
            return candidatos_das_respostas(respostas)
        finally:
            # Buscas acumulam no slskd; limpar evita a lista crescer sem fim. Mas só
            # se ela JÁ TERMINOU.
            #
            # Apagar busca em andamento cancela a busca por dentro do slskd, e a tarefa
            # dele que ia gravar o resultado quebra num
            # `DbUpdateConcurrencyException: ...affected 0 row(s); data may have been
            # modified or deleted`. O log do usuário tem 200 desses, e logo depois de um
            # deles o cliente Soulseek travou em "Disconnecting" e não voltou mais:
            # 14 faixas seguidas morreram sem nem serem procuradas.
            #
            # O tempo-limite de 25 s é generoso para uma busca, mas estourá-lo é normal.
            # Quando estoura, a busca fica para a faxina de `_limpar_buscas_terminadas`,
            # que só apaga o que está marcado como completo.
            if terminou:
                try:
                    self._chamar("DELETE", f"/searches/{busca_id}")
                except ErroSlskd:
                    pass
            else:
                # Deixadas para trás acumulam. A faxina só apaga o que o slskd já
                # marcou como completo, então ela é segura — mas custa uma chamada,
                # por isso não roda a cada busca.
                self._deixadas_para_tras += 1
                if self._deixadas_para_tras >= self.FAXINA_A_CADA:
                    self._deixadas_para_tras = 0
                    self._limpar_buscas_terminadas()

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
            except SemRedeSoulseek:
                # Também é 409, e insistir não adianta nada: sem rede, as três tentativas
                # só queimam nove segundos para chegar na mesma resposta. Quem chama
                # precisa saber disto para ESPERAR a rede voltar, não para desistir.
                raise
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

        **Estourar o tempo é perder a busca inteira.** Eu escrevia aqui que "o que já
        chegou vale" — está errado, e custou meia playlist. Medido no slskd em corrida:

            completa=False | ele diz 5 respostas / 9 arquivos | /responses devolve 0

        Enquanto a busca não termina, o endpoint de respostas devolve **lista vazia**.
        Não existe resultado parcial para ler.
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
