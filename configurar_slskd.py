"""Preenche o `slskd.yml` perguntando no terminal — sem abrir editor nenhum.

Existe porque editar YAML na mão é atrito desnecessário e dá errado de formas chatas:
caminho do Windows com espaço no nome do usuário se perde dependendo do terminal, e um
recuo trocado no arquivo derruba o slskd sem explicar por quê.

A senha é digitada **oculta** e nunca aparece na tela nem em log.

    python configurar_slskd.py

Mais tarde isto vira campo na tela de Configurações — este script é a ponte até lá, e
continua útil para instalar numa máquina nova pelo terminal.
"""

from __future__ import annotations

import getpass
import os
import platform
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

import sistema  # noqa: E402

MARCADORES = {
    "usuario": "COLOQUE_AQUI_SEU_USUARIO_SOULSEEK",
    "senha": "COLOQUE_AQUI_SUA_SENHA_SOULSEEK",
    "pasta": "COLOQUE_AQUI_A_PASTA_QUE_VOCE_VAI_COMPARTILHAR",
}

EXTENSOES_MUSICA = {".mp3", ".flac", ".wav", ".aiff", ".aif", ".m4a", ".aac", ".ogg", ".wma"}


def locais_possiveis() -> list[Path]:
    """Onde o `slskd.yml` pode estar, do mais provável para o menos.

    A pasta ``dados/`` ao lado do executável vem **primeiro** de propósito. O padrão do
    slskd é ``%LOCALAPPDATA%\\slskd``, mas nesta máquina o que foi escrito ali não ficou
    visível para o terminal do usuário — mesma máquina, mesmo usuário, mesmo
    ``LOCALAPPDATA``, e ainda assim a pasta "não existia" para ele. Guardar junto do
    executável põe a configuração num lugar que os dois lados enxergam, e o slskd suporta
    isso oficialmente via ``--app-dir``.
    """
    locais = []
    executavel = sistema.encontrar_slskd()
    if executavel:
        locais.append(executavel.parent / "dados" / "slskd.yml")
    locais.append(sistema.pasta_de_dados_do_slskd() / "slskd.yml")
    return locais


def achar_config() -> Path | None:
    """Acha o `slskd.yml`. Aceita `--config <caminho>` para apontar um lugar diferente."""
    if "--config" in sys.argv:
        indicado = Path(sys.argv[sys.argv.index("--config") + 1])
        return indicado if indicado.is_file() else None

    for caminho in locais_possiveis():
        if caminho.is_file():
            return caminho
    return None


def explicar_por_que_nao_achou() -> None:
    """Mostra o que o Python está realmente vendo no disco.

    Existe porque "não achei o arquivo" é um beco sem saída quando o arquivo está lá:
    `Path.is_file()` devolve False tanto para "não existe" quanto para "existe mas não
    consigo ler" — ele engole o erro de permissão. Sem estes números, a conversa vira
    adivinhação.
    """
    print("Não achei o slskd.yml.\n")
    print("Procurei em:")
    for caminho in locais_possiveis():
        print(f"  {'✓' if caminho.is_file() else '✗'} {caminho}")
    print()

    pasta = sistema.pasta_de_dados_do_slskd()
    alvo = pasta / "slskd.yml"

    print("O que o Python está vendo daqui:")
    # O nome da máquina é o primeiro dado a conferir quando "o arquivo está lá mas o
    # programa não acha": duas máquinas com o mesmo nome de usuário produzem caminhos
    # idênticos em telas diferentes, e aí a conversa inteira fica sem chão.
    print(f"  máquina .........: {platform.node()}")
    print(f"  usuário .........: {os.environ.get('USERNAME', '?')}")
    print(f"  LOCALAPPDATA ....: {os.environ.get('LOCALAPPDATA', '(não definido)')}")
    slskd_exe = sistema.encontrar_slskd()
    print(f"  slskd.exe .......: {slskd_exe or 'NÃO ENCONTRADO'}")
    print(f"  pasta procurada .: {pasta}")
    print(f"    existe? ........ {pasta.exists()}")
    print(f"  arquivo procurado: {alvo}")
    print(f"    existe? ........ {alvo.exists()}")
    print(f"    é arquivo? ..... {alvo.is_file()}")

    if pasta.is_dir():
        try:
            dentro = sorted(p.name for p in pasta.iterdir())
            print(f"  o que há na pasta: {dentro or '(vazia)'}")
        except OSError as erro:
            print(f"  não consegui listar a pasta: {erro}")

    print()
    if alvo.exists() and not alvo.is_file():
        print("O caminho existe mas não é um arquivo comum — confira se não virou pasta.")
    elif not pasta.exists():
        print("A pasta nem existe. O slskd foi instalado? Veja o INSTALACAO.md.")
    else:
        print("Se o arquivo aparece no Explorer mas não aqui, pode ser permissão.")
        print("Aponte o caminho na mão:")
        print("  python configurar_slskd.py --config <caminho do slskd.yml>")


