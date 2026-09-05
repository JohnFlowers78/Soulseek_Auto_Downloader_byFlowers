# ✅ TODO — Soulseek Auto Downloader

Lista viva de pendências para **nunca esquecer nada**. Riscar (`[x]`) ao concluir.
O escopo de cada item está no [FUNCIONALIDADES.md](FUNCIONALIDADES.md), as decisões
estruturais no [ARQUITETURA.md](ARQUITETURA.md); aqui é só o "o que falta fazer".

_Atualizado em: 05/09/2026_

---

## 🔧 Fase 0 — Preparar a máquina (bloqueia quase tudo)

- [ ] **Instalar o slskd** — o motor padrão. Binário Windows, sem Docker.
      Configurar: usuário/senha do Soulseek, **pasta compartilhada** (obrigatório, ver
      GUIA_SOULSEEK.md), pasta de downloads e a **API key** que o app vai usar.
- [ ] **Segunda conta Soulseek** — para poder ter slskd e SoulseekQt ligados ao mesmo tempo
      sem que um derrube o outro. (Ou decidir que vão se alternar.)
- [ ] **Instalar o ffmpeg** e deixar no PATH — espectrograma e análise de corte.
- [ ] **Criar o app no Spotify Dashboard** (Client ID + Secret, redirect
      `http://127.0.0.1:8888/callback`).
      ⚠️ **A confirmar:** consta que o dono do app precisa ter **Premium ativo** e que há
      limite de **1 app por usuário** desde março/2026. Verificar antes de desenhar em cima.
- [ ] Definir a **pasta de destino** das músicas.
- [x] Criar o `venv` do projeto.

## 🔤 Fase 1 — Núcleo que roda sem depender de nada instalado

- [x] **`normalizador.py`** — gerador de variantes de busca (acentos, hífen, feat.,
      parênteses, só-título, núcleo) + saneamento de nome de pasta. **67 testes.**
- [x] **`modelos.py`** — as estruturas que atravessam o app (`Faixa`, `Candidato`,
      `Transferencia`), num lugar só, iguais para os dois motores.
- [x] **`qualidade.py`** — decidir se um arquivo presta (AIFF/WAV/FLAC/MP3 320/M4A) e
      ranquear candidatos. Estima o bitrate quando o motor não informa.
- [x] **`qualidade.py` — comparação com o acervo** — `vale_a_pena_trocar()` e
      `filtrar_upgrades()`: a pergunta deixa de ser "presta?" e vira "é melhor que o meu?",
      com o motivo escrito para aparecer na tela.
- [x] **`leitor_pasta.py`** — varrer uma pasta, ler tags e especificações pelo `ffprobe`,
      e tirar artista/título do nome do arquivo quando não houver tags.
- [x] **`config.py`** — configurações em JSON: pastas, credenciais, formatos aceitos,
      limites. Sem segredo no código, arquivo fora do repositório. Com `problemas()`,
      que devolve as pendências já escritas em português para a tela.
- [x] **`sistema.py`** — o que muda entre Windows e macOS isolado num módulo só
      (pasta de dados do app, procura do ffmpeg/ffprobe fora do PATH).

## 📥 Fase 2 — Ler a playlist

- [ ] **Login do Spotify nas Configurações** — botão "Entrar com o Spotify", OAuth
      Authorization Code + PKCE, guardando o refresh token.
- [ ] **`leitor_spotify.py` (API)** — ler as faixas da playlist do usuário logado, paginando.
- [ ] **Marcação "esta playlist não é minha"** na tela — decide o caminho, sem adivinhação.
- [ ] **`leitor_navegador.py`** — playlist de terceiro: abrir, rolar até o fim, ler o DOM.
      Seletores anotados num ESTRATEGIAS.md (a criar) porque o Spotify muda a página.
- [ ] **`entradas.py`** — reconhecer o que o usuário colou (link de playlist, link de faixa
      do Spotify, link do SoundCloud, ou nome escrito à mão) e devolver sempre uma **lista
      de `Faixa`**. É o que faz a busca avulsa e a playlist descerem pelo mesmo cano.
- [ ] **Ler uma faixa avulsa do Spotify** pelo link (endpoint de faixa, não de playlist).
- [ ] **Ler uma faixa do SoundCloud** pelo link (título + artista).

## 🔎 Fase 3 — Buscar e baixar

- [ ] **`motores/protocolo.py`** — a interface única que os dois motores implementam.
- [ ] **`motores/motor_slskd.py`** — buscar, ler respostas, enfileirar, acompanhar, cancelar.
- [ ] **`motores/motor_soulseekqt.py`** — a contingência por automação de tela.
      **Você vai me ensinar as telas** (onde busca, onde vê resultado, onde vê download).
- [ ] **Detectar a briga de sessão** entre os dois motores e avisar com clareza.
- [ ] **Limitador de buscas** — 34 buscas / 220 s, com espera visível. **Crítico:**
      estourar = 30 min de banimento.
- [ ] **`buscador.py`** — roda as variantes na ordem, para no primeiro resultado bom.
- [ ] **`baixador.py`** — enfileira, acompanha, classifica em ✅ baixou / ⏳ preso na fila /
      ❌ não achou.
- [ ] **Fila persistente** — fechar o app no meio e retomar sem perder nada.
- [ ] **Organizador** — mover o que baixou para `<destino>/<Nome da Playlist>/`.

## 🖥️ Fase 4 — A janela do PC (PySide/Qt)

