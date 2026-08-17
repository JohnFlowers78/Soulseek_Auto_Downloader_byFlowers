# Instruções do projeto — Soulseek Auto Downloader

## Como rodar

Sempre pelo venv do projeto e com o encoding forçado — sem isso o Windows quebra a saída
com acento e inventa falha que não existe:

```bash
$env:PYTHONIOENCODING='utf-8'; .\.venv\Scripts\python.exe -m pytest tests/ -v
```

Demonstração do normalizador:

```bash
$env:PYTHONIOENCODING='utf-8'; .\.venv\Scripts\python.exe src/normalizador.py "Djavan" "Não Vou Ficar"
```

## Regras de trabalho

- **Teste nunca escreve em dado real.** Nada de tocar em `data/`, na pasta de downloads
  do slskd ou na pasta de destino das músicas. Tudo isolado em pasta temporária.
- **Cada rodada de recursos termina com um checklist "Para Testar"** — um cenário concreto
  por recurso, para conferir na mão.
- **`IDEIAS.md` é documento vivo**: cada rodada alimenta com o que se aprendeu operando.
- **`TODO.md` e `FUNCIONALIDADES.md` andam junto com o código** — riscar o que ficou pronto
  na mesma leva em que o código entra.
- **Sem pagar API de IA.** A análise de qualidade sai do próprio áudio (ffmpeg), não de OCR
  nem de modelo pago.
- **Segredo não entra no repositório.** Credenciais do Spotify e a API key do slskd vivem
  em `config.json`, que está no `.gitignore`.

## Cuidados específicos desta rede

- **Nenhuma consulta de busca pode conter `-`.** No Soulseek o hífen é operador de exclusão.
  O `normalizador.py` garante isso; qualquer caminho novo que monte consulta precisa passar
  por ele.
- **Limite de 34 buscas / 220 s.** Estourar = banimento de 30 minutos pelo servidor. O
  limitador é obrigatório em qualquer fluxo que busque em lote.
- **O slskd precisa de pasta compartilhada.** Quem só puxa é bloqueado pelos usuários e o
  app para de funcionar.

## Idioma

Código, comentários, documentação e mensagens de commit em **português do Brasil**.
Nomes de função e variável também.
