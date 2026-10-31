"""Testes das configurações.

Todo teste que grava usa `tmp_path`: nenhum encosta no `config.json` real do usuário.
A revalidação da pasta compartilhada é testada com relógio injetado — nada de esperar
30 dias nem de mexer no relógio da máquina.
"""

import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from config import DIAS_ATE_REVALIDAR_COMPARTILHADA, FORMATOS_PADRAO, Config

HOJE = datetime(2026, 10, 31, 12, 0, 0)


def completa(tmp_path, agora: datetime = HOJE) -> Config:
    """Uma configuração sem pendência nenhuma, com pastas que existem de verdade."""
    pastas = {}
    for nome in ("playlists", "acervo", "compartilhada"):
        caminho = tmp_path / nome
        caminho.mkdir(exist_ok=True)
        pastas[nome] = str(caminho)

    config = Config(
        pasta_mae_playlists=pastas["playlists"],
        pasta_mae_acervo=pastas["acervo"],
        pasta_compartilhada=pastas["compartilhada"],
        slskd_api_key="chave-de-teste",
    )
    config.confirmar_compartilhada(agora)
    return config


# ------------------------------------------------------------------ arquivo


def test_arquivo_inexistente_devolve_os_padroes(tmp_path):
    config = Config.carregar(tmp_path / "nao_existe.json")
    assert config.formatos_aceitos == FORMATOS_PADRAO
    assert config.buscas_por_janela == 34


def test_salvar_e_carregar_preserva_tudo(tmp_path):
    caminho = tmp_path / "config.json"
    original = Config(
        pasta_mae_playlists=r"D:\Musicas\Playlists",
        pasta_mae_acervo=r"D:\Musicas\Acervo",
        pasta_compartilhada=r"D:\Compartilhada",
        slskd_api_key="segredo",
        spotify_client_id="abc123",
        quantidade_por_faixa=3,
    )
    original.salvar(caminho)

    assert Config.carregar(caminho) == original


def test_salvar_cria_a_pasta_se_preciso(tmp_path):
    caminho = tmp_path / "uma" / "outra" / "config.json"
    Config().salvar(caminho)
    assert caminho.is_file()


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
        json.dumps({"pasta_mae_playlists": "D:/x", "campo_do_futuro": 42}), encoding="utf-8"
    )
    config = Config.carregar(caminho)
    assert config.pasta_mae_playlists == "D:/x"
    assert not hasattr(config, "campo_do_futuro")


def test_chave_faltando_fica_no_padrao(tmp_path):
    caminho = tmp_path / "config.json"
    caminho.write_text(json.dumps({"pasta_mae_playlists": "D:/x"}), encoding="utf-8")
    assert Config.carregar(caminho).janela_de_buscas_s == 220


def test_acentos_sobrevivem_ao_arquivo(tmp_path):
    caminho = tmp_path / "config.json"
    Config(pasta_mae_playlists=r"D:\Músicas\Sertão").salvar(caminho)
    assert Config.carregar(caminho).pasta_mae_playlists == r"D:\Músicas\Sertão"


# ---------------------------------------------------------- pasta da playlist


def test_cada_playlist_vira_subpasta_da_mae():
    config = Config(pasta_mae_playlists=r"D:\Musicas\Playlists")
    assert config.pasta_da_playlist("Set de Verão") == Path(r"D:\Musicas\Playlists\Set de Verão")


# ---------------------------------------------------------------- pendências


def test_configuracao_zerada_tem_pendencias():
    assert Config().problemas()
    assert not Config().pronto


def test_configuracao_completa_nao_tem_pendencia(tmp_path):
    assert completa(tmp_path).problemas(agora=HOJE) == []


def test_as_duas_pastas_mae_sao_cobradas_separadamente(tmp_path):
    config = completa(tmp_path)
    config.pasta_mae_playlists = ""
    config.pasta_mae_acervo = ""
    problemas = config.problemas(agora=HOJE)

    assert any("pasta das playlists" in p for p in problemas)
    assert any("pasta do acervo" in p for p in problemas)


def test_pasta_mae_que_nao_existe_e_apontada(tmp_path):
    config = completa(tmp_path)
    config.pasta_mae_playlists = str(tmp_path / "sumiu")
    assert any("não existe" in p for p in config.problemas(agora=HOJE))


def test_falta_de_chave_do_slskd_diz_onde_achar(tmp_path):
    config = completa(tmp_path)
    config.slskd_api_key = ""
    (problema,) = [p for p in config.problemas(agora=HOJE) if "chave" in p]
    assert "slskd.yml" in problema


