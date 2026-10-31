# 🔧 Instalação — o passo a passo da Fase 0

O que precisa existir na máquina antes do app conseguir baixar música. Serve para esta
máquina e para qualquer outra onde o software for instalado.

Os itens marcados **[VOCÊ]** dependem de senha, login ou escolha sua — ninguém pode fazer
por você.

_Atualizado em: 31/10/2026_

---

## Estado nesta máquina (AlienWareFlows)

| Item | Estado | Onde ficou |
|---|---|---|
| Python 3.12 | ✅ | — |
| PySide6 (a janela) | ✅ 6.12.0 | no `.venv` do projeto |
| **ffmpeg + ffprobe** | ✅ 9.0.2 | `C:\Users\Flores Dev Projects\ffmpeg\bin` (no PATH do usuário) |
| **slskd** | ✅ 0.26.2 | `C:\Users\Flores Dev Projects\slskd` |
| `slskd.yml` gerado | ✅ | `%LOCALAPPDATA%\slskd\slskd.yml` |
| Chave de API ligando app ↔ slskd | ✅ | gerada e gravada nos dois lados |
| Credenciais do Soulseek | ✅ | `joaoflores` — **login confirmado na rede** |
| Pasta compartilhada | ✅ | 39 arquivos sendo compartilhados |
| API do slskd ↔ nosso app | ✅ | `Connected, LoggedIn` em `http://localhost:5030` |
| App no Spotify Dashboard | ⬜ **[VOCÊ]** | item 2 abaixo |
| As três pastas do app | ⬜ **[VOCÊ]** | item 3 abaixo |
| Segunda conta Soulseek | ⬜ **[VOCÊ]** | item 4 — pode esperar |

---

## 1. [VOCÊ] Preencher as credenciais — pelo script, não na mão

> ⚠️ **Preencher vem ANTES de ligar.** O slskd **valida o config e morre** se encontrar os
> marcadores:
> ```
> Invalid configuration:
>   Shares:
>     Share COLOQUE_AQUI_... contains a relative path; only absolute paths are supported.
> ```
> Ele até observa o arquivo e recarrega sozinho depois — mas isso só vale para um processo
> que conseguiu subir.

O arquivo já está gerado em **`C:\Users\<você>\slskd\dados\slskd.yml`** — ao lado do
executável, e **não** no `%LOCALAPPDATA%\slskd` que é o padrão do slskd.

