# Contrato do serviço `rafira-ia`

Este documento é o registro **versionado e autossuficiente** do contrato HTTP
do `rafira-ia`. Não pressupõe acesso a nenhum outro documento: o arquivo que
antes era autoritativo para esse contrato,
`docs/plans/roadmap-ia/preparacao-para-o-retorno.md` no repositório
`rafira-web`, **não existe em nenhum ref daquele repositório** — foi citado
pelo código antigo, mas se perdeu. A spec de design deste trabalho também não
é versionada (o gitignore global do time ignora `docs/superpowers`). Este
arquivo é, portanto, a única fonte da verdade deste contrato que sobrevive em
qualquer `git log`. Quem implementar um novo caller deve conseguir trabalhar
só a partir daqui.

O `rafira-ia` é o serviço de IA da Rafira: transcreve gravações de consulta e
sintetiza dois tipos de resumo clínico. Ele nunca fala com um paciente ou
profissional diretamente — quem chama é sempre o backend Rails do
`rafira-web` (hoje via `Transcription::Client` para `/transcriptions` e
`Ai::BriefingClient` para `/briefings`, ambos reutilizando o mesmo par
`TRANSCRIPTION_API_URL`/`TRANSCRIPTION_API_TOKEN`).

## Fatos que valem para o serviço inteiro

- **Porta 4000**, fixa — definida no `CMD` da imagem
  (`uvicorn app.main:app --host 0.0.0.0 --port 4000`) e não configurável por
  variável de ambiente hoje. Não confundir com a porta 8000 de uma versão
  anterior deste mesmo serviço.
- **Todo corpo de erro, em qualquer endpoint, tem a forma
  `{"error": "<mensagem>"}`** — nunca o `{"detail": ...}` padrão do FastAPI.
  Handlers globais em `app/main.py` garantem isso tanto para `HTTPException`
  quanto para erro de validação (do FastAPI e do Pydantic). O client Ruby
  coloca esse corpo verbatim na tela que o profissional lê, então a forma
  importa tanto quanto o conteúdo.
- **`TRANSCRIPTION_MODE`** (`stub` por default, ou `real`) governa os
  **três** endpoints de trabalho (`/transcriptions`, `/briefings`,
  `/summaries`) — ver a nota dedicada mais abaixo.
- Em modo `stub`, **nenhuma chave de vendor é exigida** — é o modo que dev e
  CI usam, determinístico e sem nenhuma chamada de rede.
- Em modo `real`, a ausência de uma chave de vendor derruba o processo **no
  boot**, com uma mensagem nomeando a variável ausente — nunca falha
  silenciosamente na primeira requisição.
- O serviço nunca recebe bytes de áudio. `audio_url` é sempre uma URL
  presigned de GET; quem baixa e decodifica o áudio é a AssemblyAI, a partir
  dessa URL. Os bytes não passam pelo Rails nem por este serviço.

## Autenticação

Controlada por uma única variável, `TRANSCRIPTION_API_TOKEN`:

- **Não definida (default):** todos os endpoints ficam abertos, sem
  autenticação. É o que dev e CI usam.
- **Definida:** todo endpoint **exceto `GET /health`, `GET /docs`,
  `GET /redoc` e `GET /openapi.json`** passa a exigir o cabeçalho
  `Authorization: Bearer <token>` com o valor exato configurado. Ausência do
  cabeçalho, esquema diferente de `Bearer` (case-insensitive) ou valor
  incorreto resultam em `401` com
  `{"error": "invalid or missing bearer token"}`.
- `/health` nunca exige o token, propositalmente — é o endpoint que o
  healthcheck do `docker compose` e o do ECS chamam, e nenhum dos dois carrega
  credencial.
- **`/docs`, `/redoc` e `/openapi.json` também nunca exigem o token, mas não
  por escolha deliberada da mesma forma que `/health`.** `require_token` é
  uma dependency de nível de router, aplicada só aos três routers de
  trabalho (`/transcriptions`, `/briefings`, `/summaries`); as rotas de
  documentação são registradas pelo próprio FastAPI, fora de qualquer router
  deste projeto, e por isso ficam fora do alcance dessa dependency mesmo com
  o token configurado. O que fica exposto é só *schema* — nomes e tipos de
  campo, nunca dado de paciente —, mas quem precisar fechar completamente
  essa superfície deve desabilitar essas três rotas no ambiente afetado
  (`docs_url`, `redoc_url` e `openapi_url` de `FastAPI(...)` em
  `app/main.py`, hoje todos no default).