def test_sem_nenhum_formato_marcado_e_pendencia(tmp_path):
    config = completa(tmp_path)
    config.formatos_aceitos = []
    assert any("formato" in p for p in config.problemas(agora=HOJE))


@pytest.mark.parametrize("buscas, janela", [(50, 220), (34, 100), (40, 60)])
def test_limite_de_busca_agressivo_e_avisado(tmp_path, buscas, janela):
    config = completa(tmp_path)
    config.buscas_por_janela = buscas
    config.janela_de_buscas_s = janela
    assert any("banimento" in p for p in config.problemas(agora=HOJE))


def test_o_limite_padrao_nao_dispara_aviso(tmp_path):
    assert not any("banimento" in p for p in completa(tmp_path).problemas(agora=HOJE))


def test_chave_de_api_nao_aparece_nas_pendencias(tmp_path):
    # Mensagem de tela não é lugar de segredo.
    config = completa(tmp_path)
    config.pasta_mae_playlists = ""
    assert all("chave-de-teste" not in p for p in config.problemas(agora=HOJE))


# ------------------------------------------- revalidação da compartilhada


def test_pasta_compartilhada_nunca_confirmada_precisa_revalidar(tmp_path):
    config = completa(tmp_path)
    config.compartilhada_confirmada_em = ""
    assert config.precisa_revalidar_compartilhada(HOJE)
    assert config.dias_desde_confirmacao(HOJE) is None


def test_confirmada_hoje_nao_precisa_revalidar(tmp_path):
    config = completa(tmp_path, agora=HOJE)
    assert not config.precisa_revalidar_compartilhada(HOJE)
    assert config.dias_desde_confirmacao(HOJE) == 0


def test_no_dia_anterior_ao_prazo_ainda_esta_valida(tmp_path):
    config = completa(tmp_path, agora=HOJE)
    quase = HOJE + timedelta(days=DIAS_ATE_REVALIDAR_COMPARTILHADA - 1)
    assert not config.precisa_revalidar_compartilhada(quase)


def test_no_dia_do_prazo_passa_a_pedir(tmp_path):
    config = completa(tmp_path, agora=HOJE)
    no_prazo = HOJE + timedelta(days=DIAS_ATE_REVALIDAR_COMPARTILHADA)
    assert config.precisa_revalidar_compartilhada(no_prazo)


def test_vencida_vira_pendencia_na_tela(tmp_path):
    config = completa(tmp_path, agora=HOJE)
    depois = HOJE + timedelta(days=DIAS_ATE_REVALIDAR_COMPARTILHADA + 5)
    (problema,) = [p for p in config.problemas(agora=depois) if "Confirme a pasta" in p]

    # A mensagem precisa dizer POR QUE está pedindo, senão vira burocracia irritante.
    assert "param sem dar erro" in problema
    assert "35 dias" in problema


def test_confirmar_de_novo_zera_o_prazo(tmp_path):
    config = completa(tmp_path, agora=HOJE)
    depois = HOJE + timedelta(days=DIAS_ATE_REVALIDAR_COMPARTILHADA + 5)
    assert config.precisa_revalidar_compartilhada(depois)

    config.confirmar_compartilhada(depois)
    assert not config.precisa_revalidar_compartilhada(depois)


def test_data_de_confirmacao_estragada_vale_como_nunca(tmp_path):
    # Lado seguro: na dúvida, pede de novo.
    config = completa(tmp_path)
    config.compartilhada_confirmada_em = "isso não é data"
    assert config.precisa_revalidar_compartilhada(HOJE)


def test_pasta_compartilhada_que_sumiu_e_mais_urgente_que_o_prazo(tmp_path):
    # Se a pasta não existe mais, a mensagem tem que ser essa — não a de "confirme".
    config = completa(tmp_path)
    config.pasta_compartilhada = str(tmp_path / "sumiu")
    problemas = config.problemas(agora=HOJE)

    assert any("sumiu" in p for p in problemas)
    assert not any("Confirme a pasta" in p for p in problemas)


def test_a_confirmacao_sobrevive_ao_arquivo(tmp_path):
    caminho = tmp_path / "config.json"
    config = completa(tmp_path, agora=HOJE)
    config.salvar(caminho)

    lida = Config.carregar(caminho)
    assert lida.dias_desde_confirmacao(HOJE) == 0
