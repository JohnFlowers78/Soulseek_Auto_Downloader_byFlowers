"""As estruturas que atravessam o app inteiro.

Ficam num lugar só porque **os dois motores** (slskd e SoulseekQt) precisam falar a mesma
língua. O resto do código não deve saber qual motor está em uso — quem garante isso é este
módulo, definindo o vocabulário comum.

Detalhe que vem de fora e molda tudo: o `MotorSoulseekQt` frequentemente **não sabe o
bitrate** (a tela não mostra). Por isso quase todo campo de qualidade é opcional, e o
`qualidade.py` sabe estimar o que faltar.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class EstadoTransferencia(str, Enum):
    """Em que pé está um download.

    As três primeiras são as que viram as listas da tela: baixou, está preso, não veio.
    """

    NA_FILA = "na_fila"          # esperando o outro usuário liberar slot
    BAIXANDO = "baixando"
    CONCLUIDA = "concluida"
    FALHOU = "falhou"
    CANCELADA = "cancelada"


@dataclass(frozen=True)
class Faixa:
    """Uma música como veio da playlist do Spotify."""

    artista: str
    titulo: str
    album: str = ""
    duracao_s: float | None = None
    #: Código único da gravação. Só vem pelo caminho da API — é a rede de segurança
    #: contra baixar a versão errada (ao vivo, remaster) com o mesmo nome.
    isrc: str = ""

    def __str__(self) -> str:
        return f"{self.artista} — {self.titulo}"


@dataclass(frozen=True)
class Candidato:
    """Um arquivo encontrado na rede, oferecido por um usuário.

    Vem de qualquer um dos dois motores. Os campos opcionais são exatamente os que o
    SoulseekQt costuma não informar.
    """

    usuario: str
    #: Caminho como o dono compartilha — quase sempre com barra invertida do Windows.
    caminho: str
    tamanho_bytes: int
    duracao_s: float | None = None
    bitrate_kbps: int | None = None
    taxa_amostragem_hz: int | None = None
    profundidade_bits: int | None = None
    #: O usuário tem vaga livre para enviar agora?
    slot_livre: bool = False
    #: Quantos estão na frente na fila dele.
    posicao_fila: int | None = None
    velocidade_bps: int | None = None

    @property
    def nome_arquivo(self) -> str:
        """Só o nome, sem a pasta.

        Trata as duas barras de propósito: o caminho vem da máquina de outra pessoa, que
        na esmagadora maioria é Windows (``@@xyz\\Music\\Artista\\faixa.mp3``), mas há
        quem compartilhe de Linux ou Mac.
        """
        return self.caminho.replace("\\", "/").rsplit("/", 1)[-1]

    @property
    def extensao(self) -> str:
        """A extensão em minúsculas, sem o ponto. Vazia se não houver."""
        nome = self.nome_arquivo
        return nome.rsplit(".", 1)[-1].lower() if "." in nome else ""


@dataclass
class Transferencia:
    """Um download acompanhado do início ao fim."""

    candidato: Candidato
    estado: EstadoTransferencia = EstadoTransferencia.NA_FILA
    bytes_transferidos: int = 0
    posicao_fila: int | None = None
    #: Preenchido quando termina — é o arquivo que existe no disco.
    caminho_local: str = ""
    erro: str = ""

    @property
    def progresso(self) -> float:
        """De 0.0 a 1.0. Zero quando o tamanho é desconhecido, para não dividir por zero."""
        if self.candidato.tamanho_bytes <= 0:
            return 0.0
        return min(1.0, self.bytes_transferidos / self.candidato.tamanho_bytes)

    @property
    def terminou(self) -> bool:
        return self.estado in {
            EstadoTransferencia.CONCLUIDA,
            EstadoTransferencia.FALHOU,
            EstadoTransferencia.CANCELADA,
        }


@dataclass
class ResultadoDaFaixa:
    """O que aconteceu com uma faixa da playlist, do começo ao fim.

    É a linha que aparece nas três listas da tela — e o que fica guardado para retomar
    a fila depois de fechar o app.
    """

    faixa: Faixa
    #: Quais consultas foram tentadas, na ordem, com a etiqueta da estratégia.
    consultas_tentadas: list[str] = field(default_factory=list)
    #: Os arquivos escolhidos para baixar (pode ser mais de um, para comparar depois).
    transferencias: list[Transferencia] = field(default_factory=list)

    @property
    def baixou(self) -> bool:
        return any(t.estado is EstadoTransferencia.CONCLUIDA for t in self.transferencias)

    @property
    def preso_na_fila(self) -> bool:
        """Achou e enfileirou, mas nada terminou ainda — o caso do 'seeder offline'."""
        if self.baixou:
            return False
        return any(
            t.estado in {EstadoTransferencia.NA_FILA, EstadoTransferencia.BAIXANDO}
            for t in self.transferencias
        )

    @property
    def nao_encontrada(self) -> bool:
        """Nenhuma variante trouxe nada aproveitável."""
        return not self.transferencias