- O `Transcription::Client` do `rafira-web` já envia esse cabeçalho sempre
  que a variável equivalente está definida do lado dele — ativar autenticação
  é uma mudança de configuração nos dois lados, nunca uma mudança de código.

## Endpoints

| Método | Path             | Status possíveis                                  |
|--------|------------------|----------------------------------------------------|
| GET    | `/health`        | `200`                                              |
| POST   | `/transcriptions`| `200`, `401`\*, `422`, `500`, `502`                |
| POST   | `/briefings`     | `200`, `401`\*, `422`, `500`, `502`                |
| POST   | `/summaries`     | `200`, `401`\*, `422`, `500`, `502`                |
| POST   | `/agent/runs`    | `200`, `401`, `422`, `500`, `502`, `503`           |

O novo harness clínico tem contrato próprio em [agent-contract.md](agent-contract.md).
Ele compartilha o modo e o token existentes, mas exige token configurado em modo real.
As descrições dos três endpoints legados abaixo permanecem válidas para eles.

\* `401` só é possível quando `TRANSCRIPTION_API_TOKEN` está configurado.

Os três endpoints de trabalho podem responder `500` ou `502`; `/health`
nunca retorna nenhum dos dois — não depende de vendor nem de arquivo de
prompt, só relata que o processo está de pé. A distinção entre os dois:

- **`502`** significa que a chamada ao vendor (AssemblyAI ou OpenAI) falhou
  de forma definitiva. O corpo carrega só o motivo relatado pelo próprio
  vendor — nunca o texto completo da exceção interna nem um traceback.
- **`500`** cobre dois casos: um arquivo de prompt ausente no disco da
  imagem (só possível em modo `real`, só em `/briefings` e `/summaries` —
  ver a nota de cada endpoint), com o caminho do arquivo no corpo; ou
  qualquer outra exceção não prevista, com uma mensagem fixa e genérica no
  corpo — o texto real dessa exceção nunca sai do processo, só vai para o
  log do servidor.

O client Ruby trata qualquer resposta que não seja 2xx como **definitiva**:
não repete a chamada (só falhas de transporte, como timeout de conexão, são
repetidas, pelo `retry_on` do job). Isso vale para os três endpoints de
trabalho.

### `GET /health`

Sem autenticação, sem parâmetros. Responde sempre `200`:

```json
{ "status": "ok", "mode": "stub" }
```

`mode` reflete `TRANSCRIPTION_MODE` (`"stub"` ou `"real"`). Este endpoint
responde `ok` mesmo em modo `real` — significa que o processo está de pé, não
que cada endpoint individual esteja necessariamente saudável. Na prática,
porém, se o processo chegou a responder a `/health` em modo `real`, as
chaves de vendor já foram validadas no boot (ver acima), então o cenário de
"health ok mas vendor mal configurado" não existe para chave ausente — só
para chave presente mas inválida/expirada, que só se manifesta no próprio
endpoint que a usa.

### `POST /transcriptions`

Transcreve o áudio de uma URL presigned.

**Request:**

| Campo          | Tipo   | Obrigatório | Descrição                                            |
|----------------|--------|-------------|-------------------------------------------------------|
| `audio_url`    | string | sim         | URL presigned de GET para o áudio.                    |
| `content_type` | string | não         | MIME type reportado pelo gravador do navegador.       |

Ausência de `audio_url` responde `422`.

```json
{
  "audio_url": "https://rafira-clinical-audio.s3.amazonaws.com/sessions/9f2c1e/recording.webm?X-Amz-Signature=...",
  "content_type": "audio/webm"
}
```

**`content_type` é aceito e ignorado hoje, nas duas implementações.** Nem o
stub nem o modo `real` (AssemblyAI, que detecta o formato a partir dos
próprios bytes do áudio) usam esse valor para qualquer coisa. Aceitar e não
usar não é erro de validação — mas quem espera esse campo influenciar a
resposta vai confundir "o payload chegou e não fez efeito" com "o payload
nunca chegou".

