# ✅ TODO — Soulseek Auto Downloader

Lista viva de pendências para **nunca esquecer nada**. Riscar (`[x]`) ao concluir.
O escopo de cada item está no [FUNCIONALIDADES.md](FUNCIONALIDADES.md); aqui é só o
"o que falta fazer", na ordem em que compensa fazer.

_Atualizado em: 16/08/2026_

---

## 🔧 Fase 0 — Preparar a máquina (bloqueia quase tudo)

- [ ] **Instalar o slskd** — o motor. Binário Windows, sem Docker.
      Configurar: usuário/senha do Soulseek, **pasta compartilhada** (obrigatório, ver
      GUIA_SOULSEEK.md), pasta de downloads e a **API key** que o app vai usar.
- [ ] **Instalar o ffmpeg** e deixar no PATH — espectrograma e análise de corte.
- [ ] **Criar o app no Spotify Dashboard** (Client ID + Secret, redirect
      `http://127.0.0.1:8888/callback`).
      ⚠️ **A confirmar:** consta que o dono do app precisa ter **Premium ativo** e que há
      limite de **1 app por usuário**. Verificar no dashboard antes de desenhar em cima disso.
- [ ] Definir a **pasta de destino** das músicas (vai para as Configurações do app).
- [ ] Criar o `venv` do projeto e instalar o `requirements.txt`.

## 🔤 Fase 1 — Núcleo que roda sem depender de nada instalado

- [x] **`normalizador.py`** — gerador de variantes de busca (acentos, hífen, feat.,
      parênteses, só-título, núcleo) + saneamento de nome de pasta. **Com testes.**
- [ ] **`modelos.py`** — as estruturas que atravessam o app (`Faixa`, `Candidato`,
      `Resultado`), num lugar só.
- [ ] **`config.py`** — configurações em JSON: pastas, credenciais, formatos aceitos,
      limites de busca. Sem segredo no código.
- [ ] **`qualidade.py`** — decidir se um arquivo presta (AIFF/WAV/FLAC/MP3 320/M4A) e
      ranquear candidatos. Lógica pura, testável sem rede.

## 📥 Fase 2 — Ler a playlist

- [ ] **`leitor_spotify.py` (API)** — OAuth Authorization Code + PKCE, ler faixas da
      **sua** playlist, paginando. Guardar o refresh token.
- [ ] **`leitor_spotify.py` (navegador)** — plano B para playlist de terceiros: abrir,
      rolar até o fim, ler o DOM. Seletores anotados no ESTRATEGIAS (a criar) porque
      o Spotify muda a página.
- [ ] Detectar sozinho qual dos dois caminhos usar, e avisar na tela qual usou.

## 🔎 Fase 3 — Buscar e baixar

- [ ] **`slskd_cliente.py`** — camada fina sobre a API do slskd (buscar, ler respostas,
      enfileirar, listar transferências, cancelar).
- [ ] **Limitador de buscas** — 34 buscas / 220 s, com espera visível. **Crítico:**
      estourar = 30 min de banimento.
- [ ] **`buscador.py`** — roda as variantes na ordem, para no primeiro resultado bom.
- [ ] **`baixador.py`** — enfileira os escolhidos, acompanha até o fim, classifica em
      ✅ baixou / ⏳ preso na fila / ❌ não achou.
- [ ] **Fila persistente** — fechar o app no meio e retomar sem perder nada.
- [ ] **Organizador** — mover o que baixou para `<destino>/<Nome da Playlist>/`.

## 🖥️ Fase 4 — A tela

- [ ] Definir a cara do app — **decidir a stack** (Tkinter, PySide, ou web local).
- [ ] Campo do link + botão de ler playlist + lista das faixas para conferir antes.
- [ ] Progresso ao vivo da busca e do download.
- [ ] **As três listas**: baixadas / presas na fila / não encontradas.
- [ ] Tela de **Configurações**: pasta destino, credenciais, formatos aceitos, limites.

## 📊 Fase 5 — Espectrograma

- [ ] **`espectro.py`** — `ffmpeg -lavfi showspectrumpic` gerando o PNG por faixa.
- [ ] Miniatura ao lado de cada música na lista.
- [ ] **Comparação lado a lado** das versões da mesma música.
- [ ] **Medir a frequência de corte** e comparar com o bitrate declarado → marcar os
      arquivos maquiados.

## 🕵️ Fase 6 — Caçar o que faltou

- [ ] **Você me ensina** onde ficam escondidos os downloads livres do **Hypeddit**
      (gate, botão, o caminho todo) e do **SoundCloud**.
- [ ] **`cacador.py`** — busca grátis primeiro (SoundCloud / Hypeddit).
- [ ] **Você me passa a lista de lojas** que entram na cotação.
- [ ] **Cotação de compra** — loja, formato, preço e link, lado a lado.

## 🧠 Fase 7 — Leitura automática do gráfico

- [ ] **Você define as regras** de interpretação (o que cada corte/faixa indica).
- [ ] Frase-resumo automática por faixa, em português, a partir dos números do áudio.

---

## ❓ Decisões em aberto (precisam de você)

- [ ] **Suas playlists ou de terceiros?** Define se a Fase 2 começa pela API ou pelo
      navegador. (Se forem suas, o caminho é muito mais limpo — e vem o ISRC junto.)
- [ ] **Instalar o slskd, ou insistir no SoulseekQt antigo?** A recomendação é slskd, com
      folga. O antigo exigiria automação de tela em software de 2008.
- [ ] **Qual a cara do app?** Janela desktop ou página local no navegador.
- [ ] **Onde salvar as músicas?** O caminho da pasta de destino.
