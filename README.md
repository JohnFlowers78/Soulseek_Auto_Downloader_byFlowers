# 🎵 Soulseek Auto Downloader — by Flowers

Pega uma **playlist do Spotify**, busca cada faixa no **Soulseek**, baixa nas qualidades que
prestam (AIFF / WAV / FLAC / MP3 320 / M4A-AAC), organiza numa pasta com o nome da playlist
e ainda gera o **espectrograma** de cada arquivo para você conferir se a qualidade é real ou
maquiada.

O que sobrar — o que não foi achado ou não terminou de baixar — vira uma lista de caça:
o app procura essas faixas de **graça** (SoundCloud / Hypeddit) e, em último caso, monta uma
**cotação de compra** com os preços de cada loja.

_Atualizado em: 05/09/2026_

---

## 📚 Documentos deste projeto

| Arquivo | O que tem dentro |
|---|---|
| **[FUNCIONALIDADES.md](FUNCIONALIDADES.md)** | Tudo que o app deve fazer — o escopo combinado, por módulo |
| **[TODO.md](TODO.md)** | O que falta construir, em fases, com caixinhas para riscar |
| **[ARQUITETURA.md](ARQUITETURA.md)** | As decisões estruturais e o custo de cada uma |
| **[INSTALACAO.md](INSTALACAO.md)** | O passo a passo para deixar a máquina pronta |
| **[IDEIAS.md](IDEIAS.md)** | Documento vivo: descobertas de operação e ideias futuras |
| **[GUIA_SOULSEEK.md](GUIA_SOULSEEK.md)** | A parte dura: sintaxe de busca, limite de buscas, API do slskd |

---

## 🔑 As três descobertas que definiram a arquitetura

Antes de escrever uma linha, três perguntas foram respondidas na fonte. As respostas
economizaram o projeto inteiro de automação de tela.

### 1. Não precisa inspecionar elemento no Spotify — mas tem um porém novo

Existe a **Spotify Web API**, e ela devolve faixa, artista, álbum, duração e ISRC em JSON.
Só que a **mudança de fevereiro/2026** apertou: a API agora entrega o **conteúdo** apenas das
playlists **do próprio usuário logado**. Playlist de terceiros devolve só metadados (nome,
capa, quantidade), **não a lista de faixas**.

Então o app tem **dois leitores**:

- **Playlist sua** → API oficial com login OAuth. Limpo, completo, instantâneo, e traz o
  **ISRC** — o código único da gravação, que é ouro para conferir se o arquivo baixado é
  mesmo aquela faixa.
- **Playlist de outra pessoa** → aí sim o plano B que você imaginou: abrir no navegador e ler
  a página. E você estava certo sobre o Spotify travar a seleção de texto — mas ler o **DOM**
  não depende de selecionar nada. O texto está lá, só não dá para arrastar o mouse por cima.

### 2. O Soulseek TEM API — e isso mata a automação de telas

