"""Testes da leitura de uma pasta de músicas.

A extração de nome é testada com nomes de arquivo reais de acervo de DJ. A leitura do
ffprobe é testada com JSON escrito à mão — sem ffmpeg instalado e sem áudio de verdade,
porque a lógica está toda em `montar_arquivo_local`, separada da chamada ao programa.

A varredura usa `tmp_path` do pytest: nenhum teste encosta em pasta real do usuário.
"""

from pathlib import Path

import pytest

from leitor_pasta import (
    EXTENSOES_AUDIO,
    extrair_do_nome,
    limpar_nome,
    ler_ffprobe,
    montar_arquivo_local,
    varrer_pasta,
)


# ------------------------------------------------------- nome do arquivo


@pytest.mark.parametrize(
    "nome, esperado",
    [
        ("Artista - Titulo.mp3", ("Artista", "Titulo")),
        ("Bonobo - Kiara.flac", ("Bonobo", "Kiara")),
        ("Djavan - Não Vou Ficar.mp3", ("Djavan", "Não Vou Ficar")),
        ("Céu - Malemolência.wav", ("Céu", "Malemolência")),
    ],
)
def test_separa_artista_e_titulo(nome, esperado):
    assert extrair_do_nome(nome) == esperado


@pytest.mark.parametrize(
    "nome",
    [
        "01 - Artista - Titulo.mp3",
        "01. Artista - Titulo.mp3",
        "1 - Artista - Titulo.mp3",
        "12) Artista - Titulo.mp3",
        "01_Artista_-_Titulo.mp3",
        "A1. Artista - Titulo.mp3",
        "B2 - Artista - Titulo.mp3",
    ],
)
def test_tira_numeracao_de_faixa_de_todo_jeito(nome):
    assert extrair_do_nome(nome) == ("Artista", "Titulo")


@pytest.mark.parametrize(
    "nome, esperado",
    [
        ("50 Cent - In Da Club.mp3", ("50 Cent", "In Da Club")),
        ("2 Unlimited - No Limit.mp3", ("2 Unlimited", "No Limit")),
        ("311 - Down.mp3", ("311", "Down")),
    ],
)
def test_numero_que_e_o_nome_do_artista_nao_e_confundido_com_faixa(nome, esperado):
    # A armadilha: uma regra do tipo "tire qualquer número do começo" transformaria
    # 50 Cent em Cent. Por isso só sai número SEGUIDO de separador, ou com zero à esquerda.
    assert extrair_do_nome(nome) == esperado


def test_o_que_desempata_numeracao_de_nome_de_artista_e_o_que_sobra():
    # "01 - Artista - Titulo" e "311 - Down" têm a MESMA forma. O que separa os dois é o
    # que resta: numeração vem antes de "Artista - Titulo", então sobra um separador.
    # Se não sobra, o número era o próprio artista.
    assert extrair_do_nome("311 - Down.mp3") == ("311", "Down")
    assert extrair_do_nome("311 - Artista - Titulo.mp3") == ("Artista", "Titulo")


def test_lado_de_vinil_sai_mas_a_banda_A1_fica():
    # A mesma regra resolve o vinil sem precisar de regra nova.
    assert extrair_do_nome("A1. Artista - Titulo.mp3") == ("Artista", "Titulo")
    assert extrair_do_nome("A1 - Caught in the Middle.mp3") == ("A1", "Caught in the Middle")


def test_zero_a_esquerda_sai_mesmo_sem_sobrar_separador():
    # "01" e "04" só existem como numeração — nenhum artista se chama assim.
    assert extrair_do_nome("04 Titulo.mp3") == ("", "Titulo")
    assert extrair_do_nome("01 - Titulo.mp3") == ("", "Titulo")


def test_hifen_dentro_do_nome_da_banda_nao_divide():
    # É por isso que o separador exige espaço dos dois lados.
    assert extrair_do_nome("Blink-182 - All the Small Things.mp3") == (
        "Blink-182",
        "All the Small Things",
    )
    assert extrair_do_nome("Jay-Z - 99 Problems.mp3") == ("Jay-Z", "99 Problems")


@pytest.mark.parametrize(
    "nome",
    [
        "Artista – Titulo.mp3",   # meia-risca
        "Artista — Titulo.mp3",   # travessão
        "Artista -- Titulo.mp3",
    ],
)
def test_aceita_os_outros_tracos(nome):
    assert extrair_do_nome(nome) == ("Artista", "Titulo")


@pytest.mark.parametrize(
    "nome",
    [
        "[Label001] Artista - Titulo.mp3",
        "www.baixaki.com_Artista - Titulo.mp3",
        "(www.site.com) Artista - Titulo.mp3",
    ],
)
def test_tira_rotulo_e_site_grudados_no_comeco(nome):
    assert extrair_do_nome(nome) == ("Artista", "Titulo")


