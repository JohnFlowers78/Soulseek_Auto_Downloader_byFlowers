"""As configurações do app, guardadas em JSON fora do repositório.

Segredo nenhum entra no código: a chave da API do slskd e o segredo do Spotify vivem no
arquivo de configuração, dentro da pasta de dados do usuário (ver `sistema.py`).

> Nota sobre o que é segredo e o que não é: o **Client ID** do Spotify é público por
> desenho — ele aparece na URL de autorização, no navegador do usuário. O **Client Secret**
> e o **refresh token** são segredo de verdade.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, fields
from datetime import datetime, timedelta
from pathlib import Path

import sistema

FORMATOS_PADRAO = ["flac", "wav", "aiff", "aif", "mp3", "m4a", "aac"]

#: De quanto em quanto tempo o usuário tem que reconfirmar a pasta compartilhada.
#:
#: Pedido dele, e com razão: pasta de compartilhamento é a coisa que **apodrece em
#: silêncio**. O sujeito move o acervo, esvazia a pasta ou troca de HD, e nada reclama —
#: o Soulseek simplesmente passa a anunciar menos (ou "Nothing Shared"), os outros usuários
#: bloqueiam, e semanas depois os downloads param de completar sem erro aparente. Forçar
#: uma reconferência periódica transforma uma falha silenciosa num aviso.
DIAS_ATE_REVALIDAR_COMPARTILHADA = 30


@dataclass
class Config:
    """Tudo que o usuário escolhe. Os valores padrão são o que faz sentido sem ele mexer."""

    # --- as três pastas, definidas no primeiro acesso ------------------------
    #: Cada playlist baixada vira uma **subpasta** aqui dentro.
    pasta_mae_playlists: str = ""
    #: As pastas que o usuário aponta para buscar versão melhor ficam separadas aqui.
    pasta_mae_acervo: str = ""
    #: A que o slskd oferece para a rede. Sem ela o app funciona por um tempo e depois
    #: para de conseguir baixar — ver `problemas()`.
    pasta_compartilhada: str = ""
    #: Quando o usuário confirmou a pasta compartilhada pela última vez (ISO 8601).
    compartilhada_confirmada_em: str = ""

    # --- motor ---------------------------------------------------------------
    motor: str = "slskd"
    slskd_url: str = "http://localhost:5030"
    slskd_api_key: str = ""

    # --- Spotify -------------------------------------------------------------
    spotify_client_id: str = ""
    spotify_client_secret: str = ""
    spotify_refresh_token: str = ""
    #: So para a tela dizer "entrou como Fulano". Nao e segredo.
    spotify_nome_da_conta: str = ""

    # --- qualidade -----------------------------------------------------------
    formatos_aceitos: list[str] = field(default_factory=lambda: list(FORMATOS_PADRAO))
    minimo_mp3_kbps: int = 320
    minimo_aac_kbps: int = 256
    quantidade_por_faixa: int = 2

    # --- limites da rede -----------------------------------------------------
    #: 34 buscas a cada 220 s. Mexer nisso para cima é pedir banimento de 30 minutos.
    buscas_por_janela: int = 34
    janela_de_buscas_s: int = 220

    # --- acesso do celular ---------------------------------------------------
    painel_ativo: bool = False
    painel_porta: int = 8770
    painel_modo: str = "rede local"  # "rede local" ou "túnel"

    # ------------------------------------------------------------------ arquivo

    @staticmethod
    def caminho_padrao() -> Path:
        return sistema.pasta_de_dados() / "config.json"

    @classmethod
    def carregar(cls, caminho: Path | None = None) -> "Config":
        """Lê o arquivo. Arquivo ausente ou estragado devolve os padrões, sem estourar.

        Chaves desconhecidas são ignoradas e chaves faltando ficam no padrão — assim uma
        versão nova do app lê a configuração da versão velha, e vice-versa.
        """
        caminho = caminho or cls.caminho_padrao()
        try:
            dados = json.loads(caminho.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return cls()
        if not isinstance(dados, dict):
            return cls()

        conhecidas = {campo.name for campo in fields(cls)}
        return cls(**{k: v for k, v in dados.items() if k in conhecidas})

    #: Campos que uma gravação de rotina **nunca** pode esvaziar.
    #:
    #: Segredo não se apaga por acidente, e foi o que aconteceu: o refresh token do
    #: Spotify existia (a playlist foi lida com ele) e sumiu na execução seguinte. Uma
    #: gravação feita por um processo cujo `Config` em memória estava sem o campo é
    #: suficiente para zerar o do disco. Apagar um segredo passa a exigir
    #: `esquecer_segredos()`, que é explícito.
    SEGREDOS = ("slskd_api_key", "spotify_client_secret", "spotify_refresh_token")

    def salvar(self, caminho: Path | None = None) -> Path:
        """Grava o arquivo, criando a pasta se preciso. Devolve onde gravou.

        Um segredo vazio em memória **não** sobrescreve um segredo preenchido no disco.
        """
        caminho = caminho or self.caminho_padrao()
        dados = asdict(self)

        anterior = Config.carregar(caminho)
        for campo in self.SEGREDOS:
            if not str(dados.get(campo) or "").strip():
                guardado = getattr(anterior, campo, "")
                if guardado:
                    dados[campo] = guardado
                    setattr(self, campo, guardado)

        caminho.parent.mkdir(parents=True, exist_ok=True)
        caminho.write_text(json.dumps(dados, indent=2, ensure_ascii=False), encoding="utf-8")
        return caminho

    def esquecer_segredos(self, caminho: Path | None = None) -> Path:
        """Apaga os segredos de verdade — o único caminho que faz isso."""
        for campo in self.SEGREDOS:
            setattr(self, campo, "")
        caminho = caminho or self.caminho_padrao()
        caminho.parent.mkdir(parents=True, exist_ok=True)
        caminho.write_text(
            json.dumps(asdict(self), indent=2, ensure_ascii=False), encoding="utf-8"
        )
        return caminho

    # ---------------------------------------------------- pastas de trabalho

    def pasta_da_playlist(self, nome_saneado: str) -> Path:
        """Onde uma playlist vai parar: `<mãe das playlists>/<nome da playlist>`.

        O nome já deve vir saneado por `normalizador.nome_pasta_segura()` — este método
        não sabe tratar caractere proibido, e não deve saber.
        """
        return Path(self.pasta_mae_playlists) / nome_saneado

    # ------------------------------------------- revalidação da compartilhada

    def confirmar_compartilhada(self, quando: datetime | None = None) -> None:
        """Marca que o usuário acabou de conferir a pasta compartilhada."""
        self.compartilhada_confirmada_em = (quando or datetime.now()).isoformat(
            timespec="seconds"
        )

    def dias_desde_confirmacao(self, agora: datetime | None = None) -> int | None:
        """Há quantos dias a pasta compartilhada foi confirmada. `None` se nunca foi."""
        if not self.compartilhada_confirmada_em:
            return None
        try:
            quando = datetime.fromisoformat(self.compartilhada_confirmada_em)
        except ValueError:
            # Data estragada vale como "nunca confirmou" — é o lado seguro: pede de novo.
            return None
        return max(0, ((agora or datetime.now()) - quando).days)

    def precisa_revalidar_compartilhada(self, agora: datetime | None = None) -> bool:
        """True quando passou do prazo (ou nunca foi confirmada)."""
        dias = self.dias_desde_confirmacao(agora)
        return dias is None or dias >= DIAS_ATE_REVALIDAR_COMPARTILHADA

    # ---------------------------------------------------------------- validação

    def problemas(self, agora: datetime | None = None) -> list[str]:
        """O que ainda impede o app de funcionar, em português, para aparecer na tela.

        Devolve lista vazia quando está tudo certo. Cada frase diz **o que fazer**, não só
        o que está errado — mensagem de erro que não ensina a sair dela é decoração.
        """
        pendencias: list[str] = []

        pendencias += self._problemas_das_pastas()
        pendencias += self._problemas_da_compartilhada(agora)

        if self.motor == "slskd" and not self.slskd_api_key.strip():
            pendencias.append(
                "Falta a chave de API do slskd (está no slskd.yml, em "
                "web.authentication.api_keys)."
            )

        if not self.formatos_aceitos:
            pendencias.append("Marque pelo menos um formato aceito.")

        if self.buscas_por_janela > 34 or self.janela_de_buscas_s < 220:
            pendencias.append(
                "O limite de buscas está mais agressivo que o recomendado "
                "(34 a cada 220 s). Estourar dá banimento de 30 minutos."
            )

        return pendencias

    def _problemas_das_pastas(self) -> list[str]:
        pendencias = []
        for valor, rotulo, explicacao in (
            (
                self.pasta_mae_playlists,
                "pasta das playlists",
                "é onde cada playlist baixada vira uma subpasta",
            ),
            (
                self.pasta_mae_acervo,
                "pasta do acervo",
                "é onde ficam as pastas que você aponta para buscar versão melhor",
            ),
        ):
            if not valor.strip():
                pendencias.append(f"Escolha a {rotulo} — {explicacao}.")
            elif not Path(valor).is_dir():
                pendencias.append(f"A {rotulo} não existe: {valor}")
        return pendencias

    def _problemas_da_compartilhada(self, agora: datetime | None) -> list[str]:
        if not self.pasta_compartilhada.strip():
            return [
                "Escolha uma pasta para compartilhar na rede. Sem ela o Soulseek anuncia "
                '"Nothing Shared" e os outros usuários bloqueiam você — os downloads param.'
            ]

        pasta = Path(self.pasta_compartilhada)
        if not pasta.is_dir():
            return [
                f"A pasta compartilhada sumiu: {self.pasta_compartilhada}. "
                "Aponte outra, ou os downloads vão parar de completar."
            ]

        if self.precisa_revalidar_compartilhada(agora):
            dias = self.dias_desde_confirmacao(agora)
            quando = "nunca foi confirmada" if dias is None else f"foi confirmada há {dias} dias"
            return [
                f"Confirme a pasta compartilhada — ela {quando}. "
                f"A conferência é pedida a cada {DIAS_ATE_REVALIDAR_COMPARTILHADA} dias "
                "porque pasta de compartilhamento esvazia sem avisar, e aí os downloads "
                "param sem dar erro."
            ]
        return []

    @property
    def pronto(self) -> bool:
        return not self.problemas()