**Response `200`:**

| Campo         | Tipo             | Descrição                                                        |
|---------------|------------------|--------------------------------------------------------------------|
| `text`        | string           | Transcrição completa, concatenando todos os segmentos.            |
| `language`    | string           | Sempre `"pt-BR"` hoje.                                             |
| `duration_sec`| int              | Duração do áudio em segundos.                                     |
| `provider`    | string           | `"stub"` ou `"assemblyai"`, conforme o modo.                       |
| `external_id` | string           | Id da transcrição no provider (ou um UUID gerado, no stub).        |
| `segments`    | array de Segment | Um item por trecho diarizado. Pode ser vazio.                     |

Cada `Segment`: `{ start: float, end: float, speaker: string|null, text: string }`.

```json
{
  "text": "Bom dia. Como você está se sentindo essa semana? Tenho notado uma melhora no sono, mas ainda sinto ansiedade antes das consultas.",
  "language": "pt-BR",
  "duration_sec": 612,
  "provider": "assemblyai",
  "external_id": "7c9c9f1e-2f3b-4a11-9c2e-1a2b3c4d5e6f",
  "segments": [
    { "start": 0.0, "end": 4.5, "speaker": "Falante A", "text": "Bom dia. Como você está se sentindo essa semana?" },
    { "start": 4.5, "end": 12.0, "speaker": "Falante B", "text": "Tenho notado uma melhora no sono, mas ainda sinto ansiedade antes das consultas." }
  ]
}
```

**`speaker` é sempre o rótulo cru do vendor (ex.: `"Falante A"`), nunca um
papel clínico.** Ninguém mapeia "Falante A" para "profissional" ou
"paciente" — esse mapeamento seria um chute, e uma atribuição de fala errada
num registro clínico é pior do que um rótulo genérico. `speaker` é `null`
quando o provider não diariza. No modo `stub`, os dois segmentos fixos da
fixture usam `"profissional"` e `"paciente"` como valor de `speaker` — são
rótulos de conveniência da fixture de desenvolvimento, não uma amostra do
formato real; **não construir integração assumindo que `speaker` em produção
se parece com essas duas strings.**

### `POST /briefings`

Sintetiza um briefing de retorno a partir de um dossiê estruturado. Trabalho
distinto de `/summaries`: este endpoint sintetiza **vários encontros** de um
dossiê; `/summaries` resume **uma** transcrição de consulta isolada.

**Request — o dossiê.** Todo campo é opcional; um objeto vazio é um dossiê
válido (primeira consulta do paciente). O dossiê **não carrega nome, CPF,
telefone nem endereço** do paciente — idade no lugar de data de nascimento.

| Campo                  | Tipo                | Descrição |
|-------------------------|--------------------|-----------|
| `kind`                  | string ou null     | Ex.: `"return_briefing"`. Não afeta a resposta hoje. |
| `locale`                 | string ou null     | Não afeta a resposta hoje. |
| `patient`                | object ou null     | `age`, `sex`, `allergy_status`, `allergies`, `background`. |
| `medications`            | object ou null     | Não afeta a resposta hoje. |
| `encounters`             | array de Encounter | Ver o invariante de ordenação abaixo. `null` é tratado como `[]`. |
| `documents`              | array de Document  | `null` é tratado como `[]`. |
| `upcoming_appointment`   | object ou null     | Não afeta a resposta hoje. |

`Encounter`: `{ id, recorded_at, service, cid: {code, description}, sections[], addenda[], attachments[] }`.
`Document`: `{ kind, issued_at, encounter_id, content }`.

`id` (de `Encounter`) e `encounter_id` (de `Document`) aceitam tanto string
quanto número — o Rails pode serializar como inteiro; o serviço normaliza
para string internamente, mas a citação em `source_encounter_ids` na
resposta é sempre string.

**Exemplo completo de dossiê:**

