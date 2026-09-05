"""Testes das configurações.

Todo teste que grava usa `tmp_path`: nenhum encosta no `config.json` real do usuário.
"""

import json

import pytest

from config import FORMATOS_PADRAO, Config


def completa(tmp_path) -> Config:
    """Uma configuração sem pendência nenhuma, com pastas que existem de verdade."""
    destino = tmp_path / "destino"
    compartilhada = tmp_path / "compartilhada"
    destino.mkdir(exist_ok=True)
    compartilhada.mkdir(exist_ok=True)
    return Config(
        pasta_destino=str(destino),
        pasta_compartilhada=str(compartilhada),
        slskd_api_key="chave-de-teste",
    )


# ------------------------------------------------------------------ arquivo


def test_arquivo_inexistente_devolve_os_padroes(tmp_path):
    config = Config.carregar(tmp_path / "nao_existe.json")
    assert config.formatos_aceitos == FORMATOS_PADRAO
    assert config.buscas_por_janela == 34


def test_salvar_e_carregar_preserva_tudo(tmp_path):
    caminho = tmp_path / "config.json"
    original = Config(
        pasta_destino=r"D:\Musicas",
        pasta_compartilhada=r"D:\Compartilhada",
        slskd_api_key="segredo",
        quantidade_por_faixa=3,
    )
    original.salvar(caminho)

    lida = Config.carregar(caminho)
    assert lida == original


def test_salvar_cria_a_pasta_se_preciso(tmp_path):
    caminho = tmp_path / "uma" / "outra" / "config.json"
    Config().salvar(caminho)
    assert caminho.is_file()


def test_salvar_devolve_onde_gravou(tmp_path):
    caminho = tmp_path / "config.json"
    assert Config().salvar(caminho) == caminho


def test_json_estragado_devolve_os_padroes_em_vez_de_estourar(tmp_path):
    caminho = tmp_path / "config.json"
    caminho.write_text("{isso não é json", encoding="utf-8")
    assert Config.carregar(caminho).buscas_por_janela == 34


def test_json_que_nao_e_objeto_devolve_os_padroes(tmp_path):
    caminho = tmp_path / "config.json"
    caminho.write_text("[1, 2, 3]", encoding="utf-8")
    assert Config.carregar(caminho) == Config()


def test_chave_desconhecida_e_ignorada(tmp_path):
    # Uma versão velha do app tem que conseguir ler a configuração da versão nova.
    caminho = tmp_path / "config.json"
    caminho.write_text(
        json.dumps({"pasta_destino": "D:/x", "campo_do_futuro": 42}), encoding="utf-8"
    )
    config = Config.carregar(caminho)
    assert config.pasta_destino == "D:/x"
    assert not hasattr(config, "campo_do_futuro")


def test_chave_faltando_fica_no_padrao(tmp_path):
    # E a versão nova tem que conseguir ler a da velha.
    caminho = tmp_path / "config.json"
    caminho.write_text(json.dumps({"pasta_destino": "D:/x"}), encoding="utf-8")
    assert Config.carregar(caminho).janela_de_buscas_s == 220


def test_acentos_sobrevivem_ao_arquivo(tmp_path):
    caminho = tmp_path / "config.json"
    Config(pasta_destino=r"D:\Músicas\Sertão").salvar(caminho)
    assert Config.carregar(caminho).pasta_destino == r"D:\Músicas\Sertão"


# ---------------------------------------------------------------- pendências


def test_configuracao_zerada_tem_pendencias():
    problemas = Config().problemas()
    assert problemas
    assert not Config().pronto


def test_configuracao_completa_nao_tem_pendencia(tmp_path):
    assert completa(tmp_path).problemas() == []
    assert completa(tmp_path).pronto


def test_falta_de_pasta_compartilhada_explica_a_consequencia(tmp_path):
    config = completa(tmp_path)
    config.pasta_compartilhada = ""
    (problema,) = [p for p in config.problemas() if "compartilhar" in p]
    # A mensagem tem que dizer o que acontece, não só que falta preencher.
    assert "bloqueiam" in problema


def test_pasta_que_nao_existe_e_apontada(tmp_path):
    config = completa(tmp_path)
    config.pasta_destino = str(tmp_path / "sumiu")
    assert any("não existe" in p for p in config.problemas())


def test_falta_de_chave_do_slskd_diz_onde_achar(tmp_path):
    config = completa(tmp_path)
    config.slskd_api_key = ""
    (problema,) = [p for p in config.problemas() if "chave" in p]
    assert "slskd.yml" in problema


def test_sem_nenhum_formato_marcado_e_pendencia(tmp_path):
    config = completa(tmp_path)
    config.formatos_aceitos = []
    assert any("formato" in p for p in config.problemas())


@pytest.mark.parametrize(
    "buscas, janela", [(50, 220), (34, 100), (40, 60)]
)
def test_limite_de_busca_agressivo_e_avisado(tmp_path, buscas, janela):
    # Mexer nisso para cima é pedir banimento de 30 minutos.
    config = completa(tmp_path)
    config.buscas_por_janela = buscas
    config.janela_de_buscas_s = janela
    assert any("banimento" in p for p in config.problemas())


def test_o_limite_padrao_nao_dispara_aviso(tmp_path):
    assert not any("banimento" in p for p in completa(tmp_path).problemas())


def test_chave_de_api_nao_aparece_nas_pendencias(tmp_path):
    # Mensagem de tela não é lugar de segredo.
    config = completa(tmp_path)
    config.pasta_destino = ""
    assert all("chave-de-teste" not in p for p in config.problemas())
