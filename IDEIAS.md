# 💡 Ideias e Observações — Soulseek Auto Downloader

Documento vivo, separado do README: aqui ficam as **observações de funcionamento** que valem
ouro na operação e as **ideias futuras** discutidas durante o desenvolvimento — para nada se
perder entre uma versão e outra. As observações mais importantes também vão para o README.

_Atualizado em: 16/08/2026_

---

## 📌 Observações de operação

### O hífen não era "caractere inválido" — era um comando
A intuição de que caracteres especiais quebravam a busca estava certa no efeito e errada na
causa, e a diferença muda o conserto. Acento, cedilha e til são problema **de grafia**: o
arquivo do outro sujeito está salvo sem eles. Já o hífen é problema **de sintaxe**: o cliente
Soulseek lê `-palavra` como "exclua o que tiver essa palavra". Buscar `Djavan - Se` pede
literalmente arquivos com "Djavan" e **sem** "Se".

Por isso os dois recebem tratamentos diferentes no `normalizador.py`: acento vira variante
(uma busca com, outra sem, porque não dá para saber como o outro catalogou), e hífen sai
**sempre, de todas**, sem variante nenhuma.

### O limite de buscas manda no ritmo do app inteiro
34 buscas a cada 220 segundos. Estourou, o servidor bane por 30 minutos. Isso não é um
detalhe de implementação — é o que define a experiência:

> 100 faixas × 3 variantes = 300 buscas = **~33 minutos no melhor caso**.

Daí três decisões que já nascem tomadas: a busca **para na primeira variante que der certo**
(cada variante extra é cota queimada), a fila é **persistente** (ninguém vai ficar meia hora
com a janela aberta), e a tela **mostra o "aguardando X s"** — senão o app parece travado e
o usuário mata o processo no meio.

### A ordem das variantes não é cosmética
`(Extended Mix)` e `(Original Mix)` são removidos **depois** da remoção do `feat.`, e não
junto. Para quem é DJ, "Extended Mix" muitas vezes **é** a faixa certa — remover cedo demais
faria o app baixar a versão errada com ar de acerto. Já o `feat.` quase nunca está no nome do
arquivo, então sai antes sem prejuízo.

### O ISRC é a rede de segurança contra a faixa errada
Quando a playlist é lida pela API oficial, cada faixa vem com **ISRC** — o código único da
gravação. Duas músicas com o mesmo nome e o mesmo artista podem ser gravações diferentes
(estúdio, ao vivo, remaster), e o ISRC distingue. Se o arquivo baixado tiver ISRC nas tags,
dá para confirmar o acerto sem ouvir. É mais um motivo para preferir o caminho da API ao
caminho do navegador.

---

## 🔮 Ideias futuras

### Aprender qual variante mais acerta
Cada variante já sai etiquetada com a estratégia. Guardando qual delas fechou o download em
cada faixa, dá para descobrir o padrão pessoal do acervo — se música brasileira quase sempre
resolve em `sem_acentos` e eletrônica em `sem_parenteses`, o app pode **começar por ela** e
economizar cota de busca. Melhora sozinho com o uso, sem IA nenhuma.

### Preferir quem já serviu bem
O slskd informa velocidade, fila e slot livre de cada usuário. Guardando quem entregou rápido
e íntegro no passado, dá para **ranquear por reputação própria**. Numa rede de gente real,
o mesmo sujeito que tem um FLAC bom costuma ter os outros também — vale investigar a pasta
inteira de quem acertou (o slskd deixa navegar os compartilhamentos alheios).

### Espectrograma como filtro, não só como relatório
Hoje o desenho é: baixa, depois analisa, você olha. Mas dá para fechar o ciclo — se a análise
detectar corte em 16 kHz num arquivo que se diz 320, o app **descarta sozinho e vai buscar
outra fonte**, sem esperar você olhar. A imagem continua lá para conferência, mas deixa de
ser o único juiz.

### Comparar as versões antes de escolher
Quando a mesma música vem em três fontes, o lado a lado dos espectrogramas é bonito mas é
trabalho manual. Com o corte medido em número, o app pode já **ordenar do melhor para o pior**
e deixar o vencedor marcado — a comparação visual vira conferência, não decisão.

### Um "modo acervo" além do modo playlist
A mesma máquina serve para varrer uma pasta de músicas que **você já tem** e apontar quais
estão em qualidade ruim ou são transcodificação disfarçada — e então buscar substituto na
rede. A playlist do Spotify é uma porta de entrada; a análise de qualidade vale para tudo.

### Ler o disco inteiro, não só a faixa
Quando várias faixas da playlist são do mesmo álbum, buscar o **álbum** de uma vez é mais
econômico que buscar faixa por faixa — uma busca traz dez arquivos. Economiza cota do limite
e costuma render qualidade mais consistente, porque veio tudo do mesmo rip.

---

## ❓ A confirmar

- **Spotify exige Premium para o dono do app?** A documentação de uma ferramenta da
  comunidade afirma que sim, e que há limite de **1 app por usuário** desde março/2026.
  Não foi confirmado na fonte oficial — checar no dashboard antes de desenhar em cima.
- **Playlist de terceiro pela API**: a mudança de fev/2026 diz que playlists que não são do
  usuário devolvem "apenas metadados, não o conteúdo". Vale testar na prática com um link
  real para ver o que exatamente volta — pode ser que playlist pública colaborativa se
  comporte diferente.
- **Hypeddit e SoundCloud**: onde ficam escondidos os downloads liberados. Você vai me
  mostrar o caminho — gate, botão, o passo a passo.
- **Lojas para a cotação**: quais entram.