Você duvidou, e era uma boa dúvida: o SoulseekQt original, aquele de 2008, realmente não tem
API nenhuma. **Mas existe o [slskd](https://github.com/slskd/slskd)** — um cliente moderno da
mesma rede Soulseek, sem interface obrigatória, que roda como serviço e expõe **API REST
completa**: buscar, ler resultados, enfileirar download, acompanhar transferência, cancelar.

Roda em Windows nativo (não precisa Docker) e tem wrapper Python pronto (`slskd-api`).

**Consequência prática:** nada de te fazer explicar tela por tela do Soulseek antigo, nada de
clicar em pixel, nada de OCR para ler a lista de downloads. O bot conversa por HTTP. É outra
categoria de confiabilidade — e continua sendo a **mesma rede**, os mesmos usuários, os
mesmos arquivos.

### 3. O Spek não tem API — e não precisa ter

O Spek é uma interface gráfica em wxWidgets, sem linha de comando no build oficial. Só que
por baixo **o Spek é o `ffmpeg`**: ele usa as bibliotecas do ffmpeg para decodificar e
desenhar. E o ffmpeg tem o filtro `showspectrumpic`, que gera **o mesmo espectrograma**
direto por linha de comando.

Ou seja: nada de abrir o Spek, dar print da tela e recortar. Geramos o PNG direto do ffmpeg,
já no tamanho certo, já com o nome do arquivo, já na pasta.

E vai além do desenho: dá para medir a **frequência de corte em número** — analisando o áudio
em vez da imagem. Um MP3 320 real vai até ~20 kHz; um 128 kbps renomeado para "320" corta
seco em 16 kHz. O app compara **o que o arquivo diz ser** com **o que ele é de verdade**, e
marca os mentirosos.

> Isso também resolve o custo: **sem Tesseract e sem API de IA** para ler gráfico. A conta
> sai do próprio áudio, de graça, offline. A IA fica só para a descrição em texto, se um dia
> você quiser.

---

## 🧱 Como as peças se encaixam

```
Link da playlist
      │
      ├── leitor_spotify.py ──── API OAuth (playlist sua)
      │                     └─── navegador/DOM (playlist de terceiro)
      ▼
 Lista de faixas (artista, título, álbum, duração, ISRC)
      │
      ▼
 normalizador.py ─── gera N formas de escrever a mesma busca
      │              (com acento, sem acento, sem "feat.", sem parênteses, só título…)
      ▼
 buscador.py ─── slskd (API REST) ─── rede Soulseek
      │           ⚠ no máximo 34 buscas / 220 s, senão banimento de 30 min
      ▼
 seletor.py ─── filtra por formato e bitrate, ranqueia, escolhe os melhores
      │
      ▼
 baixador.py ─── enfileira, acompanha, separa: ✅ baixou / ⏳ na fila / ❌ não achou
      │
      ├──► pasta destino / <Nome da Playlist> /
      │
      ▼
 espectro.py ─── ffmpeg showspectrumpic ─── PNG lado a lado + corte em kHz
      │
      ▼
 cacador.py ─── o que faltou: SoundCloud / Hypeddit (grátis) → cotação de compra
```

---

## ⚙️ Requisitos

| Programa | Para quê | Situação nesta máquina |
|---|---|---|
| Python 3.12 | o app inteiro | ✅ instalado (3.12.10) |
| Git | versionamento | ✅ instalado (2.54.0) |
| **slskd** | o motor de busca/download do Soulseek | ⬜ falta instalar |
| **ffmpeg** | espectrograma e análise de qualidade | ⬜ falta instalar |
| Conta Soulseek | login na rede | ⬜ a confirmar |
| App no Spotify Dashboard | ler suas playlists | ⬜ a criar |

> O **Spek** continua útil para você olhar na mão quando quiser, mas o app **não depende**
> dele. Nada de automatizar a janela dele.

---

## 🚦 Estado atual

O núcleo que não depende de nada instalado já está de pé — **229 testes passando**:

- **`src/normalizador.py`** — o gerador de variantes de busca, que resolve exatamente a dor
  dos caracteres especiais.
- **`src/modelos.py`** — o vocabulário comum aos dois motores (`Faixa`, `Candidato`,
  `Transferencia`, `ArquivoLocal`) e as três listas da tela.
- **`src/qualidade.py`** — o filtro de formato/bitrate e o ranking. Estima o bitrate quando
  o motor não informa, diversifica por usuário na hora de escolher, e sabe dizer se um
  achado é **upgrade de verdade** sobre o que você já tem.
- **`src/leitor_pasta.py`** — varre uma pasta do disco e descobre o que cada arquivo é:
  tags pelo `ffprobe`, e artista/título tirados do nome quando não há tags.
- Documentação completa do escopo (os 5 MDs acima).

E a **primeira janela já abre**:

- **`app.py` + `src/tela_configuracoes.py`** — a tela de Configurações: pasta de destino,
  **pasta compartilhada**, ligação com o slskd (com teste de conexão), formatos aceitos,
  limites da rede e o painel de requisitos da máquina.
- **`src/config.py`** — as configurações em JSON, fora do repositório, com a lista de
  pendências já escrita em português.
- **`src/sistema.py`** — o que muda entre Windows e macOS, num módulo só.

> ⚠️ **Ainda não dá para baixar música.** Falta o slskd instalado, o leitor de playlist e o
> buscador. O que existe hoje é o núcleo de lógica testado e a tela de configuração.
> O mapa completo está no [TODO.md](TODO.md).

### Abrir o app

```bash
.\.venv\Scripts\python.exe app.py
```

### Rodar os testes

```bash
.\.venv\Scripts\python.exe -m pytest tests/ -q
```
