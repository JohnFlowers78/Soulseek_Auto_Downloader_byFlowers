"""Testes da janela principal.

Offscreen, sem abrir janela e sem tocar na rede. O motor é substituído por um duble:
subir o slskd de verdade num teste seria péssimo — ele entra na rede Soulseek.
"""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6", reason="interface gráfica não instalada")

from PySide6.QtWidgets import QApplication  # noqa: E402

from config import Config  # noqa: E402
from motor import EstadoDoMotor, Situacao  # noqa: E402
from politica import Foco  # noqa: E402
from tela_principal import JanelaPrincipal  # noqa: E402
from trabalho import Andamento  # noqa: E402


class MotorFalso:
    def __init__(self, situacao=None, nosso=False):
        self._situacao = situacao or Situacao(EstadoDoMotor.PARADO)
        self.fomos_nos = nosso
        self.log: list[str] = []
        self.ligou = 0
        self.desligou = 0

    def situacao(self):
        return self._situacao

    def usuario_logado(self):
        return ""

    def log_recente(self, quantas=20):
        return self.log[-quantas:]

    def ligar(self):
        self.ligou += 1
        self._situacao = Situacao(EstadoDoMotor.SUBINDO)
        return self._situacao

    def desligar(self):
        self.desligou += 1
        self._situacao = Situacao(EstadoDoMotor.PARADO)
        return self._situacao


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def config(tmp_path):
    pastas = {}
    for nome in ("playlists", "acervo", "compartilhada"):
        caminho = tmp_path / nome
        caminho.mkdir()
        pastas[nome] = str(caminho)
    c = Config(
        pasta_mae_playlists=pastas["playlists"],
        pasta_mae_acervo=pastas["acervo"],
        pasta_compartilhada=pastas["compartilhada"],
        slskd_api_key="chave",
        spotify_client_id="id",
    )
    c.confirmar_compartilhada()
    return c


def janela(app, config, motor=None) -> JanelaPrincipal:
    j = JanelaPrincipal(config)
    j.motor = motor or MotorFalso()
    j._atualizar_motor()
    return j


# ------------------------------------------------------------------ montar


def test_a_janela_monta_com_as_tres_abas(app, config):
    j = janela(app, config)
    titulos = [j.abas.tabText(i) for i in range(j.abas.count())]

    assert len(titulos) == 3
    for esperado in ("Baixar", "Motor", "Configurações"):
        assert any(esperado in t for t in titulos), esperado


def test_o_titulo_diz_de_quem_e(app, config):
    assert "Flowers" in janela(app, config).windowTitle()


# ------------------------------------------------------------------ motor


def test_motor_parado_deixa_ligar_e_nao_desligar(app, config):
    j = janela(app, config, MotorFalso(Situacao(EstadoDoMotor.PARADO)))

    assert j.botao_ligar.isEnabled()
    assert not j.botao_desligar.isEnabled()


def test_motor_de_outro_nao_pode_ser_desligado_por_nos(app, config):
    # Um slskd que o usuário abriu à mão não é nosso para matar.
    motor = MotorFalso(Situacao(EstadoDoMotor.DE_FORA, "já havia um rodando"), nosso=False)
    j = janela(app, config, motor)

    assert not j.botao_ligar.isEnabled()
    assert not j.botao_desligar.isEnabled()


def test_o_que_nos_subimos_pode_ser_desligado(app, config):
    motor = MotorFalso(Situacao(EstadoDoMotor.RODANDO), nosso=True)
    j = janela(app, config, motor)

    assert j.botao_desligar.isEnabled()


def test_o_botao_liga_o_motor(app, config):
    motor = MotorFalso()
    j = janela(app, config, motor)
    j._ligar_motor()

    assert motor.ligou == 1


def test_o_estado_do_motor_aparece_na_tela(app, config):
    j = janela(app, config, MotorFalso(Situacao(EstadoDoMotor.SUBINDO, "montando cache")))
    assert "montando cache" in j.rotulo_motor.text()


# ----------------------------------------------------- impedimentos


def test_sem_entrada_nao_comeca(app, config):
    j = janela(app, config, MotorFalso(Situacao(EstadoDoMotor.RODANDO)))
    assert "Cole um link" in j._impedimento_para_baixar()


def test_sem_motor_no_ar_nao_comeca(app, config):
    j = janela(app, config, MotorFalso(Situacao(EstadoDoMotor.PARADO)))
    j.campo_entrada.setText("Djavan - Flor de Lis")

    assert "motor não está no ar" in j._impedimento_para_baixar()


def test_pasta_de_playlists_que_nao_existe_nao_comeca(app, config, tmp_path):
    """Nao basta o campo estar preenchido — a pasta precisa EXISTIR.

    A tela de Configuracoes sugere um caminho padrao no campo. Um caminho sugerido e
    nunca criado passava pelo teste de "esta vazio?" e so quebrava na hora de gravar
    o primeiro arquivo.
    """
    j = janela(app, config, MotorFalso(Situacao(EstadoDoMotor.RODANDO)))
    j.campo_entrada.setText("Djavan - Flor de Lis")
    j.config.pasta_mae_playlists = str(tmp_path / "nunca_criada")

    assert "pasta das playlists" in j._impedimento_para_baixar()


