# 🎯 Funcionalidades — o que este app deve fazer

Este é o **escopo combinado**: tudo que foi pedido, organizado por módulo, com o
comportamento esperado escrito de forma que dê para conferir depois se ficou certo.

Aqui é o **"o quê"**. O **"o que falta"** está no [TODO.md](TODO.md); o **"como"** e as
descobertas ficam no [IDEIAS.md](IDEIAS.md) e no [GUIA_SOULSEEK.md](GUIA_SOULSEEK.md).

_Atualizado em: 16/08/2026_

---

## 1. 📥 Ler a playlist do Spotify

**Pedido:** _"vou te passar o link de minha playlist do spotify e você vai abrir num navegador,
inspecionar o elemento da página e copiar o nome de cada música uma por uma"_ —
_"a menos que você consiga copiar o nome das músicas de outra forma apenas acessando com o link!"_

- Colar o **link da playlist** e o app extrai a lista de faixas sozinho.
- **Dois caminhos**, escolhidos automaticamente:
  - **API oficial do Spotify** (login OAuth) — para **playlists suas**. Traz artista, título,
    álbum, duração e **ISRC**.
  - **Leitura do navegador (DOM)** — para **playlists de terceiros**, que desde fev/2026 a API
    não entrega mais o conteúdo. Rola a página até o fim e lê todas as faixas.
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

- **A API existe**: o app conversa com o **slskd** (cliente moderno da rede Soulseek) por
  **REST**. Sem automação de tela, sem clique em pixel, sem OCR.
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
