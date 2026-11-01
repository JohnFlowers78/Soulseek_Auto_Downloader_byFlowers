"""Lê e escreve o `slskd.yml` — usuário, senha e pasta compartilhada.

Existe para que isso possa ser feito **pela janela**, e não só pelo terminal. O
`configurar_slskd.py` continua valendo para quem preferir a linha de comando; os dois
usam este módulo, então não há duas verdades.

Edição por linha em vez de um analisador de YAML de verdade: são três campos, o
arquivo é o que o nosso próprio gerador escreve, e somar uma dependência (e mais um
item a empacotar) para mexer em três linhas não paga.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

import sistema

MARCADORES = {
    "usuario": "COLOQUE_AQUI_SEU_USUARIO_SOULSEEK",
    "senha": "COLOQUE_AQUI_SUA_SENHA_SOULSEEK",
    "pasta": "COLOQUE_AQUI_A_PASTA_QUE_VOCE_VAI_COMPARTILHAR",
}


def achar_yml() -> Path | None:
    """Acha o `slskd.yml`, procurando primeiro ao lado do executável.

    A pasta `dados/` junto do programa vem antes do padrão `%LOCALAPPDATA%\\slskd`
    porque nesta máquina o que foi escrito no AppData não ficou visível para o
    terminal do usuário — mesma máquina, mesmo usuário, e a pasta "não existia" para
    ele. Guardar junto do executável põe tudo onde os dois lados enxergam.
    """
    candidatos = []
    executavel = sistema.encontrar_slskd()
    if executavel:
        candidatos.append(executavel.parent / "dados" / "slskd.yml")
    candidatos.append(sistema.pasta_de_dados_do_slskd() / "slskd.yml")
    return next((c for c in candidatos if c.is_file()), None)


def _linhas(caminho: Path) -> list[str]:
    try:
        return caminho.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []


def ler_valor(chave: str, caminho: Path | None = None) -> str:
    """Devolve o valor de uma chave simples (`username`, `password`), ou `""`.

    Senha também sai daqui — quem chama decide se mostra. Aqui o trabalho é ler.
    """
    caminho = caminho or achar_yml()
    if caminho is None:
        return ""
    for linha in _linhas(caminho):
        limpa = linha.split("#", 1)[0].strip()
        if limpa.startswith(f"{chave}:"):
            valor = limpa.split(":", 1)[1].strip().strip("'\"")
            return "" if valor in MARCADORES.values() else valor
    return ""


def ler_compartilhada(caminho: Path | None = None) -> str:
    """O primeiro caminho listado em `shares.directories`."""
    caminho = caminho or achar_yml()
    if caminho is None:
        return ""
    dentro = False
    for linha in _linhas(caminho):
        sem_comentario = linha.split("#", 1)[0]
        limpa = sem_comentario.strip()
        if limpa.startswith("directories:"):
            dentro = True
            continue
        if dentro and limpa.startswith("- "):
            valor = limpa[2:].strip().strip("'\"")
            return "" if valor in MARCADORES.values() else valor
        if dentro and sem_comentario and not sem_comentario[0].isspace():
            break
    return ""


def pendencias(caminho: Path | None = None) -> list[str]:
    """Quais dos três campos ainda estão com marcador. Lista vazia = tudo preenchido."""
    caminho = caminho or achar_yml()
    # Arquivo ausente conta como TUDO pendente. Devolver lista vazia ali diria "está
    # tudo configurado" sobre um arquivo que não existe — a mentira mais perigosa que
    # esta função poderia contar.
    if caminho is None or not Path(caminho).is_file():
        return list(MARCADORES)
    texto = "\n".join(_linhas(caminho))
    return [nome for nome, marca in MARCADORES.items() if marca in texto]


def gravar(
    usuario: str = "",
    senha: str = "",
    pasta: str = "",
    caminho: Path | None = None,
) -> Path:
    """Grava os campos informados. Campo vazio **não** apaga o que já estava lá.

    Essa regra não é detalhe: a janela mostra a senha mascarada e em branco, e sem ela
    uma gravação de rotina apagaria a senha do arquivo — exatamente o acidente que já
    custou o token do Spotify neste projeto.

    Guarda uma cópia do arquivo anterior antes de escrever.
    """
    caminho = caminho or achar_yml()
    # Vale tanto para "não achei em lugar nenhum" quanto para "me deram um caminho que
    # não existe": nos dois casos o recado tem que ensinar a sair, não vazar o erro cru
    # do sistema de arquivos.
    if caminho is None or not Path(caminho).is_file():
        raise FileNotFoundError(
            "Não achei o slskd.yml. O slskd foi instalado? Veja o INSTALACAO.md."
        )

    linhas = _linhas(caminho)
    if usuario.strip():
        linhas = _trocar_chave(linhas, "username", usuario.strip())
    if senha.strip():
        linhas = _trocar_chave(linhas, "password", senha.strip())
    if pasta.strip():
        linhas = _trocar_compartilhada(linhas, pasta.strip())

    shutil.copy2(caminho, caminho.with_suffix(".yml.anterior"))
    caminho.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    return caminho


def _trocar_chave(linhas: list[str], chave: str, valor: str) -> list[str]:
    padrao = re.compile(rf"^(\s*){chave}:\s*.*$")
    saida, trocou = [], False
    for linha in linhas:
        achado = padrao.match(linha.split("#", 1)[0])
        if achado and not trocou:
            saida.append(f"{achado.group(1)}{chave}: {valor}")
            trocou = True
        else:
            saida.append(linha)
    return saida


def _trocar_compartilhada(linhas: list[str], pasta: str) -> list[str]:
    """Troca o primeiro item de `shares.directories`, preservando o recuo."""
    saida, dentro, trocou = [], False, False
    for linha in linhas:
        sem_comentario = linha.split("#", 1)[0]
        limpa = sem_comentario.strip()

        if limpa.startswith("directories:"):
            dentro = True
            saida.append(linha)
            continue
        if dentro and not trocou and limpa.startswith("- "):
            recuo = sem_comentario[: len(sem_comentario) - len(sem_comentario.lstrip())]
            saida.append(f"{recuo}- {pasta}")
            trocou = True
            continue
        if dentro and sem_comentario and not sem_comentario[0].isspace():
            dentro = False
        saida.append(linha)
    return saida
