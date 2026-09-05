# 🏗️ Arquitetura — as decisões estruturais

Por que o app é montado assim. Cada decisão aqui tem custo, e o custo está escrito junto —
para quando bater a dúvida daqui a três meses.

_Atualizado em: 05/09/2026_

---

## 🧩 Um miolo, várias caras

```
                    ┌──────────────────────────────────┐
                    │            NÚCLEO                │
                    │  leitor de playlist              │
                    │  normalizador de busca           │
                    │  qualidade / ranking             │
                    │  espectro (ffmpeg)               │
                    │  fila persistente                │
                    └────────────┬─────────────────────┘
                                 │
              ┌──────────────────┼──────────────────┐
              │                  │                  │
        ┌─────▼─────┐     ┌──────▼──────┐    ┌──────▼───────┐
        │  Janela   │     │  Serviço    │    │ Motores      │
        │  PySide   │     │  web local  │    │ Soulseek     │
        │  (o PC)   │     │  (celular)  │    │ (2 opções)   │
        └───────────┘     └─────────────┘    └──────────────┘
```

O serviço web roda **dentro do mesmo processo** da janela desktop, numa thread de fundo.
Um processo, um estado, uma fila. Se fossem dois programas, a fila teria que ser sincronizada
entre eles — complexidade que não paga.

**O celular é controle remoto e visor, nunca destino.** Os arquivos de música ficam sempre na
máquina, porque é de lá que saem para o pendrive.

## 🚪 Várias entradas, um cano só

O núcleo **nunca fala em "playlist"**. Ele trabalha com **lista de `Faixa`** — e é isso que
faz cada porta de entrada nova custar quase nada:

```
link de playlist do Spotify   ─┐
playlist de terceiro (DOM)    ─┤
nome escrito à mão            ─┼──►  list[Faixa]  ──►  normalizador ──► busca ──► download
link de faixa do Spotify      ─┤
link do SoundCloud            ─┤
uma pasta do disco            ─┘
```

Uma **busca avulsa é uma lista de uma faixa só**. Não existe caminho de código separado para
ela: mesma normalização, mesmo filtro de qualidade, mesmo ranking, mesma fila. Se amanhã
aparecer "importar de um arquivo .txt" ou "ler a fila do Rekordbox", é só mais uma entrada.

O módulo `entradas.py` é quem olha o que o usuário colou e decide de qual porta veio.

### A pasta é a única entrada que traz bagagem

Todas as outras entradas dão só o **nome** da música. A pasta dá o nome **e um arquivo que
já existe** — e isso muda a pergunta lá na frente:

```
playlist  →  "esse arquivo presta?"            →  qualidade.avaliar()
pasta     →  "esse arquivo é melhor que o meu?" →  qualidade.vale_a_pena_trocar()
```

Sem essa segunda pergunta, o modo "melhorar o acervo" baixaria um FLAC para substituir um
FLAC: cota de busca, banda e tempo do usuário gastos para terminar onde começou. É por isso
que `ArquivoLocal` carrega o degrau de qualidade real do arquivo, e não só o nome.

E é por isso que a varredura aceita **OGG, WMA e MP3 128**, formatos que o filtro de playlist
rejeita: ali eles são lixo, aqui são o alvo.

### Ler tags com `ffprobe`, não com uma biblioteca nova

O `ffprobe` vem junto com o ffmpeg, que **já é requisito** para o espectrograma. Ele lê tags
e especificações técnicas (duração, bitrate, taxa, profundidade de bits) numa chamada só, em
qualquer formato que o ffmpeg abra — MP3, FLAC, WAV, AIFF, WMA, o que aparecer.

Uma dependência de sistema em vez de duas coisas para instalar e manter.

O custo dessa escolha está isolado: toda a lógica mora em `montar_arquivo_local()`, que
recebe o JSON já pronto. A chamada ao programa é uma função fina de cinco linhas. Resultado
prático: **a leitura se testa com JSON escrito à mão**, sem ffmpeg instalado e sem arquivo
de áudio de verdade. E, sem ffmpeg, o módulo ainda lê os nomes pelo nome do arquivo em vez
de travar.

## 🔌 Dois motores atrás de uma porta só

Decisão tomada com o custo conhecido: manter os dois **dobra a manutenção**, e a automação de
tela é a metade frágil. Vale como rede de segurança, mas só se ficar **isolada**.

```python
class MotorSoulseek(Protocol):
    def buscar(self, consulta: str) -> list[Candidato]: ...
    def enfileirar(self, candidato: Candidato) -> bool: ...
    def transferencias(self) -> list[Transferencia]: ...
    def posicao_na_fila(self, candidato: Candidato) -> int | None: ...
```