def contar_musicas(pasta: Path, teto: int = 50) -> int:
    """Conta até `teto` músicas. Para cedo: só interessa saber se há conteúdo."""
    total = 0
    try:
        for caminho in pasta.rglob("*"):
            if caminho.is_file() and caminho.suffix.lower() in EXTENSOES_MUSICA:
                total += 1
                if total >= teto:
                    break
    except OSError:
        return total
    return total


def perguntar_pasta() -> str:
    """Pede a pasta compartilhada e confere que ela serve de verdade."""
    while True:
        bruto = input("Pasta que você vai COMPARTILHAR na rede: ").strip().strip('"').strip("'")
        if not bruto:
            print("  → precisa de um caminho.\n")
            continue

        pasta = Path(bruto)
        if not pasta.is_dir():
            print(f"  → essa pasta não existe: {pasta}\n")
            continue

        quantas = contar_musicas(pasta)
        if quantas == 0:
            print(
                "  ⚠ Não achei nenhuma música aí dentro. Compartilhar pasta vazia é o mesmo\n"
                '    que não compartilhar: o Soulseek anuncia "Nothing Shared" e os outros\n'
                "    usuários bloqueiam você automaticamente — os downloads param de completar."
            )
            if input("    Usar essa pasta assim mesmo? (s/N) ").strip().lower() != "s":
                print()
                continue
        else:
            quantas_txt = f"{quantas}+" if quantas >= 50 else str(quantas)
            print(f"  ✓ {quantas_txt} música(s) encontrada(s) — serve.")

        return str(pasta)


def main() -> int:
    config = achar_config()
    if config is None:
        explicar_por_que_nao_achou()
        return 1

    texto = config.read_text(encoding="utf-8")
    pendentes = [nome for nome, marca in MARCADORES.items() if marca in texto]

    if not pendentes:
        print("O slskd.yml já está preenchido — usuário, senha e pasta compartilhada.")
        print(f"Arquivo: {config}")
        if input("Quer preencher de novo? (s/N) ").strip().lower() != "s":
            return 0
        print("\nPara trocar valores já gravados, apague o slskd.yml e rode:")
        print("  python configurar_slskd.py")
        print("(ou edite o arquivo direto, se preferir)")
        return 0

    print(f"Preenchendo: {config}\n")

    if "usuario" in pendentes:
        usuario = ""
        while not usuario:
            usuario = input("Seu usuário do Soulseek: ").strip()
        texto = texto.replace(MARCADORES["usuario"], usuario)

    if "senha" in pendentes:
        senha = ""
        while not senha:
            # getpass não ecoa a senha — nem na tela, nem no histórico do terminal.
            senha = getpass.getpass("Sua senha do Soulseek (não aparece): ").strip()
        texto = texto.replace(MARCADORES["senha"], senha)

    if "pasta" in pendentes:
        texto = texto.replace(MARCADORES["pasta"], perguntar_pasta())

    reserva = config.with_suffix(".yml.anterior")
    shutil.copy2(config, reserva)
    config.write_text(texto, encoding="utf-8")

    print()
    print("✓ Gravado.")
    print(f"  arquivo .......: {config}")
    print(f"  cópia anterior : {reserva}")
    print()
    print("Agora ligue o motor e deixe a janela aberta.")
    print()
    # O "&" não é enfeite: no PowerShell uma string entre aspas sozinha é só um texto,
    # que ele ecoa de volta sem executar nada. É o erro que mais parece "não aconteceu
    # nada" sem dar mensagem alguma.
    executavel = sistema.encontrar_slskd() or Path("slskd.exe")
    # --app-dir aponta o slskd para a MESMA pasta onde este script gravou o config.
    # Sem ele, o slskd usaria o padrão (%LOCALAPPDATA%\slskd) e não acharia nada.
    app_dir = config.parent
    print("  No PowerShell (repare no & na frente — sem ele o PowerShell só imprime o texto):")
    print(f'    & "{executavel}" --app-dir "{app_dir}"')
    print()
    print("  No cmd ou no Git Bash:")
    print(f'    "{executavel}" --app-dir "{app_dir}"')
    print()
    print("A interface web dele fica em http://localhost:5030 (login slskd / senha slskd).")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nCancelado — nada foi gravado.")
        raise SystemExit(130)
