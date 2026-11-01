"""Várias pastas compartilhadas, não uma só.

Acervo de DJ não mora num lugar só — são discos diferentes, por gênero, por ano. E
compartilhar mais é do interesse de quem baixa: quanto mais você oferece, menos gente
te bloqueia e mais downloads completam.

A armadilha do formato está registrada em teste aqui porque ela não dá erro: no
`slskd.yml`, `filters:` é **irmã** de `directories:` e vem indentada igual. Tratar
"linha que não começa na coluna zero" como "ainda estou na lista" fazia a troca engolir
os filtros do usuário junto.
"""

import os

import pytest

import slskd_config
from config import Config

MODELO = """soulseek:
  username: joaoflores
  password: x

shares:
  directories:
    - D:\\Musicas
    - E:\\Techno
  filters:
    - \\.ini$
    - Thumbs.db$

web:
  port: 5030
"""


@pytest.fixture
def yml(tmp_path):
    caminho = tmp_path / "slskd.yml"
    caminho.write_text(MODELO, encoding="utf-8")
    return caminho


# ----------------------------------------------------------------- ler


def test_le_todas_as_pastas(yml):
    assert slskd_config.ler_compartilhadas(yml) == [r"D:\Musicas", r"E:\Techno"]


def test_os_filtros_nao_entram_como_pasta(yml):
    # `filters:` tem o mesmo recuo de `directories:` — é por aqui que o erro entra.
    for achada in slskd_config.ler_compartilhadas(yml):
        assert "Thumbs" not in achada and ".ini" not in achada


def test_ler_uma_so_continua_devolvendo_a_primeira(yml):
    assert slskd_config.ler_compartilhada(yml) == r"D:\Musicas"


# --------------------------------------------------------------- gravar


def test_grava_a_lista_inteira(yml):
    slskd_config.gravar(pastas=[r"D:\A", r"D:\B", r"D:\C"], caminho=yml)

    assert slskd_config.ler_compartilhadas(yml) == [r"D:\A", r"D:\B", r"D:\C"]


def test_tirar_uma_pasta_realmente_tira(yml):
    """Trocar só o primeiro item deixava as outras penduradas no arquivo.

    Quem tira uma pasta da lista na janela espera que ela saia do slskd — e ela
    continuava sendo oferecida à rede.
    """
    slskd_config.gravar(pastas=[r"D:\Musicas"], caminho=yml)

    assert slskd_config.ler_compartilhadas(yml) == [r"D:\Musicas"]
    assert "E:\\Techno" not in yml.read_text(encoding="utf-8")


def test_os_filtros_sobrevivem_a_gravacao(yml):
    slskd_config.gravar(pastas=[r"D:\A"], caminho=yml)
    texto = yml.read_text(encoding="utf-8")

    assert "Thumbs.db$" in texto
    assert "\\.ini$" in texto
    assert "port: 5030" in texto


def test_lista_vazia_nao_apaga_o_que_estava_la(yml):
    # Mesma regra da senha: campo vazio não apaga. Lista vazia aqui seria um acidente.
    slskd_config.gravar(pastas=[], caminho=yml)

    assert slskd_config.ler_compartilhadas(yml) == [r"D:\Musicas", r"E:\Techno"]


def test_uma_pasta_so_continua_funcionando(yml):
    slskd_config.gravar(pasta=r"D:\Nova", caminho=yml)

    assert slskd_config.ler_compartilhadas(yml) == [r"D:\Nova"]


def test_o_recuo_da_lista_e_preservado(yml):
    slskd_config.gravar(pastas=[r"D:\A", r"D:\B"], caminho=yml)

    for linha in yml.read_text(encoding="utf-8").splitlines():
        if linha.strip().startswith("- D:"):
            assert linha.startswith("    - "), linha


# --------------------------------------------------------------- Config


def test_config_guarda_varias():
    c = Config()
    c.definir_compartilhadas([r"D:\A", r"D:\B"])

    assert c.todas_as_compartilhadas() == [r"D:\A", r"D:\B"]
    assert c.pasta_compartilhada == r"D:\A", "a primeira continua sendo 'a' pasta"


def test_config_antiga_com_uma_pasta_continua_respondendo():
    # Config gravada antes deste recurso não tem a lista — e não pode virar vazia.
    c = Config(pasta_compartilhada=r"D:\Antiga")

    assert c.todas_as_compartilhadas() == [r"D:\Antiga"]


def test_repetida_e_vazia_nao_entram():
    c = Config()
    c.definir_compartilhadas([r"D:\A", "  ", r"D:\A", "", r"D:\B"])

    assert c.todas_as_compartilhadas() == [r"D:\A", r"D:\B"]


def test_a_lista_sobrevive_ao_disco(tmp_path):
    # O caminho vai SEMPRE explícito. `salvar()` sem caminho grava no config.json de
    # verdade do usuário — foi o que aconteceu aqui, e apagou as pastas dele.
    arquivo = tmp_path / "config.json"
    c = Config()
    c.definir_compartilhadas([r"D:\A", r"D:\B"])
    c.salvar(arquivo)

    assert Config.carregar(arquivo).todas_as_compartilhadas() == [r"D:\A", r"D:\B"]


def test_pasta_que_sumiu_e_reportada(tmp_path):
    existe = tmp_path / "tem"
    existe.mkdir()
    c = Config(pasta_mae_playlists=str(existe), pasta_mae_acervo=str(existe))
    c.definir_compartilhadas([str(existe), str(tmp_path / "sumiu")])
    c.confirmar_compartilhada()

    assert any("sumiram" in p for p in c.problemas())


# ------------------------------------------------------------- a janela


def test_a_janela_mostra_e_devolve_a_lista(tmp_path):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    pytest.importorskip("PySide6", reason="interface gráfica não instalada")
    from PySide6.QtWidgets import QApplication

    from tela_configuracoes import ListaDePastas

    QApplication.instance() or QApplication([])
    lista = ListaDePastas("escolha")
    lista.definir([r"D:\A", r"D:\B"])

    assert lista.valores() == [r"D:\A", r"D:\B"]
    assert lista.valor() == r"D:\A"

    lista.lista.setCurrentRow(0)
    lista._tirar()
    assert lista.valores() == [r"D:\B"]


def test_a_janela_aceita_uma_pasta_so_em_texto():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    pytest.importorskip("PySide6", reason="interface gráfica não instalada")
    from PySide6.QtWidgets import QApplication

    from tela_configuracoes import ListaDePastas

    QApplication.instance() or QApplication([])
    lista = ListaDePastas("escolha")
    lista.definir(r"D:\Sozinha")  # config antiga chega como texto

    assert lista.valores() == [r"D:\Sozinha"]