> **Por que fora do padrão:** nesta máquina, o que foi escrito em `%LOCALAPPDATA%\slskd`
> não ficou visível para o terminal do usuário — mesma máquina, mesmo usuário, mesmo
> `LOCALAPPDATA` impresso, e ainda assim a pasta "não existia" para ele, enquanto
> `C:\Users\<você>\slskd\` (criada no mesmo minuto) aparecia normalmente. A causa não foi
> identificada. Guardar a configuração junto do executável põe tudo num lugar que os dois
> lados enxergam, e o slskd suporta isso oficialmente com `--app-dir`.
>
> Ficou um `MARCADOR_DE_DIAGNOSTICO.txt` na pasta antiga, para o caso ser investigado
> depois sem travar o trabalho agora.

Faltam três valores. **Não edite o YAML na mão** — rode:

```
cd "C:\Users\Flores Dev Projects\Documents\Claude_Projects\Soulseek_Auto_Downloader_byFlowers"
.\.venv\Scripts\python.exe configurar_slskd.py
```

Ele pergunta no terminal:

| | O que ele faz de diferente |
|---|---|
| **usuário** do Soulseek | — |
| **senha** do Soulseek | digitada **oculta** (`getpass`): não aparece na tela nem no histórico |
| **pasta compartilhada** | **confere se tem música dentro** antes de aceitar |

Guarda cópia do anterior em `slskd.yml.anterior`. Aceita o caminho com ou sem aspas.

> **Sobre a pasta compartilhada:** não precisa ser o acervo inteiro — precisa **não estar
> vazia**. Enquanto o cliente anunciar *"Nothing Shared"*, outros usuários bloqueiam você
> automaticamente e os downloads param de completar. Não é etiqueta, é requisito de
> funcionamento.

### Ligar o slskd

**No PowerShell** — repare no `&` na frente e no `--app-dir`:

```
& "C:\Users\Flores Dev Projects\slskd\slskd.exe" --app-dir "C:\Users\Flores Dev Projects\slskd\dados"
```

> O `--app-dir` aponta o slskd para a mesma pasta onde a configuração foi gravada. Sem ele,
> o slskd procura no padrão (`%LOCALAPPDATA%\slskd`) e não acha nada. O próprio
> `configurar_slskd.py` imprime este comando pronto no fim.

> ⚠️ Sem o `&`, o PowerShell trata a string entre aspas como **texto** e só ecoa o caminho
> de volta, sem executar nada e sem dar erro. É o engano que mais parece "não aconteceu
> nada". No `cmd` e no Git Bash as aspas sozinhas funcionam.

Deixe essa janela aberta — é o motor rodando. A interface web dele fica em
**http://localhost:5030** (login `slskd` / senha `slskd`, só aceita acesso da própria
máquina).

> ⏳ **A primeira execução demora muito mais que as seguintes.** Ele monta o cache de
> compartilhamento varrendo a pasta inteira antes de abrir a porta — com acervo grande
> isso passa de um minuto, e parece travado. Da segunda vez em diante ele carrega o cache
> do disco e sobe em ~2 segundos. Não mate o processo achando que empacou.

Sinais de que deu certo, no log:

```
[..] Share cache loaded from disk successfully. Sharing N directories and N files
[..] Connected to the Soulseek server
[..] Logged in to the Soulseek server as <seu usuário>
```

Dá para conferir se conectou pela própria interface web, ou pelo botão **Testar conexão**
na aba 🔌 Soulseek das nossas Configurações.

> ⚠️ **Endureça depois:** a senha da interface web do slskd está no padrão (`slskd`/`slskd`).
> Está aceitável agora porque o acesso é restrito a `127.0.0.1`, mas troque antes de expor
> qualquer coisa para fora.

---

## 2. [VOCÊ] Criar o app no Spotify Dashboard

1. Entre em **https://developer.spotify.com/dashboard** com sua conta (a Premium).
2. **Create app**.
3. **App name** e **description**: qualquer coisa (ex.: `Soulseek Auto Downloader`).
4. **Redirect URI** — este tem que ser **exato**:
   ```
   http://127.0.0.1:8888/callback
   ```
   Use `127.0.0.1`, **não** `localhost`. O Spotify exige HTTPS para endereços normais e
   só abre exceção para o endereço de loopback numérico.
5. **Which API/SDKs are you planning to use?** → marque **Web API**.
6. Salve, entre no app criado → **Settings** → copie o **Client ID** e o **Client Secret**.

Me passe o **Client ID**. O **Client Secret** é segredo: cole direto no campo das
Configurações do app quando eu terminar a tela — não precisa passar por aqui.

---

## 3. [VOCÊ] Escolher as três pastas

A estrutura combinada tem **três** raízes, definidas no primeiro acesso:

| Pasta | Para quê |
|---|---|
| **Mãe das playlists** | cada playlist baixada vira uma subpasta aqui dentro |
| **Mãe do acervo** | as pastas que você aponta para buscar versão melhor ficam separadas aqui |
| **Compartilhada (upload)** | a que o Soulseek oferece para a rede (a mesma do item 1) |

Me diga os três caminhos, ou escolha direto na tela quando ela estiver pronta.

> A pasta de upload vai ter **revalidação obrigatória a cada 1 mês de uso** — o app pede
> para você confirmar que ela ainda existe e ainda tem conteúdo. É proteção contra o caso
> silencioso de alguém mover/esvaziar a pasta e só descobrir semanas depois, quando os
> downloads já pararam de completar.

---

## 4. [VOCÊ] Segunda conta Soulseek — pode esperar

Decisão tomada: **duas contas**. Mas ela só é necessária quando o segundo motor (o bot que
automatiza a tela do SoulseekQt) entrar. Enquanto só o slskd estiver em uso, **uma conta
basta**.

Motivo de precisar de duas depois: o servidor do Soulseek **derruba a sessão antiga** quando
a mesma conta entra de novo. Dois clientes ligados com a mesma conta ficam se expulsando em
loop.

---

## Instalar numa máquina nova

O app vai ter **botões de instalar dependências** nas próprias Configurações, para não
precisar repetir isto na mão. Até eles existirem, o caminho é:

1. **`ffmpeg` — pelo winget, que é uma linha** e já resolve o PATH:
   ```
   winget install Gyan.FFmpeg --accept-package-agreements --accept-source-agreements
   ```
   `Gyan.FFmpeg` é **a mesma build** *essentials* que foi instalada à mão nesta máquina
   (9.0.2, de gyan.dev — a que o ffmpeg.org indica para Windows). É o caminho que o botão
   de instalar dependência (C1) vai usar.

   Sem winget: baixar de https://www.gyan.dev/ffmpeg/builds/, extrair em
   `%USERPROFILE%\ffmpeg` e somar `...\ffmpeg\bin` ao PATH do usuário.

   > ⚠️ O `winget search` pode travar por minutos tentando atualizar a origem antes de
   > responder. Com `--accept-source-agreements` e `install` direto ele não faz essa volta.
2. `slskd`: baixar `slskd-<versão>-win-x64.zip` de
   https://github.com/slskd/slskd/releases, extrair em `%USERPROFILE%\slskd`.
   **Não tem pacote winget** — por isso o botão do C1 vai baixar o zip da API de releases
   do GitHub.
3. Repetir os itens 1 a 3 acima.

> **Por que o app procura as dependências no disco, e não só no PATH:** mexer no PATH só
> vale para processos abertos **depois** da mudança. O app que acabou de instalar o ffmpeg
> pelo botão continuaria dizendo "não encontrado" até ser reiniciado. Por isso
> `sistema.encontrar_programa()` procura também em `%USERPROFILE%\ffmpeg\bin` e nos outros
> lugares prováveis — e é lá que o nosso instalador coloca as coisas, sem precisar de
> administrador.

> **Windows: habilite caminho longo antes de instalar o PySide6.** Sem isso o `pip` falha no
> meio e deixa o pacote meio instalado (funciona, mas o `pip list` não o mostra — e aí o
> empacotamento quebra). Uma vez só, em PowerShell **como Administrador**:
> ```
> New-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem" -Name LongPathsEnabled -Value 1 -PropertyType DWORD -Force
> ```
