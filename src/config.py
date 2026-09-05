"""As configurações do app, guardadas em JSON fora do repositório.

Segredo nenhum entra no código: a chave da API do slskd e o token do Spotify vivem no
arquivo de configuração, dentro da pasta de dados do usuário (ver `sistema.py`).
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

import sistema

FORMATOS_PADRAO = ["flac", "wav", "aiff", "aif", "mp3", "m4a", "aac"]


@dataclass
class Config:
    """Tudo que o usuário escolhe. Os valores padrão são o que faz sentido sem ele mexer."""

    # --- pastas ---
    pasta_destino: str = ""
    #: A pasta que o slskd oferece para os outros usuários da rede. Sem ela o app
    #: funciona por um tempo e depois para de conseguir baixar — ver `problemas()`.
    pasta_compartilhada: str = ""

    # --- motor ---
    motor: str = "slskd"
    slskd_url: str = "http://localhost:5030"
    slskd_api_key: str = ""

    # --- qualidade ---
    formatos_aceitos: list[str] = field(default_factory=lambda: list(FORMATOS_PADRAO))
    minimo_mp3_kbps: int = 320
    minimo_aac_kbps: int = 256
    quantidade_por_faixa: int = 2

    # --- limites da rede ---
    #: 34 buscas a cada 220 s. Mexer nisso para cima é pedir banimento de 30 minutos.
    buscas_por_janela: int = 34
    janela_de_buscas_s: int = 220

    # --- acesso do celular ---
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

    def salvar(self, caminho: Path | None = None) -> Path:
        """Grava o arquivo, criando a pasta se preciso. Devolve onde gravou."""
        caminho = caminho or self.caminho_padrao()
        caminho.parent.mkdir(parents=True, exist_ok=True)
        caminho.write_text(
            json.dumps(asdict(self), indent=2, ensure_ascii=False), encoding="utf-8"
        )
        return caminho

    # ---------------------------------------------------------------- validação

    def problemas(self) -> list[str]:
        """O que ainda impede o app de funcionar, em português, para aparecer na tela.

        Devolve lista vazia quando está tudo certo. Cada frase diz **o que fazer**, não só
        o que está errado — mensagem de erro que não ensina a sair dela é decoração.
        """
        pendencias: list[str] = []

        if not self.pasta_destino.strip():
            pendencias.append("Escolha a pasta onde as músicas baixadas vão ficar.")
        elif not Path(self.pasta_destino).is_dir():
            pendencias.append(f"A pasta de destino não existe: {self.pasta_destino}")

        if not self.pasta_compartilhada.strip():
            pendencias.append(
                "Escolha uma pasta para compartilhar na rede. Sem ela o Soulseek anuncia "
                '"Nothing Shared" e os outros usuários bloqueiam você — os downloads param.'
            )
        elif not Path(self.pasta_compartilhada).is_dir():
            pendencias.append(
                f"A pasta compartilhada não existe: {self.pasta_compartilhada}"
            )

        if self.motor == "slskd" and not self.slskd_api_key.strip():
            pendencias.append(
                "Falta a chave de API do slskd (está no arquivo slskd.yml, em "
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

    @property
    def pronto(self) -> bool:
        return not self.problemas()
