# 🎯 Funcionalidades — o que este app deve fazer

Este é o **escopo combinado**: tudo que foi pedido, organizado por módulo, com o
comportamento esperado escrito de forma que dê para conferir depois se ficou certo.

Aqui é o **"o quê"**. O **"o que falta"** está no [TODO.md](TODO.md); o **"como"** e as
descobertas ficam no [IDEIAS.md](IDEIAS.md) e no [GUIA_SOULSEEK.md](GUIA_SOULSEEK.md).

_Atualizado em: 05/09/2026_

---

## 1. 📥 Ler a playlist do Spotify

**Pedido:** _"vou te passar o link de minha playlist do spotify e você vai abrir num navegador,
inspecionar o elemento da página e copiar o nome de cada música uma por uma"_ —
_"a menos que você consiga copiar o nome das músicas de outra forma apenas acessando com o link!"_

- Colar o **link da playlist** e o app extrai a lista de faixas sozinho.
- **Botão "Entrar com o Spotify" nas Configurações** — cada usuário do app loga na própria
  conta. É o caminho normal, porque **a maioria das playlists é do próprio usuário**.
- **Dois caminhos:**
  - **API oficial do Spotify** (login OAuth) — o padrão, para **playlist do usuário logado**.
    Traz artista, título, álbum, duração e **ISRC**.
  - **Leitura do navegador (DOM)** — quando **o usuário avisa que a playlist não é dele**.
    Desde fev/2026 a API não entrega o conteúdo de playlist alheia. Rola a página até o fim
    e lê todas as faixas.
