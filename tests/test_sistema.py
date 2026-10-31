"""Testes do módulo que isola o que muda entre Windows e macOS."""

import sys
from pathlib import Path

import sistema


def test_a_pasta_de_dados_leva_o_nome_do_app():
    assert sistema.pasta_de_dados().name == sistema.NOME_DO_APP


def test_a_pasta_de_dados_e_absoluta():
    # Caminho relativo aqui viraria pasta de dados dependente de onde o app foi aberto.
    assert sistema.pasta_de_dados().is_absolute()


def test_a_pasta_de_dados_fica_fora_da_pasta_do_programa():
    # É o que permite o atualizador trocar o programa sem encostar nos dados.
    programa = Path(__file__).resolve().parent.parent
    assert programa not in sistema.pasta_de_dados().resolve().parents


def test_so_um_sistema_por_vez():
    assert not (sistema.eh_windows() and sistema.eh_mac())


def test_o_nome_do_sistema_e_legivel():
    assert sistema.nome_do_sistema() in ("Windows", "macOS", sys.platform)


def test_a_pasta_de_musicas_padrao_fica_dentro_da_casa_do_usuario():
    assert Path.home() in sistema.pasta_de_musicas_padrao().parents


def test_acha_um_programa_que_existe():
    # O próprio Python está no PATH — serve de cobaia sem depender de nada instalado.
    nome = "python" if sistema.eh_windows() else "python3"
    assert sistema.encontrar_programa(nome) is not None


def test_programa_inexistente_devolve_nada_em_vez_de_estourar():
    assert sistema.encontrar_programa("programa_que_nao_existe_xyz_123") is None


def test_procurar_ffmpeg_nao_estoura_mesmo_sem_ffmpeg():
    # Pode devolver None nesta máquina — o que não pode é levantar exceção.
    resultado = sistema.encontrar_ffmpeg()
    assert resultado is None or resultado.is_file()


def test_procurar_slskd_nao_estoura_mesmo_sem_slskd():
    resultado = sistema.encontrar_slskd()
    assert resultado is None or resultado.is_file()


def test_procura_fora_do_path_acha_o_que_esta_no_disco(tmp_path):
    # O caso que motivou a busca em disco: o programa existe, mas o PATH deste processo
    # é antigo e não o enxerga. Acontece sempre depois do botão "instalar dependência".
    falso = tmp_path / "bin"
    falso.mkdir()
    alvo = falso / ("coisa.exe" if sistema.eh_windows() else "coisa")
    alvo.write_bytes(b"\0")

    assert sistema.encontrar_programa("coisa", (falso,)) == alvo


def test_procura_fora_do_path_devolve_nada_quando_nao_ha(tmp_path):
    assert sistema.encontrar_programa("coisa", (tmp_path,)) is None


def test_a_pasta_do_slskd_e_a_mesma_que_ele_usa_por_padrao():
    # Precisamos achar o slskd.yml para conferir se as credenciais já foram preenchidas.
    pasta = sistema.pasta_de_dados_do_slskd()
    assert pasta.name == "slskd"
    assert pasta.is_absolute()
