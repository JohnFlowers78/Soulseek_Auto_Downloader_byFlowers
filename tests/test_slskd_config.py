"""Testes da gravação do `slskd.yml`.

Nenhum teste encosta no slskd.yml real: todos escrevem em `tmp_path`.
"""

from pathlib import Path

import pytest

import slskd_config

MODELO = """soulseek:
  username: COLOQUE_AQUI_SEU_USUARIO_SOULSEEK
  password: COLOQUE_AQUI_SUA_SENHA_SOULSEEK
  listen_port: 50300

shares:
  directories:
    - COLOQUE_AQUI_A_PASTA_QUE_VOCE_VAI_COMPARTILHAR
  filters:
    - Thumbs.db$

web:
  port: 5030
  authentication:
    username: slskd
    password: slskd
"""


@pytest.fixture
def yml(tmp_path) -> Path:
    caminho = tmp_path / "slskd.yml"
    caminho.write_text(MODELO, encoding="utf-8")
    return caminho


# ------------------------------------------------------------------ ler


def test_marcador_nao_conta_como_valor(yml):
    # Um campo com COLOQUE_AQUI está vazio, não preenchido.
    assert slskd_config.ler_valor("username", yml) == ""
    assert slskd_config.ler_compartilhada(yml) == ""


def test_lista_o_que_falta(yml):
    assert set(slskd_config.pendencias(yml)) == {"usuario", "senha", "pasta"}


def test_sem_arquivo_tudo_esta_pendente(tmp_path):
    assert set(slskd_config.pendencias(tmp_path / "nao_existe.yml")) == {
        "usuario",
        "senha",
        "pasta",
    }


# ---------------------------------------------------------------- gravar


def test_grava_os_tres_campos(yml):
    slskd_config.gravar("joaoflores", "senha123", r"D:\Musicas", yml)

    assert slskd_config.ler_valor("username", yml) == "joaoflores"
    assert slskd_config.ler_valor("password", yml) == "senha123"
    assert slskd_config.ler_compartilhada(yml) == r"D:\Musicas"
    assert slskd_config.pendencias(yml) == []


def test_campo_vazio_nao_apaga_o_que_ja_estava(yml):
    """A senha chega sempre em branco da tela — o campo é mascarado.

    Sem esta regra, cada gravação de rotina apagaria a senha do arquivo: o mesmo
    acidente que já custou o refresh token do Spotify neste projeto.
    """
    slskd_config.gravar("joaoflores", "senha123", r"D:\Musicas", yml)
    slskd_config.gravar(usuario="outro", caminho=yml)

    assert slskd_config.ler_valor("username", yml) == "outro"
    assert slskd_config.ler_valor("password", yml) == "senha123"
    assert slskd_config.ler_compartilhada(yml) == r"D:\Musicas"


def test_guarda_copia_do_anterior(yml):
    slskd_config.gravar("joaoflores", "x", r"D:\M", yml)
    reserva = yml.with_suffix(".yml.anterior")

    assert reserva.is_file()
    assert "COLOQUE_AQUI" in reserva.read_text(encoding="utf-8")


def test_o_resto_do_arquivo_fica_intacto(yml):
    slskd_config.gravar("joaoflores", "x", r"D:\M", yml)
    texto = yml.read_text(encoding="utf-8")

    # A senha da interface web do slskd não pode ser confundida com a do Soulseek:
    # as duas chaves se chamam "password".
    assert "listen_port: 50300" in texto
    assert "port: 5030" in texto
    assert "Thumbs.db$" in texto
    assert texto.count("password:") == 2


def test_a_senha_do_soulseek_e_a_primeira_e_nao_a_da_interface_web(yml):
    slskd_config.gravar(senha="segredo-do-soulseek", caminho=yml)
    linhas = yml.read_text(encoding="utf-8").splitlines()

    (primeira,) = [i for i, l in enumerate(linhas) if "password: segredo-do-soulseek" in l]
    (web,) = [i for i, l in enumerate(linhas) if "password: slskd" in l]
    assert primeira < web, "a do Soulseek vem antes; trocar a errada derruba o login"


def test_o_recuo_da_pasta_e_preservado(yml):
    slskd_config.gravar(pasta=r"D:\Musicas\House", caminho=yml)
    (linha,) = [l for l in yml.read_text(encoding="utf-8").splitlines() if "House" in l]

    assert linha.startswith("    - "), "YAML quebra se o recuo mudar"


def test_caminho_com_espaco_e_acento_sobrevive(yml):
    pasta = r"C:\Users\Flores Dev Projects\Music\Músicas antigas\DeepHouse - House"
    slskd_config.gravar(pasta=pasta, caminho=yml)

    assert slskd_config.ler_compartilhada(yml) == pasta


def test_gravar_sem_arquivo_avisa(tmp_path):
    with pytest.raises(FileNotFoundError) as erro:
        slskd_config.gravar("x", "y", "z", caminho=tmp_path / "nao_existe.yml")
    assert "INSTALACAO" in str(erro.value)


def test_gravar_duas_vezes_nao_duplica_linha(yml):
    slskd_config.gravar("um", "a", r"D:\1", yml)
    slskd_config.gravar("dois", "b", r"D:\2", yml)
    texto = yml.read_text(encoding="utf-8")

    assert texto.count("username:") == 2  # a do Soulseek e a da interface web
    assert slskd_config.ler_valor("username", yml) == "dois"
