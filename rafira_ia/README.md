# RAFIRA AI

Serviço de IA da Rafira: transcrição de gravações de consulta (via
AssemblyAI) e síntese de dois tipos de resumo clínico — briefing de retorno
a partir de um dossiê estruturado, e resumo de uma única consulta para
médico ou paciente (via OpenAI). Construído com FastAPI, conteinerizado com
Docker.

Este é o backend de IA que o `rafira-web` (aplicação Rails) consome pela
rede — nunca uma biblioteca importada, nunca um processo que lê arquivo
local. **O contrato HTTP completo — endpoints, exemplos de request/response,
as quatro regras clínicas e as variáveis de ambiente — está em
[`docs/contract.md`](docs/contract.md). Este README cobre só como rodar o
serviço; o contrato é o documento autoritativo.**

## Modo `stub` vs modo `real`

Uma única variável, `TRANSCRIPTION_MODE`, escolhe a implementação dos três
endpoints de trabalho:

- **`stub`** (default) — determinístico, sem nenhuma chamada de rede e sem
  exigir **nenhuma** chave de vendor. É o modo que desenvolvimento e CI usam.
- **`real`** — chama AssemblyAI (transcrição) e OpenAI (briefing e resumo).
  Exige `ASSEMBLYAI_API_KEY` e `OPENAI_API_KEY`; a ausência de qualquer uma
  derruba o processo no boot, com uma mensagem nomeando a variável que falta.

Detalhes de cada endpoint, os exemplos completos de request/response e a
tabela de variáveis de ambiente estão em [`docs/contract.md`](docs/contract.md).

## Rodando em modo stub, sem chave nenhuma

### Com Docker

```bash
cp .env.example .env   # opcional em modo stub — os defaults já bastam
docker compose up --build
```

A API sobe em `http://localhost:4000`. Confirme com:

```bash
curl -fsS http://localhost:4000/health
# {"status":"ok","mode":"stub"}
```

### Sem Docker

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

uvicorn app.main:app --reload --port 4000
```

Nenhuma variável de ambiente é necessária para o modo `stub` — é o default
de `TRANSCRIPTION_MODE`.

## Rodando em modo real

Preencha `ASSEMBLYAI_API_KEY`, `OPENAI_API_KEY` e `TRANSCRIPTION_MODE=real`
no `.env` (copiado de `.env.example`) e suba normalmente. Ver
[`docs/contract.md`](docs/contract.md#variáveis-de-ambiente) para a lista
completa de variáveis.

## Harness clínico

O endpoint adicional `POST /agent/runs` executa resumos com fontes e respostas a dúvidas
clínicas com abstenção quando não há evidência. Veja [o contrato](docs/agent-contract.md).
O backend Rails persiste as execuções e exige revisão médica; o serviço de IA não aprova
documentos. Os endpoints anteriores continuam disponíveis.

## Documentação interativa (Swagger)

Com a aplicação em execução:

- Swagger UI: `http://localhost:4000/docs`
- ReDoc: `http://localhost:4000/redoc`
- OpenAPI JSON: `http://localhost:4000/openapi.json`

Essa documentação descreve o *schema* dos endpoints; para o contrato
completo (exemplos, regras clínicas, variáveis de ambiente), use
[`docs/contract.md`](docs/contract.md).

## Rodando os testes

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt

pytest
```

A suíte inteira roda em modo `stub`: nunca toca AssemblyAI nem OpenAI de
verdade (os testes que exercitam o caminho `real` mockam o SDK do vendor).

**Importante:** `requirements.txt` fixa versões específicas, verificadas
contra os wheels reais do PyPI — não os últimos lançamentos. A máquina de um
desenvolvedor frequentemente já tem versões bem diferentes instaladas
globalmente (de outro projeto, por exemplo), e o código pode se comportar de
forma diferente contra elas. Um venv criado a partir de `requirements.txt`
(ou `requirements-dev.txt`, que o inclui) é a única forma de rodar
localmente o que o CI e a imagem Docker efetivamente rodam.

## Estrutura do projeto

```
rafira-ia/
├── app/
│   ├── main.py                          # instancia o FastAPI, inclui os routers,
│   │                                     #   registra os handlers de erro {"error": ...},
│   │                                     #   expõe /health
│   ├── config.py                        # Settings via variáveis de ambiente
│   │                                     #   (pydantic-settings); valida modo `real` no boot
│   ├── dependencies.py                  # DI: escolhe stub|real por TRANSCRIPTION_MODE
│   ├── core/
│   │   ├── exceptions.py                # exceções de domínio
│   │   └── security.py                  # dependency de Bearer opcional
│   ├── models/
│   │   ├── transcription.py             # schemas de POST /transcriptions
│   │   ├── briefing.py                  # dossiê e resposta de POST /briefings
│   │   └── summarization.py             # schemas de POST /summaries
│   ├── routers/
│   │   ├── transcription.py             # POST /transcriptions
│   │   ├── briefing.py                  # POST /briefings
│   │   └── summarization.py             # POST /summaries
│   └── services/
│       ├── transcription/{base,stub,assemblyai}.py
│       ├── briefing/{base,stub,openai,validation}.py
│       └── summarization/{base,stub,openai}.py
├── prompts/
│   ├── briefing_system.txt              # prompt de sistema do briefing real
│   ├── default_doctor.txt               # prompt padrão do resumo "doctor"
│   └── default_patient.txt              # prompt padrão do resumo "patient"
├── docs/
│   └── contract.md                      # o contrato HTTP completo — fonte da verdade
├── tests/
├── requirements.txt
├── requirements-dev.txt
├── Dockerfile
├── docker-compose.yml
├── .env.example
└── .dockerignore
```

## Como o `rafira-web` consome este serviço

O backend Rails do `rafira-web` nunca fala com AssemblyAI ou OpenAI
diretamente — ele fala com este serviço, na porta 4000, através de
`ENV['TRANSCRIPTION_API_URL']`. Dois clientes Ruby, dois endpoints, mesmo
par de variáveis:

- `Transcription::Client` → `POST /transcriptions`
- `Ai::BriefingClient` → `POST /briefings`

Ambos enviam `Authorization: Bearer <TRANSCRIPTION_API_TOKEN>` quando essa
variável está definida do lado do Rails, e tratam qualquer resposta que não
seja 2xx como definitiva (nunca repetem a chamada por causa do conteúdo da
resposta — só uma falha de transporte, como timeout de conexão, é
repetida). O formato exato de cada request e response está em
[`docs/contract.md`](docs/contract.md).
