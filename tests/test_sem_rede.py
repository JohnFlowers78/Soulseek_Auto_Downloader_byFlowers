"""O motor de pé, mas fora da rede Soulseek — e o 409 que significa duas coisas.

Em 01/11/2026 uma playlist de 27 faixas baixou zero arquivos. O relatório culpou a rede
("não vieram"), mas o log do slskd contava outra história:

    [15:34:37 ERR] Failed to execute search ...: The server connection must be connected
    and logged in to perform a search (currently: Disconnecting)

O cliente Soulseek travou em "Disconnecting" e ficou assim por mais de oito minutos. A
porta HTTP do slskd continuou respondendo o tempo todo — por isso o app achou que estava
tudo bem — mas toda busca voltava **409**. Como 409 também é o código de "ocupado", o app
insistiu três vezes por faixa e marcou **14 faixas seguidas** como fracasso sem procurar
nenhuma delas.

E tem a provável causa da travada, que era culpa nossa: o app apagava cada busca assim
que lia as respostas, mesmo com a busca ainda rodando. O log tem 200
`DbUpdateConcurrencyException: ...affected 0 row(s); data may have been modified or
deleted` — o slskd tentando gravar o resultado de uma busca que a gente acabou de apagar.

As amostras abaixo são o texto real das respostas.
"""

import pytest

from limitador import LimitadorDeBuscas
from slskd_cliente import ClienteSlskd, ErroSlskd, SemRedeSoulseek

#: Corpo real do 409 do slskd quando ele está fora da rede.
FORA_DA_REDE = (
    b"The server connection must be connected and logged in to perform a search "
    b"(currently: Disconnecting)"
)
#: Corpo de um 409 de verdade — busca duplicada, que repetir resolve.
OCUPADO = b"A search with id 1f978965-d2fb-4e57-905b-a98ed613fc91 is already in progress"


class ConexaoFalsa:
    def __init__(self, status=200, corpo=b""):
        self.status = status
        self.corpo = corpo
        self.pedidos: list[tuple[str, str]] = []

    def pedir(self, metodo, caminho, corpo, cabecalhos):
        self.pedidos.append((metodo, caminho))
        return self.status, self.corpo

    def fechar(self):
        pass


def cliente_com(conexao) -> ClienteSlskd:
    c = ClienteSlskd(chave_api="chave", dormir=lambda _s: None)
    c._conexao = conexao
    return c


# ------------------------------------------------ 409 quer dizer duas coisas


def test_quatro_zero_nove_de_fora_da_rede_e_outro_erro():
    c = cliente_com(ConexaoFalsa(status=409, corpo=FORA_DA_REDE))

    with pytest.raises(SemRedeSoulseek) as erro:
        c._http("POST", "/searches")

    assert "saiu da rede Soulseek" in str(erro.value)


def test_quatro_zero_nove_de_ocupado_continua_erro_comum():
    # Este aqui repetir resolve — e por isso NÃO pode virar SemRedeSoulseek.
    c = cliente_com(ConexaoFalsa(status=409, corpo=OCUPADO))

    with pytest.raises(ErroSlskd) as erro:
        c._http("POST", "/searches")

    assert not isinstance(erro.value, SemRedeSoulseek)
    assert "409" in str(erro.value)


def test_a_mensagem_de_fora_da_rede_carrega_o_que_o_slskd_disse():
    # Sem o corpo, não dá para distinguir uma coisa da outra depois.
    c = cliente_com(ConexaoFalsa(status=409, corpo=FORA_DA_REDE))

    with pytest.raises(SemRedeSoulseek) as erro:
        c._http("POST", "/searches")

    assert "Disconnecting" in str(erro.value)


def test_sem_rede_continua_sendo_um_ErroSlskd():
    # Quem só quer saber que deu errado (o `_recolher`, por exemplo) continua pegando.
    assert issubclass(SemRedeSoulseek, ErroSlskd)


# ------------------------------------- insistir sem rede é queimar o relógio


class ConexaoQueConta(ConexaoFalsa):
    def __init__(self, status, corpo):
        super().__init__(status, corpo)
        self.posts = 0

    def pedir(self, metodo, caminho, corpo, cabecalhos):
        if metodo == "POST" and caminho == "/searches":
            self.posts += 1
        return super().pedir(metodo, caminho, corpo, cabecalhos)


def test_sem_rede_nao_tenta_tres_vezes():
    """Três tentativas × 3, 6 e 9 segundos = 18 segundos por faixa, para nada."""
    conexao = ConexaoQueConta(409, FORA_DA_REDE)
    c = cliente_com(conexao)

    with pytest.raises(SemRedeSoulseek):
        c._abrir_busca("Piem Music In Me")

    assert conexao.posts == 1