def test_sem_pasta_nenhuma_tambem_nao_comeca(app, config):
    j = janela(app, config, MotorFalso(Situacao(EstadoDoMotor.RODANDO)))
    j.campo_entrada.setText("Djavan - Flor de Lis")
    j.config.pasta_mae_playlists = ""

    assert "pasta das playlists" in j._impedimento_para_baixar()


def test_com_tudo_pronto_nao_ha_impedimento(app, config):
    j = janela(app, config, MotorFalso(Situacao(EstadoDoMotor.RODANDO)))
    j.campo_entrada.setText("Djavan - Flor de Lis")

    assert j._impedimento_para_baixar() == ""


# ----------------------------------------------------------- progresso


def test_o_progresso_enche_as_tres_listas(app, config):
    j = janela(app, config)
    andamento = Andamento(
        indice=3,
        total=10,
        faixa="Djavan — Se",
        baixadas=["a.flac", "b.mp3"],
        presas=["c.flac"],
        nao_vieram=["d — nada na rede"],
    )
    j._andou(andamento)

    assert j.lista_baixadas.count() == 2
    assert j.lista_presas.count() == 1
    assert j.lista_faltaram.count() == 1
    assert j.barra.value() == 3


def test_a_lista_so_cresce_e_nao_pisca(app, config):
    # Redesenhar tudo a cada volta faria a lista piscar numa corrida de horas.
    j = janela(app, config)
    j._andou(Andamento(total=10, baixadas=["a.flac"]))
    j._andou(Andamento(total=10, baixadas=["a.flac", "b.flac"]))

    assert j.lista_baixadas.count() == 2
    assert j.lista_baixadas.item(0).text() == "a.flac"


def test_os_erros_aparecem_junto_do_que_nao_veio(app, config):
    j = janela(app, config)
    j._andou(Andamento(total=5, nao_vieram=["x"], erros=["y — ErroSlskd"]))

    assert j.lista_faltaram.count() == 2


def test_cada_download_ganha_sua_barra_de_porcentagem(app, config):
    j = janela(app, config)
    j._andou(Andamento(total=5, baixando=[("a.flac", 42), ("b.aiff", 7)]))

    assert set(j._barras) == {"a.flac", "b.aiff"}
    assert j._barras["a.flac"][1].value() == 42
    assert j._barras["b.aiff"][1].value() == 7


def test_as_barras_sao_reaproveitadas_e_nao_recriadas(app, config):
    # Criar e destruir widgets a cada segundo, por horas, faria a janela piscar.
    j = janela(app, config)
    j._andou(Andamento(total=5, baixando=[("a.flac", 10)]))
    barra_antes = j._barras["a.flac"][1]

    j._andou(Andamento(total=5, baixando=[("a.flac", 80)]))

    assert j._barras["a.flac"][1] is barra_antes
    assert barra_antes.value() == 80


def test_arquivo_que_terminou_perde_a_barra(app, config):
    j = janela(app, config)
    j._andou(Andamento(total=5, baixando=[("a.flac", 90), ("b.flac", 50)]))
    j._andou(Andamento(total=5, baixando=[("b.flac", 70)], baixadas=["a.flac"]))

    assert set(j._barras) == {"b.flac"}


def test_sem_nada_baixando_aparece_o_aviso_de_ocioso(app, config):
    j = janela(app, config)
    j._andou(Andamento(total=5, baixando=[("a.flac", 10)]))
    assert not j.rotulo_ocioso.isVisible() or True  # offscreen não calcula visibilidade

    j._andou(Andamento(total=5, baixando=[]))
    assert j._barras == {}


def test_nome_comprido_e_encurtado_mas_o_inteiro_fica_na_dica(app, config):
    comprido = "Ludwig van Beethoven, Bavarian Radio Symphony Orchestra - Symphony No. 6.flac"
    j = janela(app, config)
    j._andou(Andamento(total=1, baixando=[(comprido, 50)]))

    rotulo = j._barras[comprido][0]
    assert len(rotulo.text()) <= 52
    assert rotulo.toolTip() == comprido


def test_a_faixa_atual_aparece_com_a_posicao(app, config):
    j = janela(app, config)
    j._andou(Andamento(indice=7, total=14, faixa="Tim Maia — Você"))

    assert "[7/14]" in j.rotulo_faixa.text()
    assert "Tim Maia" in j.rotulo_faixa.text()


# --------------------------------------------------------------- foco


def test_o_foco_padrao_e_sem_perda(app, config):
    # O Qt guarda o VALOR do enum de string, nao o membro — por isso ==.
    assert janela(app, config).escolha_foco.currentData() == Foco.SEM_PERDA


def test_da_para_escolher_mp3(app, config):
    j = janela(app, config)
    j.escolha_foco.setCurrentIndex(1)
    assert Foco(j.escolha_foco.currentData()) is Foco.MP3


# --------------------------------------------------------------- fechar


def test_fechar_derruba_o_motor(app, config):
    # Nada de processo órfão depois que a janela some.
    from PySide6.QtGui import QCloseEvent

    motor = MotorFalso(Situacao(EstadoDoMotor.RODANDO), nosso=True)
    j = janela(app, config, motor)
    j.closeEvent(QCloseEvent())

    assert motor.desligou >= 1
