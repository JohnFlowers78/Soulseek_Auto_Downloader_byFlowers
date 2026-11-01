"""Testes do baixador.

Tudo que mexe em disco usa `tmp_path`: nenhum teste encosta na área de passagem real do
slskd nem na pasta de música do usuário.
"""

import pytest

from baixador import Baixador, Lote, _destino_livre
from modelos import Candidato, EstadoTransferencia, Transferencia
from qualidade import avaliar


def candidato(nome="musica.flac", usuario="joao") -> Candidato:
    return Candidato(
        usuario=usuario,
        caminho=rf"@@abc\Music\Artista\{nome}",
        tamanho_bytes=30_000_000,
        duracao_s=250.0,
    )


def transferencia(estado, nome="musica.flac", usuario="joao") -> Transferencia:
    return Transferencia(candidato=candidato(nome, usuario), estado=estado)


class ClienteFalso:
    def __init__(self, downloads=None, recusar: set[str] | None = None):
        self._downloads = downloads or []
        self.recusar = recusar or set()
        self.enfileirados: list[Candidato] = []

    def enfileirar(self, candidato: Candidato) -> bool:
        if candidato.usuario in self.recusar:
            raise RuntimeError("usuário sumiu")
        self.enfileirados.append(candidato)
        return True

    def downloads(self):
        return self._downloads() if callable(self._downloads) else self._downloads


def baixador(cliente, pasta) -> Baixador:
    return Baixador(cliente, pasta, dormir=lambda _: None, relogio=_relogio_falso())


def _relogio_falso():
    momento = {"t": 0.0}

    def agora():
        momento["t"] += 1.0
        return momento["t"]

    return agora


# ------------------------------------------------------------- enfileirar


def test_enfileira_os_escolhidos(tmp_path):
    cliente = ClienteFalso()
    escolhidos = [avaliar(candidato("a.flac", "joao")), avaliar(candidato("b.flac", "maria"))]

    fila = baixador(cliente, tmp_path).enfileirar(escolhidos)

    assert len(fila.aceitos) == 2
    assert fila.recusados == []
    assert len(cliente.enfileirados) == 2


def test_um_usuario_que_sumiu_nao_derruba_os_outros(tmp_path):
    # É exatamente para isto que escolhemos de usuários diferentes.
    cliente = ClienteFalso(recusar={"joao"})
    escolhidos = [avaliar(candidato("a.flac", "joao")), avaliar(candidato("b.flac", "maria"))]

    fila = baixador(cliente, tmp_path).enfileirar(escolhidos)

    assert [c.usuario for c in fila.aceitos] == ["maria"]
    # O motivo tem que vir junto: a versao anterior engolia a excecao e o app imprimia
    # um palpite inventado ("os usuarios podem ter saido do ar").
    assert len(fila.recusados) == 1
    recusado, motivo = fila.recusados[0]
    assert recusado.usuario == "joao"
    assert "usuário sumiu" in motivo


def test_enfileirar_lista_vazia(tmp_path):
    fila = baixador(ClienteFalso(), tmp_path).enfileirar([])
    assert fila.aceitos == []
    assert not fila


# --------------------------------------------------------------- lote


def test_o_lote_separa_as_tres_listas():
    lote = Lote(
        transferencias=[
            transferencia(EstadoTransferencia.CONCLUIDA, "a.flac"),
            transferencia(EstadoTransferencia.NA_FILA, "b.flac"),
            transferencia(EstadoTransferencia.BAIXANDO, "c.flac"),
            transferencia(EstadoTransferencia.FALHOU, "d.flac"),
        ]
    )
    assert len(lote.concluidas) == 1
    assert len(lote.presas) == 2  # na fila e baixando ainda podem terminar
    assert len(lote.falhadas) == 1
    assert not lote.tudo_terminou


def test_lote_todo_terminado():
    lote = Lote(
        transferencias=[
            transferencia(EstadoTransferencia.CONCLUIDA),
            transferencia(EstadoTransferencia.FALHOU, "b.flac"),
        ]
    )
    assert lote.tudo_terminou


# ---------------------------------------------------------- acompanhar


def test_acompanhar_para_quando_tudo_termina(tmp_path):
    voltas = {"n": 0}

    def downloads():
        voltas["n"] += 1
        estado = (
            EstadoTransferencia.CONCLUIDA if voltas["n"] >= 3 else EstadoTransferencia.BAIXANDO
        )
        return [transferencia(estado)]

    lote = baixador(ClienteFalso(downloads), tmp_path).acompanhar([candidato()])

    assert lote.tudo_terminou
    assert voltas["n"] == 3