@pytest.mark.parametrize(
    "nome",
    [
        "Artista - Titulo (320kbps).mp3",
        "Artista - Titulo [320].mp3",
        "Artista - Titulo [FLAC].flac",
        "Artista - Titulo (V0).mp3",
        "Artista - Titulo - 320kbps.mp3",
    ],
)
def test_tira_selo_de_qualidade_do_fim(nome):
    assert extrair_do_nome(nome) == ("Artista", "Titulo")


@pytest.mark.parametrize(
    "nome, titulo",
    [
        ("Daft Punk - One More Time (Original Mix).wav", "One More Time (Original Mix)"),
        ("Daft Punk - One More Time (Extended Mix).aiff", "One More Time (Extended Mix)"),
        ("Djavan - Se (Ao Vivo).mp3", "Se (Ao Vivo)"),
    ],
)
def test_o_mix_faz_parte_do_nome_e_nao_pode_sair(nome, titulo):
    # "(Original Mix)" não é selo de qualidade — para DJ é o que distingue a faixa.
    # Quem decide removê-lo é o normalizador, na variante certa, não o leitor de pasta.
    assert extrair_do_nome(nome)[1] == titulo


@pytest.mark.parametrize(
    "nome",
    ["Titulo.mp3", "04 Titulo.mp3", "- Titulo.mp3", "Titulo"],
)
def test_sem_artista_devolve_artista_vazio_em_vez_de_chutar(nome):
    # Chutar um artista errado seria pior que não ter nenhum: entraria como termo
    # obrigatório na busca e derrubaria todos os resultados.
    artista, titulo = extrair_do_nome(nome)
    assert artista == ""
    assert titulo == "Titulo"


def test_nome_vazio_nao_explode():
    assert extrair_do_nome("") == ("", "")
    assert extrair_do_nome(".mp3") == ("", "")


def test_extensao_maiuscula_tambem_sai():
    assert extrair_do_nome("Artista - Titulo.MP3") == ("Artista", "Titulo")


def test_ponto_que_nao_e_extensao_de_audio_fica():
    assert limpar_nome("Artista - Titulo.Ao Vivo") == "Artista - Titulo.Ao Vivo"


def test_sublinhado_so_vira_espaco_quando_nao_ha_espaco_nenhum():
    # "Artista_Fulano - Titulo" tem espaço: o "_" é parte do nome, não separador.
    assert extrair_do_nome("Artista_Fulano - Titulo.mp3") == ("Artista_Fulano", "Titulo")


# ------------------------------------------------------------- ffprobe


def ffprobe_falso(
    tags_formato: dict | None = None,
    tags_trilha: dict | None = None,
    **contêiner,
) -> dict:
    """Uma resposta de ffprobe plausível, para testar sem ffmpeg instalado."""
    formato = {"duration": "250.5", "bit_rate": "320000", "size": "10000000"}
    formato.update(contêiner)
    if tags_formato:
        formato["tags"] = tags_formato
    trilha = {"codec_type": "audio", "sample_rate": "44100"}
    if tags_trilha:
        trilha["tags"] = tags_trilha
    return {"format": formato, "streams": [{"codec_type": "video"}, trilha]}


def test_tags_ganham_do_nome_do_arquivo():
    dados = ffprobe_falso(tags_formato={"artist": "Djavan", "title": "Não Vou Ficar"})
    arquivo = montar_arquivo_local(Path("x/99 - nome errado.mp3"), dados)

    assert arquivo.faixa.artista == "Djavan"
    assert arquivo.faixa.titulo == "Não Vou Ficar"
    assert arquivo.origem_do_nome == "tags"


def test_tags_do_flac_em_maiusculas_na_trilha_tambem_valem():
    # FLAC guarda na trilha e usa MAIÚSCULAS — achatar isso é trabalho do módulo.
    dados = ffprobe_falso(tags_trilha={"TITLE": "Kiara", "ARTIST": "Bonobo"})
    arquivo = montar_arquivo_local(Path("x/faixa.flac"), dados)

    assert (arquivo.faixa.artista, arquivo.faixa.titulo) == ("Bonobo", "Kiara")


def test_sem_tags_cai_no_nome_do_arquivo():
    arquivo = montar_arquivo_local(Path("x/Djavan - Se.mp3"), ffprobe_falso())

    assert (arquivo.faixa.artista, arquivo.faixa.titulo) == ("Djavan", "Se")
    assert arquivo.origem_do_nome == "nome do arquivo"


def test_tag_pela_metade_e_marcada_como_mistura():
    # O usuário precisa saber que metade veio de palpite, para poder corrigir antes de buscar.
    dados = ffprobe_falso(tags_formato={"title": "Se"})
    arquivo = montar_arquivo_local(Path("x/Djavan - Outro Nome.mp3"), dados)

    assert arquivo.faixa.titulo == "Se"
    assert arquivo.faixa.artista == "Djavan"
    assert arquivo.origem_do_nome == "tags + nome do arquivo"