| | `MotorSlskd` | `MotorSoulseekQt` |
|---|---|---|
| Como fala | API REST | automação de tela |
| Confiabilidade | alta | baixa (janela muda, timing) |
| Dados que devolve | bitrate, tamanho, fila, velocidade | pouco — às vezes só nome e tamanho |
| macOS | funciona igual | **não** (permissão de acessibilidade, outras janelas) |
| Papel | padrão | contingência |

**Consequência que atravessa o código todo:** o `MotorSoulseekQt` às vezes não sabe o bitrate.
Então nada no núcleo pode *exigir* bitrate — quando ele falta, é **estimado pelo tamanho e
pela duração**. É por isso que `qualidade.py` aceita candidato sem bitrate declarado.

### ⚠️ As duas sessões brigam

O servidor Soulseek **derruba a sessão antiga** quando a mesma conta entra de novo. slskd e
SoulseekQt ligados ao mesmo tempo, com a mesma conta, ficam se expulsando em loop.

Saídas: **duas contas** (uma para cada motor) ou **alternar**. O app precisa detectar a
desconexão em ciclo e dizer o que está acontecendo — senão vira um bug de sintoma bizarro.

## 🔒 Acesso do celular — sem VPN, com segurança de verdade

Sem VPN, a proteção sai da rede e vai para a aplicação. São **dois modos**, e o padrão de
fábrica é o fechado.

### Modo 1 — Rede local (padrão)

O serviço escuta na rede de casa; o celular entra pelo IP local. **Zero exposição à
internet** — não existe porta aberta para o mundo. Cobre o caso real da maioria: o DJ e o
celular na mesma Wi-Fi do estúdio.

Certificado HTTPS auto-assinado, aceito uma vez no celular. O aviso feio aparece só na
primeira conexão.

### Modo 2 — Túnel de saída (para usar fora de casa)

Quando precisar acessar de fora, **túnel de saída via `cloudflared`** — o mesmo que já é
usado no projeto do Instagram, então não é ferramenta nova.

Por que ele e não abrir porta no roteador:

| | Túnel de saída | Encaminhamento de porta |
|---|---|---|
| Porta aberta na sua casa | **nenhuma** | sim, para o mundo |
| Se o app tiver uma falha | limitada ao app | vira porta de entrada na sua rede |
| HTTPS | certificado válido, de graça | você que se vire |
| IP fixo / DDNS | não precisa | precisa |
| VPN no celular | **não** | não |

Encaminhamento de porta está **descartado**. O ganho é zero e o risco é a rede inteira.

### Regras que valem nos dois modos

- **A API key do slskd nunca sai do servidor.** O navegador fala com o nosso serviço; o
  serviço fala com o motor. Se a chave chegasse ao celular, qualquer aba do navegador teria
  controle total do Soulseek.
- **Senha guardada com hash forte** (Argon2id ou bcrypt). Nunca em texto, nunca em base64.
- **Sessão por token**, cookie `HttpOnly` + `SameSite=Strict` + `Secure`.
- **Limite de tentativas de login**, com espera crescente. Sem isso, senha de painel caseiro
  cai em minutos.
- **Token anti-CSRF** em tudo que muda estado.
- **O painel não recebe caminho de arquivo.** Espectrograma e música são servidos por **id
  interno**, resolvido para o caminho do lado do servidor. É o que fecha a porta para
  travessia de diretório (`../../`) — o buraco clássico de painel caseiro que serve arquivo.
- **Nada de comando de sistema pelo navegador.** O celular manda link de playlist e lê
  resultado. Escolher pasta, abrir arquivo, rodar processo: só na janela do PC.

## 💻 Windows agora, macOS depois — sem virar reescrita

Windows é a versão testada. macOS entra quando houver máquina para testar. Para que isso seja
um **porte** e não uma reescrita, três regras valem desde a primeira linha:

- **Nunca caminho escrito na mão.** Só `pathlib`; nada de `C:\` nem de `\` montado à unha.
- **Pastas do sistema resolvidas por função**, não por constante — a pasta de dados do app é
  `%LOCALAPPDATA%` no Windows e `~/Library/Application Support` no macOS.
- **O que é de sistema fica isolado** num módulo só. Hoje isso é: a automação de tela do
  SoulseekQt, o caminho do ffmpeg e o registro do instalador.

O instalador pergunta o sistema e entrega o pacote certo. A automação do SoulseekQt **não
atravessa** para o macOS — lá o motor é o slskd, e o app precisa dizer isso em vez de
oferecer um botão que não funciona.

## 🗂️ Como os arquivos se organizam

```
src/
  nucleo/        playlist, normalizador, qualidade, espectro, fila
  motores/       protocolo + motor_slskd + motor_soulseekqt
  interface/     janela PySide
  web/           serviço local + painel do celular
  sistema/       o que muda entre Windows e macOS (isolado de propósito)
tests/
```

`normalizador.py` está em `src/` na raiz por enquanto; muda para `src/nucleo/` quando o
segundo módulo do núcleo chegar — antes disso, pasta com um arquivo só é cerimônia à toa.
