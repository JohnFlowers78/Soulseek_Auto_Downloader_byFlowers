"""Busca uma faixa no Soulseek, tentando as variantes até acertar.

Junta as peças que já existem: o `normalizador` gera as formas de escrever a busca, o
`slskd_cliente` pergunta à rede, e o `qualidade` decide o que presta.

**Para na primeira variante que traz resultado aproveitável.** Isso não é otimização
prematura: cada busca gasta cota do limite de 34 por 220 segundos. Tentar as 7 variantes
de toda faixa multiplicaria por sete o tempo de uma playlist — de meia hora para três
horas e meia.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from modelos import Candidato, Faixa
from normalizador import Variante, artista_aparece_em, gerar_variantes
from qualidade import Avaliacao, Criterios, escolher_melhores, ranquear, reprovados
from slskd_cliente import ClienteSlskd


@dataclass
class ResultadoDaBusca:
    """O que a busca de uma faixa produziu — inclusive quando não produziu nada."""

    faixa: Faixa
    #: Na ordem em que foram tentadas. Serve para o relatório e para aprender depois
    #: qual estratégia mais acerta neste acervo.
    variantes_tentadas: list[Variante] = field(default_factory=list)
    #: A variante que trouxe resultado. `None` quando nenhuma trouxe.
    variante_que_acertou: Variante | None = None
    #: Todos os aprovados, do melhor para o pior.
    aprovados: list[Avaliacao] = field(default_factory=list)
    #: Os descartados, com o motivo — é o que responde "não tinha nada mesmo?".
    descartados: list[Avaliacao] = field(default_factory=list)
    #: Arquivos bons que foram barrados por serem de **outro artista**. Separados dos
    #: demais descartes porque contam outra história: a música existe na rede, com esse
    #: nome, mas não é a sua.
    de_outro_artista: list[Candidato] = field(default_factory=list)
    #: Os que vão para a fila de download.
    escolhidos: list[Avaliacao] = field(default_factory=list)

    @property
    def achou(self) -> bool:
        return bool(self.escolhidos)

    @property
    def buscas_gastas(self) -> int:
        return len(self.variantes_tentadas)

    def resumo(self) -> str:
        """Uma linha para a tela e para o log."""
        if self.achou:
            etiqueta = self.variante_que_acertou.estrategia if self.variante_que_acertou else "?"
            return (
                f"✅ {self.faixa} — {len(self.escolhidos)} opção(ões) "
                f"[{etiqueta}, {self.buscas_gastas} busca(s)]"
            )
        if self.descartados:
            return (
                f"⚠️ {self.faixa} — achou {len(self.descartados)}, "
                f"nenhum passou no filtro ({self.buscas_gastas} busca(s))"
            )
        if self.de_outro_artista:
            return (
                f"❌ {self.faixa} — achou {len(self.de_outro_artista)} com esse nome, "
                f"mas de outro artista ({self.buscas_gastas} busca(s))"
            )
        return f"❌ {self.faixa} — nada na rede ({self.buscas_gastas} busca(s))"


class Buscador:
    def __init__(
        self,
        cliente: ClienteSlskd,
        criterios: Criterios | None = None,
        quantidade_por_faixa: int = 2,
        max_variantes: int = 4,
        conferir_artista: bool = True,
    ):
        """`max_variantes` limita quantas formas tentar antes de desistir.

        Quatro é o ponto em que as variantes deixam de ser precisas e passam a ser
        chutes largos (ver a ordem em `normalizador.gerar_variantes`). Insistir além
        disso gasta cota para trazer faixa errada.
        """
        self.cliente = cliente
        self.criterios = criterios
        self.quantidade_por_faixa = quantidade_por_faixa
        self.max_variantes = max_variantes
        self.conferir_artista = conferir_artista

    def buscar_faixa(self, faixa: Faixa) -> ResultadoDaBusca:
        resultado = ResultadoDaBusca(faixa=faixa)

        for variante in gerar_variantes(faixa.artista, faixa.titulo)[: self.max_variantes]:
            resultado.variantes_tentadas.append(variante)

            candidatos = self.cliente.buscar(variante.consulta)
            if not candidatos:
                continue

            # Confere o artista de volta ANTES de qualquer outra coisa. A variante
            # `so_titulo` busca sem o artista de propósito, e sem esta peneira o app
            # baixa a música certa do cantor errado — já aconteceu.
            if self.conferir_artista and faixa.artista:
                do_artista, de_outros = [], []
                for candidato in candidatos:
                    alvo = do_artista if artista_aparece_em(candidato.caminho, faixa.artista) else de_outros
                    alvo.append(candidato)
                resultado.de_outro_artista.extend(de_outros)
                candidatos = do_artista
                if not candidatos:
                    continue

            aprovados = ranquear(candidatos, faixa.duracao_s, self.criterios)
            if not aprovados:
                # Achou arquivos, mas nenhum presta. Guarda os motivos e segue tentando:
                # outra grafia pode trazer gente com acervo melhor.
                resultado.descartados = reprovados(candidatos, faixa.duracao_s, self.criterios)
                continue

            resultado.variante_que_acertou = variante
            resultado.aprovados = aprovados
            resultado.descartados = reprovados(candidatos, faixa.duracao_s, self.criterios)
            resultado.escolhidos = escolher_melhores(aprovados, self.quantidade_por_faixa)
            return resultado

        return resultado

    def buscar_varias(self, faixas: list[Faixa]) -> list[ResultadoDaBusca]:
        """Busca uma lista inteira. Demora o que o limitador mandar."""
        return [self.buscar_faixa(faixa) for faixa in faixas]

    def tempo_estimado_s(self, quantas_faixas: int, variantes_por_faixa: float = 1.6) -> float:
        """Piso de tempo para uma lista, em segundos.

        `variantes_por_faixa` é uma média: a maioria das faixas resolve na primeira ou
        segunda variante. O número é chute informado, e o relatório real vai permitir
        calibrá-lo com o uso.
        """
        buscas = int(quantas_faixas * variantes_por_faixa)
        return self.cliente.limitador.tempo_estimado_s(buscas)