def test_le_as_especificacoes_tecnicas():
    arquivo = montar_arquivo_local(Path("x/faixa.mp3"), ffprobe_falso())

    assert arquivo.bitrate_kbps == 320
    assert arquivo.duracao_s == 250.5
    assert arquivo.taxa_amostragem_hz == 44100
    assert arquivo.tamanho_bytes == 10_000_000


def test_profundidade_de_bits_do_flac_vem_de_bits_per_raw_sample():
    dados = ffprobe_falso()
    dados["streams"][1].update({"bits_per_raw_sample": "24", "sample_rate": "96000"})
    arquivo = montar_arquivo_local(Path("x/faixa.flac"), dados)

    assert arquivo.profundidade_bits == 24
    assert arquivo.taxa_amostragem_hz == 96000


def test_bits_per_sample_zero_nao_vira_profundidade():
    # O ffprobe usa 0 para "não se aplica" em formato comprimido.
    dados = ffprobe_falso()
    dados["streams"][1]["bits_per_sample"] = "0"
    assert montar_arquivo_local(Path("x/faixa.mp3"), dados).profundidade_bits is None


def test_valores_ausentes_ou_invalidos_viram_nada():
    dados = {"format": {"duration": "N/A", "bit_rate": ""}, "streams": []}
    arquivo = montar_arquivo_local(Path("x/Artista - Titulo.mp3"), dados)

    assert arquivo.duracao_s is None
    assert arquivo.bitrate_kbps is None
    assert arquivo.faixa.artista == "Artista"


def test_sem_ffprobe_ainda_se_le_o_nome():
    # Sem ffmpeg instalado o app não trava: perde as especificações, mantém os nomes.
    arquivo = montar_arquivo_local(Path("x/Djavan - Se.mp3"), None)

    assert (arquivo.faixa.artista, arquivo.faixa.titulo) == ("Djavan", "Se")
    assert arquivo.bitrate_kbps is None
    assert arquivo.formato == "mp3"


def test_arquivo_do_acervo_nasce_marcado_como_acervo():
    # É o rótulo que identifica o gráfico na comparação lado a lado.
    assert montar_arquivo_local(Path("x/a.mp3"), None).origem == "acervo"


def test_ffprobe_ausente_devolve_nada_em_vez_de_estourar():
    assert ler_ffprobe(Path("x/a.mp3"), executavel="programa_que_nao_existe_xyz") is None


# ----------------------------------------------------------- varredura


def criar(pasta: Path, *nomes: str) -> None:
    for nome in nomes:
        caminho = pasta / nome
        caminho.parent.mkdir(parents=True, exist_ok=True)
        caminho.write_bytes(b"\0" * 16)


def test_varre_so_os_arquivos_de_audio(tmp_path):
    criar(tmp_path, "a.mp3", "b.flac", "capa.jpg", "notas.txt", "lista.m3u")
    achados = [c.name for c in varrer_pasta(tmp_path)]
    assert achados == ["a.mp3", "b.flac"]


def test_varredura_pega_os_formatos_ruins_de_proposito(tmp_path):
    # São exatamente os que mais valem a troca — ignorá-los seria ignorar o alvo
    # desta funcionalidade.
    criar(tmp_path, "velha.wma", "antiga.ogg", "ruim.mp3", "boa.flac")
    assert len(varrer_pasta(tmp_path)) == 4


def test_varredura_entra_nas_subpastas(tmp_path):
    criar(tmp_path, "raiz.mp3", "Album/faixa.flac", "Album/Disco 2/outra.wav")
    assert len(varrer_pasta(tmp_path)) == 3


def test_varredura_pode_ficar_so_na_raiz(tmp_path):
    criar(tmp_path, "raiz.mp3", "Album/faixa.flac")
    achados = varrer_pasta(tmp_path, recursivo=False)
    assert [c.name for c in achados] == ["raiz.mp3"]


def test_varredura_vem_ordenada(tmp_path):
    # A lista aparece na tela; o usuário precisa reencontrar o que viu.
    criar(tmp_path, "zeta.mp3", "alfa.mp3", "Beta.mp3")
    achados = [c.name for c in varrer_pasta(tmp_path)]
    assert achados == sorted(achados, key=str.lower)


def test_extensao_maiuscula_e_reconhecida(tmp_path):
    criar(tmp_path, "FAIXA.FLAC", "outra.Mp3")
    assert len(varrer_pasta(tmp_path)) == 2


def test_pasta_inexistente_devolve_lista_vazia(tmp_path):
    assert varrer_pasta(tmp_path / "nao_existe") == []


def test_pasta_vazia_devolve_lista_vazia(tmp_path):
    assert varrer_pasta(tmp_path) == []


def test_as_extensoes_cobrem_com_e_sem_perda():
    assert {"flac", "wav", "aiff", "mp3", "m4a"} <= EXTENSOES_AUDIO
    assert {"ogg", "wma", "opus"} <= EXTENSOES_AUDIO
