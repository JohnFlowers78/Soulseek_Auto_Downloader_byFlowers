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

from PySide6.QtWidgets import QApplication  # noqa: E402

from config import Config  # noqa: E402
from tela_configuracoes import TelaConfiguracoes  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def config_de_teste(tmp_path):
    destino = tmp_path / "destino"
    compartilhada = tmp_path / "compartilhada"
    destino.mkdir()
    compartilhada.mkdir()
    return Config(
        pasta_destino=str(destino),
        pasta_compartilhada=str(compartilhada),
        slskd_api_key="chave-de-teste",
        quantidade_por_faixa=3,
    )


def test_a_janela_monta(app, config_de_teste):
    tela = TelaConfiguracoes(config_de_teste)
    assert tela.windowTitle().startswith("Soulseek Auto Downloader")


def test_tem_as_quatro_abas(app, config_de_teste):
    from PySide6.QtWidgets import QTabWidget

    tela = TelaConfiguracoes(config_de_teste)
    (widget_abas,) = tela.findChildren(QTabWidget)
    titulos = [widget_abas.tabText(i) for i in range(widget_abas.count())]
    assert len(titulos) == 4
    assert any("Pastas" in t for t in titulos)
    assert any("Soulseek" in t for t in titulos)


def test_os_campos_nascem_preenchidos_com_a_configuracao(app, config_de_teste):
    tela = TelaConfiguracoes(config_de_teste)

    assert tela.destino.valor() == config_de_teste.pasta_destino
    assert tela.compartilhada.valor() == config_de_teste.pasta_compartilhada
    assert tela.slskd_chave.text() == "chave-de-teste"
    assert tela.quantidade.value() == 3


def test_o_que_a_tela_recolhe_bate_com_o_que_recebeu(app, config_de_teste):
    tela = TelaConfiguracoes(config_de_teste)
    recolhida = tela._recolher_da_tela()

    assert recolhida.pasta_destino == config_de_teste.pasta_destino
    assert recolhida.pasta_compartilhada == config_de_teste.pasta_compartilhada
    assert set(recolhida.formatos_aceitos) == set(config_de_teste.formatos_aceitos)


def test_mexer_num_campo_chega_na_configuracao(app, config_de_teste):
    tela = TelaConfiguracoes(config_de_teste)
    tela.quantidade.setValue(5)
    tela.slskd_url.setText("http://outro:9999")

    recolhida = tela._recolher_da_tela()
    assert recolhida.quantidade_por_faixa == 5
    assert recolhida.slskd_url == "http://outro:9999"


def test_desmarcar_formato_tira_ele_da_configuracao(app, config_de_teste):
    tela = TelaConfiguracoes(config_de_teste)
    tela.caixas_formato["mp3"].setChecked(False)
    assert "mp3" not in tela._recolher_da_tela().formatos_aceitos


def test_a_chave_de_api_fica_escondida_na_tela(app, config_de_teste):
    from PySide6.QtWidgets import QLineEdit

    tela = TelaConfiguracoes(config_de_teste)
    assert tela.slskd_chave.echoMode() == QLineEdit.EchoMode.Password


def test_configuracao_completa_mostra_que_esta_completa(app, config_de_teste):
    tela = TelaConfiguracoes(config_de_teste)
    assert "completa" in tela.painel_pendencias.toPlainText().lower()


def test_configuracao_zerada_lista_as_pendencias(app, tmp_path):
    tela = TelaConfiguracoes(Config())
    texto = tela.painel_pendencias.toPlainText()
    assert "compartilhar" in texto


def test_o_limite_de_buscas_nao_deixa_passar_de_34(app, config_de_teste):
    # A tela impede antes de o `Config.problemas()` precisar reclamar.
    tela = TelaConfiguracoes(config_de_teste)
    tela.buscas_janela.setValue(999)
    assert tela.buscas_janela.value() == 34


def test_a_janela_da_busca_nao_desce_de_220_segundos(app, config_de_teste):
    tela = TelaConfiguracoes(config_de_teste)
    tela.janela_s.setValue(10)
    assert tela.janela_s.value() == 220


def test_o_seletor_de_pasta_oferece_criar_quando_a_pasta_nao_existe(app, tmp_path):
    tela = TelaConfiguracoes(Config())
    tela.destino.definir(str(tmp_path / "ainda_nao_existe"))
    assert tela.destino.criar.isEnabled()


def test_o_seletor_nao_oferece_criar_o_que_ja_existe(app, tmp_path):
    tela = TelaConfiguracoes(Config())
    tela.destino.definir(str(tmp_path))
    assert not tela.destino.criar.isEnabled()


def test_criar_a_pasta_funciona(app, tmp_path):
    nova = tmp_path / "nova" / "mais_funda"
    tela = TelaConfiguracoes(Config())
    tela.destino.definir(str(nova))
    tela.destino._criar()

    assert nova.is_dir()
    assert not tela.destino.criar.isEnabled()