def test_acompanhar_desiste_no_tempo_limite(tmp_path):
    cliente = ClienteFalso([transferencia(EstadoTransferencia.NA_FILA)])
    lote = baixador(cliente, tmp_path).acompanhar([candidato()], espera_max_s=5)

    # O que sobra preso NÃO é erro: é a terceira lista da tela.
    assert len(lote.presas) == 1
    assert not lote.tudo_terminou


def test_acompanhar_ignora_downloads_de_outras_faixas(tmp_path):
    cliente = ClienteFalso(
        [
            transferencia(EstadoTransferencia.CONCLUIDA, "minha.flac", "joao"),
            transferencia(EstadoTransferencia.BAIXANDO, "de_outro_lote.flac", "pedro"),
        ]
    )
    lote = baixador(cliente, tmp_path).acompanhar([candidato("minha.flac", "joao")])

    assert len(lote.transferencias) == 1
    assert lote.transferencias[0].candidato.nome_arquivo == "minha.flac"


def test_nao_termina_cedo_quando_o_slskd_omite_uma_transferencia(tmp_path):
    """O bug que fazia perder download: o lote era trocado pelo que a consulta trouxe.

    O slskd nem sempre devolve todas as transferências em toda consulta. Se a lista for
    substituída em bloco, o lote encolhe, `tudo_terminou` vira verdadeiro com o que
    sumiu ainda baixando, e o acompanhamento acaba cedo.
    """
    voltas = {"n": 0}

    def downloads():
        voltas["n"] += 1
        if voltas["n"] == 1:
            # só a primeira aparece, e já concluída
            return [transferencia(EstadoTransferencia.CONCLUIDA, "a.flac", "joao")]
        if voltas["n"] == 2:
            # a segunda aparece agora, ainda baixando
            return [transferencia(EstadoTransferencia.BAIXANDO, "b.flac", "maria")]
        return [
            transferencia(EstadoTransferencia.CONCLUIDA, "a.flac", "joao"),
            transferencia(EstadoTransferencia.CONCLUIDA, "b.flac", "maria"),
        ]

    lote = baixador(ClienteFalso(downloads), tmp_path).acompanhar(
        [candidato("a.flac", "joao"), candidato("b.flac", "maria")]
    )

    assert len(lote.transferencias) == 2
    assert len(lote.concluidas) == 2
    assert voltas["n"] >= 3, "terminou antes de a segunda completar"


def test_o_lote_sempre_tem_todos_os_candidatos_pedidos(tmp_path):
    # Mesmo que o slskd não devolva nada, as duas têm que aparecer no relatório —
    # senão a faixa some das três listas da tela.
    cliente = ClienteFalso([])
    lote = baixador(cliente, tmp_path).acompanhar(
        [candidato("a.flac", "joao"), candidato("b.flac", "maria")], espera_max_s=3
    )
    assert len(lote.transferencias) == 2
    assert len(lote.presas) == 2


def test_conferir_varios_faz_UMA_consulta_para_todos(tmp_path):
    """O bug que derrubou uma playlist de 425 faixas.

    Conferir cada pendente separadamente fazia N chamadas para buscar o mesmo dado.
    Com 50 pendentes, 50 conexões por faixa processada — e o Windows ficou sem portas
    efêmeras, devolvendo `WinError 10055 — sem espaço de buffer`.
    """
    chamadas = {"n": 0}

    def downloads():
        chamadas["n"] += 1
        return [transferencia(EstadoTransferencia.CONCLUIDA, f"m{i}.flac") for i in range(50)]

    grupos = {i: [candidato(f"m{i}.flac")] for i in range(50)}
    lotes = baixador(ClienteFalso(downloads), tmp_path).conferir_varios(grupos)

    assert chamadas["n"] == 1, "uma consulta serve todos os grupos"
    assert len(lotes) == 50


def test_conferir_varios_devolve_um_lote_por_grupo(tmp_path):
    cliente = ClienteFalso([transferencia(EstadoTransferencia.CONCLUIDA, "a.flac")])
    grupos = {"x": [candidato("a.flac")], "y": [candidato("b.flac")]}

    lotes = baixador(cliente, tmp_path).conferir_varios(grupos)

    assert lotes["x"].concluidas
    # O que o slskd não conhece ainda conta como pendente, não some do relatório.
    assert lotes["y"].presas


def test_conferir_varios_sem_grupos(tmp_path):
    assert baixador(ClienteFalso([]), tmp_path).conferir_varios({}) == {}


