# Contrato do harness clínico — v1

`POST /agent/runs` complementa os endpoints anteriores sem alterar seus corpos.
É uma interface privada entre Rails e FastAPI. Identidade do paciente, autorização,
consulta ao banco, recuperação de diretrizes, idempotência e aprovação pertencem ao Rails.
O FastAPI executa uma tarefa sem persistência e devolve um resultado que exige revisão.

## Segurança e modo

Usa `TRANSCRIPTION_MODE=stub|real` e `TRANSCRIPTION_API_TOKEN`, como o restante do serviço.
Em modo real, token não configurado resulta em 503. Com token configurado, sua ausência
ou valor incorreto na requisição resulta em 401, inclusive no modo stub. Não exponha o
serviço diretamente à internet. A marca `approved_summary` é uma asserção do backend
autenticado; o FastAPI não tem acesso ao banco para verificar a aprovação do profissional.

## Requisição

```json
{
  "task": "doctor_summary",
  "question": null,
  "sources": [{
    "id": "transcript:42",
    "kind": "transcript",
    "title": "Transcrição 42",
    "text": "Paciente relata melhora do sono.",
    "recorded_at": "2026-10-24T13:00:00-03:00",
    "url": null,
    "version": null
  }]
}
```

- `task`: `doctor_summary`, `patient_summary` ou `clinical_question`.
- `sources`: 1–50 fontes com ids únicos, texto de 1–60.000 caracteres; soma até 150.000.
- `kind`: `transcript`, `history`, `exam_report`, `approved_summary`, `guideline`.
- `question`: obrigatória e não vazia para dúvida clínica, até 4.000 caracteres.
- Versão do paciente: exatamente uma fonte `approved_summary`; outras são rejeitadas.
- Resumos não aceitam `guideline`; dúvidas podem receber as diretrizes recuperadas pelo Rails.
- Campos extras são rejeitados. URLs são metadados, nunca são acessadas pelo modelo/harness.

## Resposta

```json
{
  "claims": [{
    "text": "Paciente relata melhora do sono.",
    "kind": "recorded_fact",
    "citations": [{"source_id": "transcript:42", "quote": "Paciente relata melhora do sono."}]
  }],
  "missing_data": [],
  "limitations": ["Demonstração: trechos literais, sem síntese clínica."],
  "abstained": false,
  "summary": "[recorded_fact] Paciente relata melhora do sono.",
  "model": "stub",
  "generated_at": "2026-10-24T16:00:00Z",
  "harness_version": "1.0.0",
  "requires_review": true,
  "steps": ["context_validated", "task_routed", "draft_generated", "citations_validated", "awaiting_human_review"]
}
```

Até 30 afirmações com até oito citações por afirmação. `kind` pode ser `recorded_fact`,
`hypothesis` ou `suggestion`. Citações devem conter trechos literais não vazios presentes
na fonte indicada. Sugestões só são aceitas para dúvidas, com ao menos uma diretriz citada.
Fatos do paciente não podem se apoiar exclusivamente em diretrizes.

O texto de `summary` é composto das afirmações, sem uma segunda geração livre.
`missing_data` e `limitations` são textos produzidos pelo modelo para revisão, não um
validador clínico determinístico. Verificar citações não comprova correção semântica.

Sem diretriz recebida na dúvida clínica: `abstained=true`, `claims=[]`, `summary=""`,
e etapa `abstained_without_evidence`; nenhuma chamada ao modelo. No modo stub,
dúvidas sempre se abstêm, mesmo com diretrizes. Resumos stub usam trechos literais,
identificados como demonstração.

## Limites de execução e erros

Uma chamada estruturada por execução, sem retries SDK, timeout de 45s, deadline de 55s,
até 3.500 tokens de saída, usando `OPENAI_MODEL`. Não há escrita de prontuário nem emissão
de prescrição. Uma falha/refusal/citação inválida não retorna um rascunho parcial utilizável.

Erros seguem `{"error":"mensagem"}`: 401 para autenticação; 422 para schema/contexto;
502 para provedor, deadline, recusa ou resultado inválido; 500 genérico para falha inesperada;
503 para modo real sem token privado. Mensagens e logs desse endpoint não incluem corpo
clínico nem texto bruto de exceções do provedor.

Arquitetura, catálogo, aprovação, endpoints públicos e operação estão em
`rafira_web/docs/clinical-agent.md`, no projeto da plataforma.
