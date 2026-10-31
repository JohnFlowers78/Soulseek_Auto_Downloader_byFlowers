"""Testes da tela de Configurações.

Rodam **sem abrir janela**: o Qt tem uma plataforma "offscreen" que monta os widgets de
verdade na memória, sem desenhar nada na tela. Serve exatamente para o que interessa aqui —
saber se a janela monta e se os campos conversam com o `Config`.

Nenhum teste chama `_salvar()`: ele grava no `config.json` real do usuário.
"""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6", reason="interface gráfica não instalada")

from PySide6.QtWidgets import QApplication, QLineEdit, QTabWidget  # noqa: E402

from config import Config  # noqa: E402
from tela_configuracoes import TelaConfiguracoes  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def config_de_teste(tmp_path):
    pastas = {}
    for nome in ("playlists", "acervo", "compartilhada"):
        caminho = tmp_path / nome
        caminho.mkdir()
        pastas[nome] = str(caminho)

    config = Config(
        pasta_mae_playlists=pastas["playlists"],
        pasta_mae_acervo=pastas["acervo"],
        pasta_compartilhada=pastas["compartilhada"],
        slskd_api_key="chave-de-teste",
        spotify_client_id="id-publico",
        spotify_client_secret="segredo",
        quantidade_por_faixa=3,
    )
    config.confirmar_compartilhada()
    return config


def test_a_janela_monta(app, config_de_teste):
    tela = TelaConfiguracoes(config_de_teste)
    assert tela.windowTitle().startswith("Soulseek Auto Downloader")


def test_tem_as_cinco_abas(app, config_de_teste):
    tela = TelaConfiguracoes(config_de_teste)
    (widget_abas,) = tela.findChildren(QTabWidget)
    titulos = [widget_abas.tabText(i) for i in range(widget_abas.count())]

    assert len(titulos) == 5
    for esperado in ("Pastas", "Soulseek", "Spotify", "Qualidade", "Requisitos"):
        assert any(esperado in t for t in titulos), esperado


def test_os_campos_nascem_preenchidos_com_a_configuracao(app, config_de_teste):
    tela = TelaConfiguracoes(config_de_teste)

    assert tela.mae_playlists.valor() == config_de_teste.pasta_mae_playlists
    assert tela.mae_acervo.valor() == config_de_teste.pasta_mae_acervo
    assert tela.compartilhada.valor() == config_de_teste.pasta_compartilhada
    assert tela.spotify_id.text() == "id-publico"
    assert tela.quantidade.value() == 3


def test_o_que_a_tela_recolhe_bate_com_o_que_recebeu(app, config_de_teste):
    tela = TelaConfiguracoes(config_de_teste)
    recolhida = tela._recolher_da_tela()

    assert recolhida.pasta_mae_playlists == config_de_teste.pasta_mae_playlists
    assert recolhida.pasta_mae_acervo == config_de_teste.pasta_mae_acervo
    assert recolhida.pasta_compartilhada == config_de_teste.pasta_compartilhada
    assert set(recolhida.formatos_aceitos) == set(config_de_teste.formatos_aceitos)


def test_as_duas_pastas_mae_sao_campos_separados(app, config_de_teste):
    # Misturar playlist baixada com substituição de acervo foi justamente o que
    # o usuário pediu para NÃO acontecer.
    tela = TelaConfiguracoes(config_de_teste)
    assert tela.mae_playlists.valor() != tela.mae_acervo.valor()


def test_mexer_num_campo_chega_na_configuracao(app, config_de_teste):
    tela = TelaConfiguracoes(config_de_teste)
    tela.quantidade.setValue(5)
    tela.slskd_url.setText("http://outro:9999")
    tela.spotify_id.setText("outro-id")

    recolhida = tela._recolher_da_tela()
    assert recolhida.quantidade_por_faixa == 5
    assert recolhida.slskd_url == "http://outro:9999"
    assert recolhida.spotify_client_id == "outro-id"


def test_desmarcar_formato_tira_ele_da_configuracao(app, config_de_teste):
    tela = TelaConfiguracoes(config_de_teste)
    tela.caixas_formato["mp3"].setChecked(False)
    assert "mp3" not in tela._recolher_da_tela().formatos_aceitos


@pytest.mark.parametrize("campo", ["slskd_chave", "spotify_secret"])
def test_os_segredos_ficam_escondidos_na_tela(app, config_de_teste, campo):
    tela = TelaConfiguracoes(config_de_teste)
    assert getattr(tela, campo).echoMode() == QLineEdit.EchoMode.Password


