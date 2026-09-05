# 🔌 Guia Soulseek — como a rede funciona por dentro

A parte dura e específica: por que as buscas falham, quanto dá para buscar sem tomar
banimento, e como o app conversa com a rede. Anotado aqui porque é conhecimento que se perde
entre uma versão e outra.

_Atualizado em: 05/09/2026_

---

## ⛔ O hífen não "quebra" a busca — ele EXCLUI resultados

Esta é a descoberta que explica a maior parte das buscas vazias.

No cliente oficial do Soulseek, o campo de busca aceita **operadores**. Os termos são
combinados com **E** (todos precisam aparecer), e um **`-` colado antes de uma palavra
significa "exclua tudo que tenha essa palavra"**.

Então quando se busca:

```
Djavan - Se
```

o cliente entende: _"me traga arquivos que contenham `Djavan`, **e que NÃO contenham** `Se`"_.

O resultado é vazio ou quase vazio — não porque o hífen é um caractere "inválido", mas porque
ele é um **comando**, e você mandou o comando errado sem saber.

**Regra do app:** nenhuma consulta pode conter `-`. Nunca. Ele vira espaço, sempre.

## 🔤 Os outros caracteres — por que atrapalham

Os demais são um problema diferente, e mais simples: **a busca do Soulseek casa texto com o
nome do arquivo e da pasta** de quem compartilha. Não há normalização do lado do servidor.

Se o arquivo na máquina do sujeito se chama `Djavan - Nao Vou Ficar.mp3` (sem til, como muita
gente salva), buscar por `Não` não casa com `Nao`. E vice-versa.

Por isso a estratégia não é "achar o tratamento certo" — **não existe um certo**. A estratégia
é **buscar a mesma música escrita de várias formas**, que foi exatamente a sua intuição:

| Tratamento | Vira | Por quê |
|---|---|---|
| `-` (hífen) | espaço, **sempre** | é operador de exclusão |
| `ã ç é ô` (acentos) | `a c e o` | metade da rede salva sem acento |
| `' " \` ~` | espaço | pontuação não casa de forma confiável |
| `feat. / ft. / part.` | removido | quase nunca está no nome do arquivo |
| `(Original Mix)` | removido **numa** variante | mas mantido noutra — para DJ, às vezes é o que importa |
| nome do artista | removido **numa** variante | grafia do artista varia demais |

Cada consulta gerada leva a etiqueta da estratégia que usou. Com o tempo dá para ver **qual
variante mais acerta** e começar por ela.

## ⏱️ O limite de buscas — 34 a cada 220 segundos

**O servidor da rede bane por 30 minutos quem busca demais em pouco tempo.**

O número de referência, usado pelas ferramentas consolidadas da comunidade, é
**34 buscas a cada 220 segundos** (~9 buscas por minuto).

Isso não é detalhe de implementação, é o que dita o ritmo do app:

> Uma playlist de **100 faixas** × até **3 variantes** cada = **300 buscas** =
> **no mínimo ~33 minutos**, mesmo que tudo dê certo.

Consequências no desenho:

- O limitador de buscas é **obrigatório**, não opcional.
- A tela precisa mostrar **"aguardando X s"** — senão parece travado.
- A fila tem que ser **persistente**: ninguém vai deixar a janela aberta meia hora sem poder
  fechar.
- Vale **parar na primeira variante que der certo**, para não gastar buscas à toa.

## 🤝 Compartilhar de volta não é opcional

O Soulseek é gente real servindo arquivo da banda de casa. Quem só puxa e não oferece nada é
bloqueado individualmente pelos usuários — e uma conta bloqueada por muita gente simplesmente
para de conseguir baixar.

**O slskd precisa de uma pasta compartilhada configurada.** Não é etiqueta, é requisito de
funcionamento.

---

## 🛠️ slskd — o motor

O SoulseekQt original (o de 2008) **não tem API**. Sua desconfiança estava certa.

Mas o [**slskd**](https://github.com/slskd/slskd) é um cliente moderno da **mesma rede**, que
roda como serviço e expõe **API REST** completa. Windows nativo, Docker opcional.

### Wrapper Python

```bash
pip install slskd-api
```

```python
import slskd_api
slskd = slskd_api.SlskdClient(host, api_key, url_base)
```

### Os métodos que interessam

**Buscar** — `slskd.searches`:

| Método | Assinatura | Devolve |
|---|---|---|
| `search_text(...)` | `searchText`, `id=None`, `fileLimit=10000`, `filterResponses=True`, `minimumPeerUploadSpeed=0`, `minimumResponseFileCount=1`, `responseLimit=100`, `searchTimeout=15000` | `SearchState` — **sem os resultados** |
| `state(id, includeResponses=False)` | consulta o andamento | `SearchState` |
| `search_responses(id)` | pega os resultados | `list[SearchResponseItem]` |

> A busca é **assíncrona**: `search_text` só abre a busca. Os arquivos chegam depois, via
> `search_responses(id)`. Tem que esperar e ir lendo.

**Baixar** — `slskd.transfers`:

| Método | Assinatura | Devolve |
|---|---|---|
| `enqueue(username, files)` | os arquivos vêm dos resultados da busca | `bool` |
| `get_all_downloads(includeRemoved=False)` | tudo que está baixando | `list[Transfer]` |
| `get_download(username, id)` | um download | `Transfer` |
| `get_queue_position(username, id)` | **a posição na fila do outro usuário** | `int` ou `str` |
| `cancel_download(username, id, remove=False)` | cancela | `bool` |

`get_queue_position` é o que alimenta a lista **"⏳ presas na fila"** que você pediu — dá para
mostrar "você é o 14º na fila desse usuário".

### Referência que vale estudar

O [**sockseek**](https://github.com/fiso64/slsk-batchdl) (antes `slsk-batchdl`) é um CLI que
já faz boa parte deste trabalho. Não vamos usá-lo como dependência, mas as decisões dele são
mapa de mina evitada — foi de lá que vieram os números do limitador de buscas e a ideia de
separar **condições obrigatórias** (formato, tolerância de duração) de **preferências** (o
que só ordena o ranking).

---

## 📊 Espectrograma sem o Spek

O Spek é interface gráfica (wxWidgets) sem linha de comando no build oficial — **não tem API**.
Mas por baixo ele é o **ffmpeg**. Então:

```bash
ffmpeg -i "musica.flac" -lavfi showspectrumpic=s=1024x512:legend=1 "musica.png"
```

Mesma imagem, direto em PNG, sem abrir janela nem dar print.

E o número que realmente denuncia a qualidade — a **frequência de corte** — sai do áudio, não
da imagem:

| O que se vê | O que significa |
|---|---|
| conteúdo até ~20 kHz | FLAC/WAV/AIFF ou MP3 320 de verdade |
| corte seco em ~19 kHz | MP3 320 legítimo |
| corte seco em ~16 kHz | 128 kbps — **um "320" com corte em 16 kHz é transcodificação** |
| corte em ~15 kHz ou menos | fonte ruim, independente do que o arquivo alega |

Comparar **o que o arquivo diz ser** com **o que ele é** é o que pega o arquivo maquiado.
Tudo isso é conta em cima do áudio: **sem OCR, sem Tesseract, sem API de IA, sem custo**.

> Existem ainda o **Spek-X** (fork com linha de comando) e o **spek-rs** (reescrita em Rust),
> ambos por cima do mesmo `showspectrumpic`. Só valem se um dia quisermos a estética exata
> do Spek — o cálculo não precisa deles.