```json
{
  "kind": "return_briefing",
  "locale": "pt-BR",
  "patient": {
    "age": 47,
    "sex": "F",
    "allergy_status": "unknown",
    "allergies": null,
    "background": { "comorbidities_reported": false }
  },
  "medications": { "in_use": ["losartana 50mg"] },
  "encounters": [
    {
      "id": "780",
      "recorded_at": "2026-01-10T09:00:00",
      "service": "Primeira consulta",
      "cid": null,
      "sections": [{ "title": "Queixa principal", "text": "Dor torácica leve ao esforço." }],
      "addenda": [],
      "attachments": []
    },
    {
      "id": "812",
      "recorded_at": "2026-05-14T09:00:00",
      "service": "Consulta de retorno",
      "cid": { "code": "I21.9", "description": "Infarto agudo do miocárdio" },
      "sections": [],
      "addenda": [],
      "attachments": []
    },
    {
      "id": "845",
      "recorded_at": "2026-08-20T09:00:00",
      "service": "Consulta de retorno",
      "cid": null,
      "sections": [],
      "addenda": [{ "text": "Paciente relata melhora do quadro." }],
      "attachments": ["laudo_ecg_845.pdf"]
    }
  ],
  "documents": [
    {
      "kind": "pedido_exames",
      "issued_at": "2026-08-20T09:10:00",
      "encounter_id": "845",
      "content": { "exams": ["ecocardiograma de controle"] }
    }
  ],
  "upcoming_appointment": { "date": "2026-09-20", "service": "Consulta de retorno" }
}
```

**Response `200`:**

| Campo         | Tipo                    | Descrição |
|---------------|-------------------------|-----------|
| `summary`     | string                  | Nunca vazio; ver regra 4 abaixo para o caso sem histórico. |
| `since_last`  | object ou `null`        | `null` só quando `encounters` está vazio. Ver campos abaixo. |
| `evolution`   | array de EvolutionEntry | Uma entrada por tema/encontro. Pode ser vazio. |
| `watch_points`| array de WatchPoint     | Pode ser vazio. |
| `model`       | string                  | `"stub"` ou o nome do modelo OpenAI usado. |
| `generated_at`| string (ISO 8601, UTC)  | Momento em que a resposta foi gerada. |

`since_last`: `{ encounter_id: string, days_ago: int, items: [Claim] }`.
**`days_ago` é sempre um inteiro, nunca `null`** — se `recorded_at` do
encontro mais recente estiver ausente ou for ilegível, cai para `0` em vez de
degradar o tipo. Um client que espera `int` nunca precisa tratar `null`
nesse campo.

`Claim` (usado em `since_last.items`) e `EvolutionEntry` (usado em
`evolution`) trazem `source_encounter_ids: [string]`, nunca vazio numa
entrada que sobreviveu à validação — ver Regra 2 abaixo.

```json
{
  "summary": "3 encontro(s) considerado(s) no período observado, o mais recente em 2026-08-20T09:00:00.",
  "since_last": {
    "encounter_id": "845",
    "days_ago": 17,
    "items": [
      {
        "text": "Documento \"pedido_exames\" registrado no último encontro.",
        "kind": "note",
        "source_encounter_ids": ["845"],
        "confidence": "high"
      }
    ]
  },
  "evolution": [
    {
      "topic": "Infarto agudo do miocárdio",
      "text": "Acompanhamento de infarto agudo do miocárdio (CID I21.9) desde 2026-05-14, com melhora relatada em 2026-08-20.",
      "source_encounter_ids": ["780", "812", "845"],
      "confidence": "medium"
    }
  ],
  "watch_points": [
    {
      "text": "Status de alergias não informado no dossiê.",
      "reason": "missing_data",
      "confidence": "high"
    }
  ],
  "model": "gpt-4o-mini",
  "generated_at": "2026-09-06T13:02:11Z"
}
```

**Este exemplo de resposta ilustra o modo `real`**, deliberadamente: a
entrada de `evolution` acima cita três encontros (`780`, `812`, `845`) num
único tema, acompanhando sua evolução ao longo do tempo. **O modo `stub`
nunca produz uma entrada assim** — ver "Limitações do stub" abaixo.

#### Invariante obrigatório: ordem de `encounters` (regra para quem implementa o caller)

**`encounters` deve chegar em ordem cronológica, do mais antigo para o mais
recente, e conter apenas encontros do profissional que está solicitando o
briefing.** O backend que monta o dossiê é responsável por aplicar esse
escopo e essa ordenação **antes** de chamar este serviço — o `rafira-ia` não
reordena nem filtra por profissional; ele confia inteiramente no que
recebe.