def test_o_client_id_do_spotify_fica_visivel(app, config_de_teste):
    # Client ID é público por desenho — aparece na URL de autorização. Esconder só
    # atrapalharia o usuário conferir se colou certo.
    tela = TelaConfiguracoes(config_de_teste)
    assert tela.spotify_id.echoMode() == QLineEdit.EchoMode.Normal


def test_configuracao_completa_mostra_que_esta_completa(app, config_de_teste):
    tela = TelaConfiguracoes(config_de_teste)
    assert "completa" in tela.painel_pendencias.toPlainText().lower()


def test_configuracao_zerada_lista_as_pendencias(app, tmp_path):
    tela = TelaConfiguracoes(Config())
    texto = tela.painel_pendencias.toPlainText()
    assert "compartilhar" in texto


# ------------------------------------------ revalidação da compartilhada


def test_pasta_nunca_confirmada_aparece_na_tela(app, tmp_path):
    compartilhada = tmp_path / "compartilhada"
    compartilhada.mkdir()
    tela = TelaConfiguracoes(Config(pasta_compartilhada=str(compartilhada)))

    assert "Nunca confirmada" in tela.rotulo_confirmacao.text()


def test_confirmada_hoje_aparece_na_tela(app, config_de_teste):
    tela = TelaConfiguracoes(config_de_teste)
    assert "Confirmada hoje" in tela.rotulo_confirmacao.text()


def test_o_botao_de_confirmar_zera_o_prazo(app, tmp_path):
    compartilhada = tmp_path / "compartilhada"
    compartilhada.mkdir()
    config = Config(pasta_compartilhada=str(compartilhada))
    tela = TelaConfiguracoes(config)
    assert config.precisa_revalidar_compartilhada()

    tela._confirmar_compartilhada()

    assert not config.precisa_revalidar_compartilhada()
    assert "Confirmada hoje" in tela.rotulo_confirmacao.text()


def test_nao_deixa_confirmar_pasta_que_nao_existe(app, tmp_path):
    # Chama a DECISÃO, não o clique: o clique abre QMessageBox, que é modal e deixaria
    # o teste pendurado para sempre esperando alguém apertar OK.
    config = Config(pasta_compartilhada=str(tmp_path / "nao_existe"))
    tela = TelaConfiguracoes(config)

    assert "não existe" in tela._impedimento_para_confirmar()
    assert config.precisa_revalidar_compartilhada()


def test_nao_deixa_confirmar_sem_escolher_pasta(app):
    tela = TelaConfiguracoes(Config())
    assert "Escolha uma pasta" in tela._impedimento_para_confirmar()


def test_pasta_valida_nao_tem_impedimento(app, config_de_teste):
    tela = TelaConfiguracoes(config_de_teste)
    assert tela._impedimento_para_confirmar() == ""


# ----------------------------------------------------------- limites e pastas


def test_o_limite_de_buscas_nao_deixa_passar_de_34(app, config_de_teste):
    tela = TelaConfiguracoes(config_de_teste)
    tela.buscas_janela.setValue(999)
    assert tela.buscas_janela.value() == 34


def test_a_janela_da_busca_nao_desce_de_220_segundos(app, config_de_teste):
    tela = TelaConfiguracoes(config_de_teste)
    tela.janela_s.setValue(10)
    assert tela.janela_s.value() == 220


def test_o_seletor_de_pasta_oferece_criar_quando_a_pasta_nao_existe(app, tmp_path):
    tela = TelaConfiguracoes(Config())
    tela.mae_playlists.definir(str(tmp_path / "ainda_nao_existe"))
    assert tela.mae_playlists.criar.isEnabled()


def test_o_seletor_nao_oferece_criar_o_que_ja_existe(app, tmp_path):
    tela = TelaConfiguracoes(Config())
    tela.mae_playlists.definir(str(tmp_path))
    assert not tela.mae_playlists.criar.isEnabled()


def test_criar_a_pasta_funciona(app, tmp_path):
    nova = tmp_path / "nova" / "mais_funda"
    tela = TelaConfiguracoes(Config())
    tela.mae_playlists.definir(str(nova))
    tela.mae_playlists._criar()

    assert nova.is_dir()
    assert not tela.mae_playlists.criar.isEnabled()