- A escolha **não é adivinhada**: existe uma marcação explícita na tela ("esta playlist não é
  minha"), porque errar o caminho custa uma tentativa perdida e confunde o diagnóstico.
- Guardar o **nome da playlist** — é ele que vai nomear a pasta de destino.
- Mostrar a lista lida na tela **antes** de sair buscando, para conferência.

## 2. 🔤 Tratar o nome das músicas (o coração do problema)

**Pedido:** _"todos os caractéres especiais e até os simples como hífen (-), acentos,
C-cedilha (ç), crase ('), til (~) e outros mais acabam tornando a busca inválida"_ —
_"como isso pode variar em cada caso, poderíamos fazer ele buscar a mesma música escrita de
formas diferentes!"_

- Para cada faixa, gerar **várias formas de escrever a mesma busca**, da mais fiel à mais
  permissiva, e tentar uma por uma até achar resultado.
- Tratamentos que cada variante pode aplicar:
  - **Hífen** — removido sempre. _(Não é frescura: no Soulseek o `-` antes de uma palavra
    significa **EXCLUIR** aquela palavra. "Artista - Título" manda o cliente excluir coisas.
    Era essa a causa das buscas vazias.)_
  - **Acentos** — `ã→a`, `ç→c`, `é→e`, `ô→o`. Muita gente salva o arquivo sem acento.
  - **Aspas, crase, apóstrofo, til solto** e demais pontuações → viram espaço.
  - **`feat.` / `ft.` / `featuring` / `part.`** e o convidado → removidos numa variante.
  - **Parênteses e colchetes** — `(Original Mix)`, `[Remastered 2011]` → removidos numa
    variante, mantidos noutra (para DJ, "Extended Mix" às vezes **é** o que importa).
  - **Só o título**, sem o artista — para quando o nome do artista está escrito diferente.
  - **Núcleo**: só as palavras significativas, sem acento e sem pontuação — a rede de arrasto.
- Cada variante é **etiquetada** com a estratégia que usou, para dar para aprender depois
  qual funciona melhor.
- ✅ **Implementado** em `src/normalizador.py`, com testes.

## 3. 🔎 Buscar no Soulseek

**Pedido:** _"realizar uma busca no app SoulSeek de Desktop"_ —
_"é possível que não seja tão fácil de trabalhar de cara com o soulseek afinal é um software
muito antigo"_ — _"Sería maravilhoso ter uma API dele disponível"_

- **Dois motores**, atrás da mesma interface interna — o resto do app não sabe qual está
  em uso:
  - **slskd (API REST)** — o padrão. Sem automação de tela, sem clique em pixel, sem OCR.
  - **SoulseekQt (automação de tela)** — a rede de segurança, para os casos em que o slskd
    não sirva. Frágil por natureza (software de 2008), então fica isolado atrás da mesma
    interface e nunca vaza para o resto do código.
- ⚠️ **Os dois não rodam juntos com a mesma conta.** O servidor Soulseek derruba a sessão
  antiga quando a mesma conta entra de novo. Usar os dois ao mesmo tempo exige **duas contas**;
  senão, alternar. O app precisa detectar e avisar em vez de deixar o usuário no escuro.
- Buscar variante por variante; parar assim que uma trouxer resultado aproveitável.
- **Respeitar o limite da rede**: no máximo **34 buscas a cada 220 segundos**. Estourar
  significa **banimento de 30 minutos** pelo servidor. O app segura a fila sozinho e mostra
  o tempo de espera.
- Fila **persistente**: fechar o app no meio e retomar de onde parou.

## 4. ⭐ Escolher os melhores resultados

**Pedido:** _"as músicas precisam ter uma qualidade específica para serem baixadas como
(Aiff, Wav, Flac, mp3 320kbps ou AAC m4a). Caso ache mais de uma opção, baixe mais de uma opção."_

- **Formatos aceitos** (o resto é descartado): **AIFF, WAV, FLAC, MP3 320 kbps, M4A/AAC**.
- Ranquear por: formato > bitrate > usuário com slot livre > velocidade > tamanho de fila.
- **Baixar mais de uma opção** quando houver — para comparar espectrograma depois.
- Conferir **duração** contra a do Spotify (tolerância configurável) para não baixar a faixa
  errada de mesmo nome.

## 5. ⬇️ Baixar e organizar

**Pedido:** _"nosso bot vai até a lista de downloads do soulseek e salva todas as que
realmente baixaram em uma pasta com o mesmo nome que tinha a playlist e um local que
indicarmos nas configurações"_

- Enfileirar os escolhidos e **acompanhar até o fim**.
- Ao concluir, mover para: `<pasta configurada>/<Nome da Playlist>/`.
- Nome da pasta **saneado** para o Windows (sem `\ / : * ? " < > |`).
- A pasta de destino é definida nas **Configurações** do app.

## 6. 📋 Relatório do que faltou

**Pedido:** _"No app também terá uma lista com as músicas que faltaram e logo abaixo quais não
foram encontradas e quais foram encontradas mas não foram baixadas, ficaram enfileiradas na
tela de downloads do Soulseek aguardando a pessoa que iria fornecer a seed mas estava offline"_

Três listas separadas, na tela:

- ✅ **Baixadas** — com formato, bitrate e tamanho.
- ⏳ **Encontradas mas presas na fila** — usuário offline, fila cheia, sem slot. Mostrar a
  posição na fila e permitir **tentar outra fonte**.
- ❌ **Não encontradas** — nenhuma variante trouxe resultado aproveitável. Mostrar quais
  variantes foram tentadas.

## 7. 📊 Espectrograma de cada faixa

**Pedido:** _"teremos um bot que passa tudo pelo aplicativo "Spek" e tira um print da análise
(do gráfico colorido gerado) e coloca ao lado das músicas encontradas, assim é possível que eu
analise os resultados em únidade ou olhando lado a lado músicas iguais encontradas por qualidade"_

- Gerar o espectrograma **sem abrir o Spek**: `ffmpeg -lavfi showspectrumpic` produz a mesma
  imagem, direto em PNG. Sem print de tela, sem recorte.
- Mostrar a miniatura **ao lado de cada faixa** na lista.
- **Comparação lado a lado** quando a mesma música foi baixada em mais de uma versão.
- **Bônus que o Spek não dá**: medir a **frequência de corte em número** e comparar com o que
  o arquivo alega. Flagra o "MP3 320" que na verdade é um 128 requentado.

## 8. 🕵️ Caçar o que faltou — de graça primeiro, comprar depois

**Pedido:** _"um botão que busque todas as músicas não foram baixadas daquela playlist para
comprar na internet (mostrar todos os resultados como uma cotação real), também existe a
chance de achar elas para baixar via soundcloud ou via Hypeddit de graça, o que é a
preferência, claro!"_

- Um **botão** que pega tudo que faltou e sai à caça, **nesta ordem de preferência**:
  1. **Grátis** — SoundCloud (faixas com download liberado) e **Hypeddit** (o download livre
     costuma estar escondido atrás de gate/botão — você vai me ensinar onde).
  2. **Compra** — varrer as lojas e montar uma **cotação real**: loja, formato oferecido,
     preço, link. Lado a lado, para escolher.
- Você ainda vai indicar **quais lojas** entram na cotação.

## 9. 🧠 Descrição automática do espectrograma (fase futura)

**Pedido:** _"vou querer definir mais específicamente sobre o que os resultados dos gráficos
indicam para que você ja analise por conta e me traga uma pré-descrição de cada análise"_

- Você define as regras de leitura ("corte em 16 kHz = 128 kbps disfarçado", "faixa preta no
  topo = upscale", etc.).
- O app traduz o gráfico numa frase em português, por faixa.
- **Sem custo de IA**: os números vêm do próprio áudio, não de OCR na imagem.

## 10. 🖥️📱 Duas telas: a janela do PC e o painel do celular

**Pedido:** _"manter a janela desktop (PySide/Qt) mas também vou querer ter uma parte
Front-End rodando em navegador para que o usuário possa colar playlist de seu celular e
assistir e analisar os resultados por lá, mas os arquivos de músicas devem ser sempre
disponibilizados na máquina afinal é melhor para gerenciar os arquivos para dentro de
pendrives (DJ Life)"_

- **Janela desktop (PySide/Qt)** — o app completo: configurações, motores, pastas, tudo.
- **Painel web** — para usar do **celular**: colar o link da playlist, acompanhar o progresso,
  ver as três listas e **analisar os espectrogramas** (que é onde a tela grande do celular
  ajuda de verdade).
- **Os arquivos ficam sempre na máquina.** O celular é controle remoto e visor — nunca
  destino de download. Quem gerencia pendrive é o DJ, no PC.
- Os dois falam com **o mesmo miolo**: um serviço local só, duas caras.

## 11. 🔒 Acesso do celular sem VPN

**Pedido:** _"não quero que rode em Tailscale (não gosto da ideia de ter de ficar ativando e
desativando VPN para usar meus apps, então vamos ter de cuidar melhor da parte de segurança
nas requisições)"_

Sem VPN, a segurança tem que estar **na aplicação**. Regras que valem para qualquer modo de
acesso (detalhes e a escolha do modo estão no [ARQUITETURA.md](ARQUITETURA.md)):

- **O navegador nunca fala com o slskd.** Ele fala só com o nosso serviço, que guarda a API
  key. Chave de motor não chega ao celular em hipótese alguma.
- **Login com senha + sessão por token**, com limite de tentativas. Nada de "quem tem o
  endereço, entra".
- **HTTPS sempre** que sair da máquina.
- **O painel do celular não comanda o sistema.** Ele manda link de playlist e lê resultado.
  Nada de escolher caminho de pasta, abrir arquivo ou rodar processo pelo navegador.
- **Padrão de fábrica é fechado**: só rede local. Sair disso é uma decisão explícita nas
  Configurações, com o aviso do que muda.

## 12. 📦 Instalador que reconhece a máquina — Windows e macOS

**Pedido:** _"ao instalar um app por meio do nosso 'pacote atualizador' que vamos gerar, ele
pergunte se a máquina que está sendo instalada é uma versão MacOS ou Windows, afinal pode
variar. Isso é importante pois vários DJs usam macbook"_ — _"a versão de Macbook não vou
conseguir ficar arrumando tanto pois não tenho um disponível"_

- **Pacote atualizador** no mesmo espírito do usado no projeto do Instagram: acha instalações
  existentes, mostra se vai **ATUALIZAR** ou **INSTALAR NOVO**, e **nunca encosta nos dados**
  do usuário (configurações, logins, fila, histórico).
- **Pergunta o sistema** (Windows / macOS) e entrega o pacote certo.
- **Windows é a versão testada**; macOS entra depois, quando houver máquina para testar.
  Até lá o código já nasce **sem caminho fixo de Windows**: nada de `C:\` escrito na mão,
  nada de `\` montado à unha — só `pathlib`, e as pastas do sistema resolvidas por função.
  Assim a versão macOS é um porte, não uma reescrita.
- ⚠️ A automação de tela do SoulseekQt é a parte que **não** atravessa sistemas: o macOS
  precisa de permissão de acessibilidade e as janelas são outras. No Mac, o motor é o slskd.

## 13. 🔍 Busca avulsa — uma música só

**Pedido:** _"uma tela onde o usuário escreve o nome de uma única música (com acentos,
apóstrofes, hífens, caracteres especiais e tudo completo como realmente é o nome da música e
nome do artista) ou cola o link de uma música do spotify ou soundcloud e o nosso app faz o
trabalho pesado de buscar no soulseek ou se não encontrar onde baixar e devolver os
resultados"_

- Uma tela com **um campo só**, que aceita três coisas e descobre sozinho qual é:
  - **o nome escrito à mão** — `Céu — Malemolência (Ao Vivo)`, com todo acento, apóstrofo,
    hífen e til que a música realmente tem;
  - **link de música do Spotify**;
  - **link de música do SoundCloud**.
- **Escrever bonito é o jeito certo.** O usuário não deve "limpar" nada — quanto mais fiel o
  nome, melhor, porque é justamente da grafia completa que o `normalizador.py` deriva as
  variantes. Pedir para o usuário adivinhar o tratamento seria devolver a ele o problema que
  o app existe para resolver.
- Busca no Soulseek com as mesmas variantes, o mesmo filtro de qualidade e o mesmo ranking.
- **Se não achar, já emenda na caça** (§8): grátis primeiro (SoundCloud/Hypeddit), depois a
  cotação de compra. Numa tela só, sem o usuário ter que pedir de novo.
- Serve tanto na janela do PC quanto no painel do celular — é a tela que mais combina com o
  uso do celular ("lembrei de uma música agora").

> **Isto não é um módulo novo, é uma porta de entrada nova.** Playlist do Spotify, playlist
> lida do navegador, nome digitado, link de faixa — tudo vira a mesma lista de `Faixa` e
> desce pelo mesmo cano. Por isso o núcleo trabalha com **lista de faixas**, nunca com
> "playlist": uma busca avulsa é só uma lista de uma faixa só. Ver [ARQUITETURA.md](ARQUITETURA.md).

## 14. 📁 Melhorar o acervo — partir de uma pasta

**Pedido:** _"eu também posso fornecer uma pasta (pasta que carrega arquivos) com músicas
dentro e todas essas músicas passaram pelo SPEK para serem analisadas e buscadas com o nome
delas dentro do soulseek buscando novas assim como o mecanismo de busca que já citei"_ —
_"Ao encontrar, baixar as músicas encontradas e analisá-las também no spek apresentando
gráficos ao lado das versões antigas para a seleção por meio de análise visual do usuário!
Comparar todas as músicas comparadas (às vezes podem ser mais de 2 → mais de 2 na mesma pasta
&& mais de duas baixadas)"_

O fluxo, de ponta a ponta:

1. **Apontar uma pasta.** O app varre (inclusive subpastas) e lista o que achou.
2. **Analisar cada arquivo que já é seu** — o espectrograma e as especificações reais.
3. **Descobrir o nome de cada música**, para poder buscar.
4. **Buscar versão melhor** no Soulseek, com as mesmas variantes de sempre.
5. **Baixar o que for upgrade** de verdade.
6. **Analisar o que baixou** e mostrar os gráficos **lado a lado com os antigos**.
7. **Você escolhe olhando**, e o app fica com o que você marcar.

### A virada de lógica: não é "presta?", é "é melhor que o meu?"

Vindo de uma playlist, qualquer arquivo aprovado serve — não há nada com que comparar.
Vindo da sua pasta, aprovar não basta: **baixar um FLAC para substituir um FLAC** é gastar
cota de busca, banda e o seu tempo para terminar exatamente onde começou.

Por isso a decisão passa por uma segunda pergunta, e **o motivo aparece escrito na tela**:

| Você tem | Achou | Decisão |
|---|---|---|
| MP3 128 | FLAC | ✅ sobe de "com perda, abaixo do ideal" para "sem perda" |
| MP3 128 | MP3 320 | ✅ sobe de degrau |
| FLAC 16 bits | FLAC 24/96 | ✅ sobe de degrau |
| FLAC | MP3 320 | ❌ seria piora |
| FLAC | FLAC igual | ❌ mesma qualidade — não compensa |
| MP3 320 **suspeito** | MP3 320 | ✅ o seu mente sobre si mesmo, vale conferir |
| qualidade desconhecida | qualquer coisa boa | ✅ vale comparar |

Quando o app **não** baixa, você precisa saber que foi decisão e não falha. "Achei, mas é a
mesma coisa que você já tem" é informação; silêncio vira bug aparente.

### A varredura aceita formato ruim de propósito

OGG, WMA, MP3 128 — os formatos que o filtro de playlist rejeita entram aqui. São
**exatamente** os arquivos que mais valem a troca. Varrer só o que "presta" deixaria de fora
o alvo da funcionalidade.

### De onde sai o nome da música

- **Tags do arquivo** primeiro (artista, título, álbum, e o ISRC quando houver).
- **Nome do arquivo** como reserva, tratando o que acervo de DJ costuma ter grudado:
  numeração (`01 - `, `A1. `), rótulo de gravadora (`[Label001]`), site
  (`www.site.com_`), selo de qualidade no fim (`(320kbps)`, `[FLAC]`, `[2011]`) e
  sublinhado no lugar de espaço.
- **A tela mostra de onde veio** cada nome ("tags" / "nome do arquivo" / "tags + nome do
  arquivo") e **deixa corrigir antes de buscar** — nome de arquivo erra, e uma busca com
  nome errado é cota queimada.
- Duas coisas que o leitor **não** faz: chutar artista quando não há separador (artista
  errado vira termo obrigatório e derruba todos os resultados), e remover `(Original Mix)` /
  `(Extended Mix)` — para DJ isso **é** o nome da faixa. Quem decide removê-los é o
  normalizador, na variante certa.

### A comparação é de N versões, não de duas

Foi pedido explicitamente: pode haver **mais de duas na pasta** e **mais de duas baixadas**.
Três rips do mesmo vinil mais dois FLACs da rede é caso comum. A tela mostra todos os
espectrogramas juntos, cada um com seu rótulo ("no seu acervo" / "baixada de fulano"), com
formato, bitrate e a **frequência de corte medida** embaixo de cada gráfico.

---

## ⚖️ Como este app se comporta na rede

O Soulseek é uma rede de gente real compartilhando de casa, com banda de casa. Duas coisas
não são negociáveis no projeto:

- **Respeitar o limite de buscas** (34/220 s) — não é só para evitar o banimento de 30 min, é
  para não jogar carga no servidor da rede.
- **Compartilhar de volta** — o slskd deve ficar com uma pasta compartilhada configurada.
  Uma conta que só puxa e nunca oferece é bloqueada pelos próprios usuários, e o app
  simplesmente para de funcionar.

E o módulo de compra existe justamente porque a intenção é comprar o que não se acha.