- [x] **Tela de Configurações** (`tela_configuracoes.py`) — pastas (destino e
      compartilhada), ligação com o slskd + teste de conexão, formatos e limites, e o
      painel de requisitos. Mostra as pendências em português. **É o que já dá para abrir.**
- [x] **`app.py`** — ponto de entrada.
- [ ] Campo do link + botão de ler playlist + lista das faixas para conferir antes.
- [ ] Progresso ao vivo da busca e do download (com o "aguardando X s" do limitador).
- [ ] **As três listas**: baixadas / presas na fila / não encontradas.
- [ ] **Tela de busca avulsa** — um campo só: nome escrito à mão (com todos os acentos e
      caracteres especiais), link de faixa do Spotify ou link do SoundCloud. Emenda na
      caça (Fase 7) quando não achar.
- [ ] **Configurações**: login do Spotify, escolha do motor, pasta destino, formatos
      aceitos, limites, e o modo de acesso do celular.

## 📱 Fase 5 — O painel do celular

- [ ] **Serviço web local** rodando na mesma máquina, dentro do processo da janela.
- [ ] **Login com senha** (hash Argon2id/bcrypt) + sessão por token + limite de tentativas.
- [ ] **Modo rede local** (padrão) com HTTPS auto-assinado.
- [ ] **Modo túnel `cloudflared`** (opcional, para usar fora de casa).
- [ ] **Painel**: colar link, acompanhar progresso, ver as três listas, ver espectrogramas.
- [ ] **Servir arquivo por id interno**, nunca por caminho — fecha a travessia de diretório.
- [ ] Conferir que a API key do slskd **não** aparece em nada que chegue ao navegador.

## 📊 Fase 6 — Espectrograma

- [ ] **`espectro.py`** — `ffmpeg -lavfi showspectrumpic` gerando o PNG por faixa.
      **É a próxima peça**, e a única que trava o modo "melhorar o acervo".
- [ ] **Medir a frequência de corte** e comparar com o bitrate declarado → é o que preenche
      `ArquivoLocal.suspeito` e destrava a regra do "seu arquivo mente sobre si mesmo".
- [ ] Miniatura ao lado de cada música, nas duas telas.
- [ ] **Comparação de N versões** lado a lado (não de duas): todos os gráficos juntos, cada
      um com rótulo, formato, bitrate e o corte medido embaixo.
- [ ] **Marcar a escolhida** e guardar/descartar as demais.

## 📁 Fase 6b — Melhorar o acervo (depende da Fase 6)

- [x] **Varrer a pasta** e ler o que cada arquivo é (`leitor_pasta.py`).
- [x] **Decidir o que é upgrade de verdade** (`qualidade.py`).
- [ ] **Tela de escolher a pasta** + lista do que foi encontrado, mostrando de onde veio
      cada nome e **deixando corrigir antes de buscar**.
- [ ] **Analisar cada arquivo do acervo** pelo espectrograma antes de sair buscando.
- [ ] **Agrupar em `Comparacao`** as versões da mesma música (as do acervo + as baixadas).
- [ ] Aviso de tempo: uma pasta de 200 músicas são 200+ buscas → **mais de uma hora** pelo
      limite de 34/220 s. O usuário precisa saber disso antes de começar, não no meio.

## 🕵️ Fase 7 — Caçar o que faltou

- [ ] **Você me ensina** onde ficam escondidos os downloads livres do **Hypeddit** e do
      **SoundCloud** (gate, botão, o caminho todo).
- [ ] **`cacador.py`** — busca grátis primeiro.
- [ ] **Você me passa a lista de lojas** que entram na cotação.
- [ ] **Cotação de compra** — loja, formato, preço e link, lado a lado.

## 🧠 Fase 8 — Leitura automática do gráfico

- [ ] **Você define as regras** de interpretação (o que cada corte/faixa indica).
- [ ] Frase-resumo automática por faixa, em português, a partir dos números do áudio.

## 📦 Fase 9 — Distribuição

- [ ] **Pacote atualizador** — acha instalações, mostra ATUALIZAR ou INSTALAR NOVO,
      **nunca encosta nos dados** do usuário. (Mesmo espírito do projeto do Instagram.)
- [ ] **Pergunta o sistema** (Windows / macOS) e entrega o pacote certo.
- [ ] Build Windows — a versão testada.
- [ ] Build macOS — quando houver máquina para testar. No Mac o motor é só o slskd.

---

## ✅ Decisões já tomadas

- **Playlists**: a maioria é do próprio usuário → botão de login do Spotify nas Configurações.
  Quando não for dele, o usuário marca e o app vai pelo navegador.
- **Motores**: os dois — slskd como padrão, SoulseekQt como contingência.
- **Telas**: janela desktop (PySide/Qt) **e** painel web para o celular. Arquivos sempre na
  máquina.
- **Acesso remoto**: sem VPN/Tailscale. Rede local por padrão, túnel `cloudflared` como opção.
  Encaminhamento de porta descartado.
- **Sistemas**: Windows primeiro e testado; macOS depois, sem virar reescrita.

## ❓ Ainda em aberto

- [ ] **Onde salvar as músicas?** O caminho da pasta de destino.
- [ ] **Uma conta Soulseek ou duas?** Define se os dois motores podem conviver ligados.
- [ ] **O painel do celular vai ser usado mais em casa ou na rua?** Se for só em casa, o modo
      rede local basta e o `cloudflared` pode esperar.
