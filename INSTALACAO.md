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
| Credenciais do Soulseek | ⬜ **[VOCÊ]** | item 1 abaixo |
| Pasta compartilhada | ⬜ **[VOCÊ]** | item 1 abaixo |
| App no Spotify Dashboard | ⬜ **[VOCÊ]** | item 2 abaixo |
| As três pastas do app | ⬜ **[VOCÊ]** | item 3 abaixo |
| Segunda conta Soulseek | ⬜ **[VOCÊ]** | item 4 — pode esperar |

---

## 1. [VOCÊ] Preencher o `slskd.yml` — três campos

O arquivo já está gerado com tudo pronto. Faltam **três** valores, cada um marcado com
`COLOQUE_AQUI`. Abra:

```
notepad "C:\Users\Flores Dev Projects\AppData\Local\slskd\slskd.yml"
```

Troque:

| Marcador | Pelo quê |
|---|---|
| `COLOQUE_AQUI_SEU_USUARIO_SOULSEEK` | seu usuário do Soulseek |
| `COLOQUE_AQUI_SUA_SENHA_SOULSEEK` | sua senha do Soulseek |
| `COLOQUE_AQUI_A_PASTA_QUE_VOCE_VAI_COMPARTILHAR` | o caminho da pasta que você vai compartilhar |

> **Sobre a pasta compartilhada:** não precisa ser o acervo inteiro — precisa **não estar
> vazia**. Enquanto o cliente anunciar *"Nothing Shared"*, outros usuários bloqueiam você
> automaticamente e os downloads param de completar. Não é etiqueta, é requisito de
> funcionamento. Caminho do Windows com barra invertida funciona normalmente aqui.

Salve e feche. O slskd **observa o arquivo** e recarrega sozinho.

### Ligar o slskd

```
"C:\Users\Flores Dev Projects\slskd\slskd.exe"
```

Deixe essa janela aberta — é o motor rodando. A interface web dele fica em
**http://localhost:5030** (login `slskd` / senha `slskd`, só aceita acesso da própria
máquina).

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