def test_acompanhar_avisa_o_progresso(tmp_path):
    avisos = []
    cliente = ClienteFalso([transferencia(EstadoTransferencia.CONCLUIDA)])
    baixador(cliente, tmp_path).acompanhar([candidato()], ao_progredir=avisos.append)

    assert avisos


# ------------------------------------------------------- achar no disco


def test_acha_o_arquivo_em_subpasta(tmp_path):
    # O slskd cria subpastas conforme a origem; procurar pelo nome evita depender disso.
    fundo = tmp_path / "joao" / "Album"
    fundo.mkdir(parents=True)
    (fundo / "musica.flac").write_bytes(b"\0" * 10)

    achado = baixador(ClienteFalso(), tmp_path).achar_no_disco("musica.flac")
    assert achado == fundo / "musica.flac"


def test_acha_sem_ligar_para_maiusculas(tmp_path):
    (tmp_path / "MUSICA.FLAC").write_bytes(b"\0")
    assert baixador(ClienteFalso(), tmp_path).achar_no_disco("musica.flac") is not None


def test_nao_acha_o_que_nao_existe(tmp_path):
    assert baixador(ClienteFalso(), tmp_path).achar_no_disco("sumiu.flac") is None


def test_pasta_de_passagem_inexistente_nao_explode(tmp_path):
    b = baixador(ClienteFalso(), tmp_path / "nao_existe")
    assert b.achar_no_disco("x.flac") is None


# ---------------------------------------------------------- organizar


def test_move_o_que_terminou_para_o_destino(tmp_path):
    passagem = tmp_path / "passagem"
    destino = tmp_path / "destino"
    (passagem / "joao").mkdir(parents=True)
    (passagem / "joao" / "musica.flac").write_bytes(b"audio")

    lote = Lote(transferencias=[transferencia(EstadoTransferencia.CONCLUIDA)])
    movidos = baixador(ClienteFalso(), passagem).organizar(lote, destino)

    assert movidos == [destino / "musica.flac"]
    assert (destino / "musica.flac").read_bytes() == b"audio"
    assert not (passagem / "joao" / "musica.flac").exists()


def test_o_caminho_final_fica_registrado_na_transferencia(tmp_path):
    passagem = tmp_path / "passagem"
    passagem.mkdir()
    (passagem / "musica.flac").write_bytes(b"audio")

    t = transferencia(EstadoTransferencia.CONCLUIDA)
    baixador(ClienteFalso(), passagem).organizar(Lote([t]), tmp_path / "destino")

    assert t.caminho_local.endswith("musica.flac")


def test_nao_move_o_que_nao_terminou(tmp_path):
    passagem = tmp_path / "passagem"
    passagem.mkdir()
    (passagem / "musica.flac").write_bytes(b"audio")

    lote = Lote(transferencias=[transferencia(EstadoTransferencia.NA_FILA)])
    assert baixador(ClienteFalso(), passagem).organizar(lote, tmp_path / "destino") == []


def test_cria_a_pasta_de_destino_se_preciso(tmp_path):
    passagem = tmp_path / "passagem"
    passagem.mkdir()
    destino = tmp_path / "fundo" / "mais_fundo"

    baixador(ClienteFalso(), passagem).organizar(Lote(), destino)
    assert destino.is_dir()


# ------------------------------------------------- não sobrescrever


def test_nunca_sobrescreve_arquivo_existente(tmp_path):
    # Baixar duas versões para comparar é o fluxo do app; uma apagando a outra
    # acabaria com a comparação antes dela acontecer.
    passagem = tmp_path / "passagem"
    destino = tmp_path / "destino"
    passagem.mkdir()
    destino.mkdir()
    (passagem / "musica.flac").write_bytes(b"nova")
    (destino / "musica.flac").write_bytes(b"antiga")

    lote = Lote(transferencias=[transferencia(EstadoTransferencia.CONCLUIDA)])
    (movido,) = baixador(ClienteFalso(), passagem).organizar(lote, destino)

    assert movido.name == "musica (2).flac"
    assert (destino / "musica.flac").read_bytes() == b"antiga"
    assert movido.read_bytes() == b"nova"


def test_o_contador_sobe_enquanto_houver_conflito(tmp_path):
    (tmp_path / "a.flac").write_bytes(b"1")
    (tmp_path / "a (2).flac").write_bytes(b"2")
    assert _destino_livre(tmp_path / "a.flac").name == "a (3).flac"


def test_sem_conflito_o_nome_fica_igual(tmp_path):
    assert _destino_livre(tmp_path / "livre.flac").name == "livre.flac"