Isso não é um detalhe cosmético: tanto o stub quanto o modo real determinam
"o encontro mais recente" tomando literalmente o **último elemento** da
lista (`encounters[-1]`) — é esse encontro que vira `since_last.encounter_id`
e cuja data alimenta `since_last.days_ago`. **Se um caller algum dia enviar
`encounters` fora de ordem, `since_last` vai citar silenciosamente o
encontro errado** — não há validação de data que detecte isso, porque o
serviço nunca ordena a lista por conta própria. Qualquer implementação nova
de caller precisa garantir essa ordenação antes de serializar o dossiê.

#### Por que `422` (body não é objeto JSON) e `200` (dossiê vazio) são mantidos separados

Um body que **não é um objeto JSON** — um array, uma string, um número,
`null`, ou JSON que nem chega a fazer parse — responde sempre `422` com:

```json
{ "error": "request body must be a JSON object" }
```

Isso é **deliberadamente diferente** de um dossiê vazio mas válido — `{}` ou
`{"encounters": []}`, ambos `200` com um briefing vazio (regra 4, abaixo).
Um campo aninhado que falha a validação do próprio modelo (ex.:
`{"patient": {"age": "não é número"}}`) também responde `422`, com uma
mensagem diferente, mas pelo mesmo princípio: o body chegou a ser um objeto
JSON, só um campo dele é inválido.

A razão de manter as duas coisas separadas: **confundir "corpo malformado"
com "dossiê legitimamente vazio" deixaria um bug de serialização do lado do
caller se esconder atrás de um briefing vazio plausível.** Um `200` com
listas vazias parece, para quem só olha a tela final, exatamente um paciente
sem histórico relevante — um resultado clínico legítimo. Se um bug no lado
Rails serializasse o dossiê como `null` ou como uma string por engano, esse
erro de integração precisa aparecer como um `422` alto e visível, nunca se
disfarçar de "paciente sem histórico". O profissional não tem como
distinguir os dois casos olhando só a resposta final; o contrato distingue
por eles.

### `POST /summaries`

Resume **uma** transcrição de consulta, para leitura por médico ou por
paciente. Sem consumidor no `rafira-web` até a data deste documento — parte
fixa do contrato mesmo assim.

**Request:**

| Campo               | Tipo   | Obrigatório | Descrição |
|---------------------|--------|-------------|-----------|
| `consultation_text` | string | sim (não pode ser vazia) | Transcrição completa da consulta. |
| `summary_type`      | `"doctor"` \| `"patient"` | sim | Público-alvo do resumo. |
| `custom_prompt`     | string | não | Substitui o prompt padrão do tipo. |

```json
{
  "consultation_text": "Paciente relata melhora do sono. Mantida a medicação atual.",
  "summary_type": "doctor",
  "custom_prompt": null
}
```

**Response `200`:**

```json
{
  "summary_type": "doctor",
  "summary": "Resumo técnico (stub): consulta registrada, sem intercorrências relatadas."
}
```

**Erros:** `422` se `consultation_text` estiver ausente/vazio ou
`summary_type` não for `"doctor"`/`"patient"`; `500` se `custom_prompt` não
for enviado e o arquivo de prompt padrão do tipo pedido
(`prompts/default_doctor.txt` ou `prompts/default_patient.txt`) não existir
no disco da imagem; `502` se a chamada à OpenAI falhar ou devolver conteúdo
vazio.

**`custom_prompt` é aceito e ignorado pelo stub** — a resposta do stub é
sempre a mesma string fixa por `summary_type` (ver
`app/services/summarization/stub.py`), então enviar `custom_prompt` contra
o stub não muda nada na resposta. Em modo `real` ele funciona normalmente:
substitui o prompt padrão do tipo pedido, e o arquivo padrão nem chega a
ser lido (ver a nota de `POST /transcriptions` acima para a mesma confusão
de "aceito mas sem efeito", em outro campo).

## Latência e timeouts

Nenhuma seção anterior diz quanto tempo um caller deve esperar por
resposta — e essa única informação decide se uma nova implementação de
caller deve chamar o serviço de dentro do ciclo de um request, ou de um
job em background. Em modo `stub` os três endpoints de trabalho respondem
em `TRANSCRIPTION_STUB_DELAY_SEC` / `BRIEFING_STUB_DELAY_SEC` (ou
instantaneamente, para `/summaries`, que não tem atraso simulado
configurável) — nunca na ordem de grandeza da tabela abaixo, que descreve
só o modo `real`:

| Endpoint               | Latência esperada em modo `real`                                                                                          | Timeout usado hoje pelo caller Rails |
|--------------------------|------------------------------------------------------------------------------------------------------------------------------|----------------------------------------|
| `POST /transcriptions`  | A conexão fica aberta pelo tempo inteiro do job da AssemblyAI — segundos a **minutos**, proporcional à duração do áudio. Uma consulta de 40 minutos é um caso real, não um extremo hipotético. | `Transcription::Client::READ_TIMEOUT` = 2400s (40 min). |
| `POST /briefings`       | Tipicamente segundos — uma síntese sobre um dossiê já montado, não uma transcrição longa.                                    | `Ai::BriefingClient::READ_TIMEOUT` = 90s. |
| `POST /summaries`       | Tipicamente segundos — uma única chamada de completion sobre uma transcrição já pronta, mesma ordem de grandeza de `/briefings`. | Nenhum ainda — sem consumidor no `rafira-web` até a data deste documento (ver a seção do endpoint acima). 90s é o ponto de partida razoável, pela mesma razão de `/briefings`: mesmo backend, uma única chamada de completion. |

Esses números vivem do lado Rails (`rafira-web`), não neste repositório;
listados aqui porque este documento se propõe a ser autossuficiente para
quem for escrever um novo caller.

## As quatro regras clínicas

Valem para qualquer implementação — stub ou real — de `/briefings`.

1. **Ausência nunca é negação.** Um dossiê que não menciona um dado não
   autoriza afirmar que ele não existe. `allergy_status: "unknown"` significa
   *ninguém perguntou*, não *não há alergia* — isso vai para `watch_points`
   com `reason: "missing_data"`, nunca vira silêncio nem uma frase como
   "paciente nega alergias".
2. **Toda afirmação cita a fonte.** `source_encounter_ids` é obrigatório em
   toda entrada de `evolution` e em todo item de `since_last.items`, e só
   pode referenciar ids de encontros **presentes no request**. Uma afirmação
   sem fonte rastreável é descartada antes de chegar ao profissional.
3. **Sem diagnóstico nem conduta.** A resposta descreve o que está
   registrado — nome do serviço, CID exatamente como arquivado, tipo de
   documento. Nunca propõe hipótese diagnóstica, nunca sugere exame, nunca
   opina sobre tratamento.
4. **Vazio é válido.** Uma primeira consulta, ou nada de relevante desde a
   última, recebe um resumo curto e honesto e listas vazias. Inventar
   conteúdo para não deixar a tela vazia é o pior resultado possível.

### Como a regra 2 é aplicada em modo `real`

Um LLM inventa um id plausível com naturalidade — a regra só é real se for
verificada no servidor, não apenas pedida no prompt:

- A resposta do modelo passa por validação **antes de sair**: cada id em
  `source_encounter_ids` precisa pertencer ao conjunto de `encounters[].id`
  do request recebido.
- Uma entrada que cite qualquer id fora desse conjunto é **descartada por
  inteiro** e registrada em log — nunca corrigida, nunca devolvida parcial
  (citar um id real e um forjado na mesma entrada descarta a entrada
  inteira).
- Se o descarte esvaziar `evolution` ou `since_last.items`, a resposta segue
  assim mesmo: honestamente vazio é um resultado aceitável (regra 4).
- A regra 4 também evita gasto: um dossiê sem `encounters` **nunca chega a
  chamar a OpenAI** — a resposta vazia é construída diretamente, do mesmo
  jeito que o stub já faz.

## Limitações do stub de `/briefings`

O stub constrói cada campo da resposta a partir do próprio request — não é
um bloco de prosa fixo. Duas limitações valem para quem depurar contra ele:

1. **Sem síntese entre encontros.** `evolution` no modo stub é estritamente
   **uma entrada por encontro**, citando somente o próprio id daquele
   encontro — mesmo o exemplo de resposta mais acima mostrando uma entrada
   que cita três ids acompanhando um tema ao longo do tempo. Essa síntese
   entre vários encontros é uma capacidade exclusiva do modo `real`; a
   granularidade 1:1 do stub é uma simplificação conservadora e correta,
   **não** o formato contra o qual construir uma UI.
