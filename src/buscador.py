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
from normalizador import (
    Variante,
    artista_aparece_em,
    gerar_variantes,
    proximidade_do_titulo,
    titulo_aparece_em,
)
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
    #: Barrados por serem **outra música do artista certo** — o caso de buscar
    #: "Djavan ficar" e receber "Tenho Medo de Ficar Só".
    de_outra_musica: list[Candidato] = field(default_factory=list)
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
        if self.de_outra_musica:
            return (
                f"❌ {self.faixa} — achou {len(self.de_outra_musica)} do artista certo, "
                f"mas de outra música ({self.buscas_gastas} busca(s))"
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
        conferir_nomes: bool = True,
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
        self.conferir_nomes = conferir_nomes

    def buscar_faixa(self, faixa: Faixa) -> ResultadoDaBusca:
        resultado = ResultadoDaBusca(faixa=faixa)

        for variante in gerar_variantes(faixa.artista, faixa.titulo)[: self.max_variantes]:
            resultado.variantes_tentadas.append(variante)

            candidatos = self.cliente.buscar(variante.consulta)
            if not candidatos:
                continue

            # Confere artista e título de volta ANTES de qualquer outra coisa. As duas
            # peneiras existem porque as variantes largas jogam fora metade do par:
            # `so_titulo` busca sem o artista, `artista_palavra_chave` busca com só uma
            # ou duas palavras do título. Sem conferir, o app baixa a música certa do
            # cantor errado, ou a música errada do cantor certo — as duas já aconteceram.
            candidatos = self._peneirar(candidatos, faixa, variante, resultado)
            if not candidatos:
                continue

            aprovados = ranquear(candidatos, faixa.duracao_s, self.criterios)
            if not aprovados:
                # Achou arquivos, mas nenhum presta. Guarda os motivos e segue tentando:
                # outra grafia pode trazer gente com acervo melhor.
                resultado.descartados = reprovados(candidatos, faixa.duracao_s, self.criterios)
                continue

            resultado.variante_que_acertou = variante
            resultado.aprovados = self._reordenar_por_proximidade(aprovados, faixa)
            resultado.descartados = reprovados(candidatos, faixa.duracao_s, self.criterios)
            resultado.escolhidos = escolher_melhores(aprovados, self.quantidade_por_faixa)
            return resultado

        return resultado

    def _peneirar(
        self,
        candidatos: list[Candidato],
        faixa: Faixa,
        variante: Variante,
        resultado: ResultadoDaBusca,
    ) -> list[Candidato]:
        if not self.conferir_nomes:
            return candidatos

        # O título é conferido em TODAS as variantes, inclusive na `fiel`.
        #
        # Eu só conferia nas variantes que encurtam o título, supondo que a consulta
        # fiel levava o título inteiro e o servidor do Soulseek filtrava direito. Com
        # título de palavras curtas isso não vale: buscando *Jansons — U Do* pela
        # variante fiel, o app baixou uma sinfonia de Beethoven regida por Mariss
        # Jansons. "U" e "Do" não filtram nada do lado de lá.
        sobreviventes = []
        for candidato in candidatos:
            if faixa.artista and not artista_aparece_em(candidato.caminho, faixa.artista):
                resultado.de_outro_artista.append(candidato)
                continue
            if not titulo_aparece_em(candidato.nome_arquivo, faixa.titulo):
                resultado.de_outra_musica.append(candidato)
                continue
            sobreviventes.append(candidato)
        return sobreviventes

    #: Peso da proximidade do nome no desempate. Pequeno de propósito: 30 pontos
    #: desempatam entre dois FLACs, mas não fazem um MP3 (500) passar na frente de um
    #: sem perda (1000). Qualidade continua mandando; o nome só decide empate.
    PESO_DA_PROXIMIDADE = 30

    def _reordenar_por_proximidade(
        self, aprovados: list[Avaliacao], faixa: Faixa
    ) -> list[Avaliacao]:
        """Entre arquivos de mesma qualidade, prefere o nome mais limpo.

        É o que separa `13 Flor de Lis.flac` de
        `08_Limão Avião Flor De Lis - Ao Vivo.flac` — os dois aprovados, um deles bem
        mais provável de ser a faixa pedida.
        """
        if not faixa.titulo:
            return aprovados

        def nota(avaliacao: Avaliacao) -> float:
            proximidade = proximidade_do_titulo(avaliacao.candidato.nome_arquivo, faixa.titulo)
            return avaliacao.pontos + proximidade * self.PESO_DA_PROXIMIDADE

        return sorted(aprovados, key=nota, reverse=True)

    def buscar_varias(self, faixas: list[Faixa]) -> list[ResultadoDaBusca]:
        """Busca uma lista inteira. Demora o que o limitador mandar."""
        return [self.buscar_faixa(faixa) for faixa in faixas]

    #: Quanto uma busca leva na rede, em média. Medido: uma trouxe 252 respostas em 5 s,
    #: outra rodou até o tempo-limite. Doze segundos é o meio-termo observado.
    SEGUNDOS_POR_BUSCA = 12.0

    def tempo_estimado_s(self, quantas_faixas: int, variantes_por_faixa: float = 1.6) -> float:
        """Quanto a lista deve levar, em segundos — espera do limite **mais** as buscas.

        Só a espera do limitador dava zero para listas curtas, porque as 34 primeiras
        buscas saem sem esperar. "~0 min" para 14 faixas é um número inútil: o usuário
        lê isso e acha que vai ser instantâneo, quando na prática são uns três minutos
        só de rede, e mais o tempo dos downloads.

        `variantes_por_faixa` é média: a maioria resolve na primeira ou segunda. É
        chute informado, e o relatório real permite calibrá-lo com o uso.
        """
        buscas = max(1, int(quantas_faixas * variantes_por_faixa))
        espera = self.cliente.limitador.tempo_estimado_s(buscas)
        return espera + buscas * self.SEGUNDOS_POR_BUSCA