def test_ocupado_continua_tentando_de_novo():
    conexao = ConexaoQueConta(409, OCUPADO)
    c = cliente_com(conexao)

    with pytest.raises(ErroSlskd):
        c._abrir_busca("Piem Music In Me")

    assert conexao.posts == 3, "o 409 de ocupado continua valendo a pena repetir"


# --------------------------------- não apagar busca que ainda está rodando


class TransporteDeBusca:
    """Finge o slskd durante uma busca, e anota o que foi apagado."""

    def __init__(self, completa: bool):
        self.completa = completa
        self.apagadas: list[str] = []
        self.visitadas: list[str] = []

    def __call__(self, metodo, caminho, corpo=None):
        self.visitadas.append(caminho)
        if metodo == "DELETE":
            self.apagadas.append(caminho)
            return 200, None
        if caminho.endswith("/responses"):
            return 200, []
        if caminho.startswith("/searches/") and metodo == "GET":
            return 200, {"isComplete": self.completa}
        return 200, None


def cliente_de_busca(transporte) -> ClienteSlskd:
    return ClienteSlskd(
        chave_api="chave",
        limitador=LimitadorDeBuscas(limite=100, janela_s=1),
        transporte=transporte,
        dormir=lambda _s: None,
    )


def test_busca_que_terminou_e_apagada():
    transporte = TransporteDeBusca(completa=True)
    cliente_de_busca(transporte).buscar("Djavan Flor de Lis", espera_max_s=1)

    assert transporte.apagadas, "busca terminada tem que sair da lista do slskd"


def test_as_deixadas_para_tras_sao_varridas_de_tempos_em_tempos():
    """Não apagar na hora não pode virar lista crescendo sem fim.

    A faxina só apaga o que o slskd já marcou como completo — por isso ela é segura
    onde o DELETE direto não era.
    """
    transporte = TransporteDeBusca(completa=False)
    cliente = cliente_de_busca(transporte)

    for _ in range(ClienteSlskd.FAXINA_A_CADA):
        cliente.buscar("qualquer coisa", espera_max_s=1)

    assert "/searches" in [c for c in transporte.visitadas if c == "/searches"], (
        "a faxina tem que ter listado as buscas"
    )


def test_busca_ainda_rodando_nao_e_apagada():
    """Apagar busca em andamento cancela a busca por dentro do slskd.

    A tarefa dele que ia gravar o resultado quebra num `DbUpdateConcurrencyException`
    — 200 deles no log do usuário — e logo depois de um desses o cliente Soulseek
    travou em "Disconnecting" e não voltou mais.
    """
    transporte = TransporteDeBusca(completa=False)
    cliente_de_busca(transporte).buscar("Adem4 Lost", espera_max_s=1)

    assert transporte.apagadas == []


# ------------------------------------------------------- esperar a rede voltar


class TransporteDeEstado:
    """O servidor volta depois de N consultas."""

    def __init__(self, volta_na: int | None):
        self.volta_na = volta_na
        self.consultas = 0

    def __call__(self, metodo, caminho, corpo=None):
        if caminho.startswith("/application"):
            self.consultas += 1
            logado = self.volta_na is not None and self.consultas >= self.volta_na
            estado = "Connected, LoggedIn" if logado else "Disconnecting"
            return 200, {"server": {"state": estado}}
        return 200, None


def test_esperar_rede_devolve_verdadeiro_quando_ela_volta():
    transporte = TransporteDeEstado(volta_na=3)
    c = cliente_de_busca(transporte)

    assert c.esperar_rede(espera_max_s=60, passo_s=1)


def test_esperar_rede_desiste_no_tempo_limite():
    # Travado em "Disconnecting" foi exatamente o que aconteceu, por oito minutos.
    c = cliente_de_busca(TransporteDeEstado(volta_na=None))

    assert not c.esperar_rede(espera_max_s=5, passo_s=1)


def test_esperar_rede_nao_quebra_se_o_motor_estiver_subindo():
    # Enquanto o slskd sobe, a porta recusa conexão. Isso não é "não voltou", é "ainda não".
    class Recusando:
        def __init__(self):
            self.vezes = 0

        def __call__(self, metodo, caminho, corpo=None):
            self.vezes += 1
            if self.vezes < 3:
                raise ErroSlskd("Não consegui falar com o slskd. Ele está rodando?")
            return 200, {"server": {"state": "Connected, LoggedIn"}}

    assert cliente_de_busca(Recusando()).esperar_rede(espera_max_s=60, passo_s=1)