2. **Campos aceitos e ignorados.** Os onze campos abaixo são aceitos no
   dossiê (nenhum gera erro de validação) mas **não afetam a resposta do
   stub de forma alguma**: `medications`, `patient.background`,
   `patient.sex`, `patient.age`, `encounters[].sections`,
   `encounters[].addenda`, `encounters[].attachments`, `documents[].content`,
   `documents[].issued_at`, `locale`, `upcoming_appointment`. Dois dossiês
   que diferem só num desses campos produzem resposta idêntica no stub —
   saber disso evita confundir "o payload chegou e não fez efeito" com "o
   payload nunca chegou".

Duas notas menores, também verificadas no código do stub
(`app/services/briefing/stub.py`):

- `since_last.items[].kind` é sempre `"note"` no stub, nunca um estado de
  fluxo como `"pending"` — o stub não tem como saber o estado real de um
  documento a partir só do dossiê, e prefere não superestimar.
- `patient.allergies` (distinto de `patient.allergy_status`) também não
  influencia a resposta do stub hoje, pelo mesmo motivo dos onze campos
  acima.

Nenhuma das duas limitações acima é um bug: o modo `real`, com um LLM atrás,
pode fazer melhor em ambos os pontos. O stub deliberadamente não tenta.

## Variáveis de ambiente

| Variável                       | Default        | Obrigatória           | Papel |
|---------------------------------|----------------|------------------------|-------|
| `TRANSCRIPTION_MODE`            | `stub`         | não                    | Governa os três endpoints de trabalho — ver nota abaixo. |
| `TRANSCRIPTION_STUB_DELAY_SEC`  | `2`            | não                    | Atraso simulado (segundos) do stub de `/transcriptions`. |
| `BRIEFING_STUB_DELAY_SEC`       | `1`            | não                    | Atraso simulado (segundos) do stub de `/briefings`. |
| `TRANSCRIPTION_API_TOKEN`       | vazio          | não                    | Se definida, exige `Authorization: Bearer` nos três endpoints de trabalho (não em `/health` nem nas rotas de documentação do FastAPI — ver seção Autenticação). |
| `ASSEMBLYAI_API_KEY`            | vazio          | **sim, só em `real`**  | Chave da AssemblyAI. Ausência em modo `real` derruba o processo no boot. |
| `OPENAI_API_KEY`                | vazio          | **sim, só em `real`**  | Chave da OpenAI. Ausência em modo `real` derruba o processo no boot. |
| `OPENAI_MODEL`                  | `gpt-4o-mini`  | não                    | Modelo usado tanto por `/briefings` quanto por `/summaries` em modo `real`. |
| `PROMPTS_DIR`                   | `prompts`      | não                    | Diretório onde `briefing_system.txt`, `default_doctor.txt` e `default_patient.txt` são lidos em modo `real`. Variável viva e efetiva hoje (não só um valor hardcoded) — quem apontar para um diretório sem os três arquivos vê `500` de `PromptNotFoundError` nos endpoints que precisarem do arquivo ausente. |

Em modo `stub`, `ASSEMBLYAI_API_KEY` e `OPENAI_API_KEY` podem ficar
totalmente ausentes — é exatamente disso que dev e CI dependem.

### Por que `TRANSCRIPTION_MODE` continua se chamando assim

Uma única variável, `TRANSCRIPTION_MODE`, decide `stub` ou `real` para os
**três** endpoints (`/transcriptions`, `/briefings` e `/summaries`) — é uma
decisão de "este processo pode alcançar backend de vendor de verdade?", não
uma variável por trabalho. O nome é impreciso para um serviço que hoje faz
três coisas, e permanece assim mesmo sabendo disso: é o nome que o
`docker-compose.yml` do `rafira-web` já define e envia para este serviço, e
renomear essa variável custaria alterações em coordenação entre os dois
repositórios por um ganho puramente cosmético.

A seleção acontece uma única vez, em `app/dependencies.py`, no momento em
que cada provider de serviço é resolvido — nunca como um `if` espalhado
dentro dos handlers das rotas.
