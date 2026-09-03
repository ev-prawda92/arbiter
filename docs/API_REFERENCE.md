# Arbiter API Reference — v1 Preview

## Discovery

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | Service health and infrastructure summary |
| GET | `/api/developer` | Developer manifest, auth state, docs links |
| GET | `/openapi.json` | Machine-readable OpenAPI schema |
| GET | `/docs` | Interactive Swagger documentation |
| GET | `/redoc` | ReDoc reference |

## Contract design

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/analyze` | Existing Source / Timing / Definition integrity review |
| POST | `/api/compile` | Compile prose rules into a proposed ResolutionSpecification |
| POST | `/api/compile-and-create` | Compile and persist only when status is READY |
| GET | `/api/contracts` | Contract registry |
| POST | `/api/contracts` | Persist a governed contract version |
| GET | `/api/contracts/{contract_id}/resolution-spec` | Latest governing specification |

## Authorities and evidence

| Method | Path | Purpose |
|---|---|---|
| GET/POST | `/api/authorities` | Governed authority registry |
| GET/POST | `/api/evidence` | Append-only evidence records |

## Resolution and operations

| Method | Path | Purpose |
|---|---|---|
| GET/POST | `/api/resolution-runs` | Replayable resolution executions |
| GET | `/api/overview` | Executive resolution-health view |
| GET | `/api/work-queue` | Prioritized operator exceptions |
| POST | `/api/work-queue/{id}` | Operator disposition state |
| GET | `/api/agent/brief` | Non-binding Resolution Operations Agent brief |
| GET | `/api/portfolio` | Portfolio resolution intelligence |

## Governance and verification

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/infrastructure` | Domain/control-plane state |
| GET | `/api/policy` | Governed policy |
| POST | `/api/policy` | Versioned policy update |
| GET | `/api/audit` | Audit events + hash-chain verification |
| GET/POST | `/api/benchmark*` | Development benchmark suite |

All preview write endpoints can be protected using the `X-Arbiter-Key` header when `ARBITER_API_KEYS` is configured.

## Case Registry & Templates (v0.9.4)

### `GET /api/cases`
Lists recent saved analysis cases.

### `GET /api/cases/{case_id}`
Returns a saved case plus its append-only run history.

### `GET /api/templates`
Lists reusable contract templates.

### `POST /api/templates`
Creates a template from explicit question/rule text.

### `POST /api/cases/{case_id}/template`
Promotes an existing case to a reusable template.

### `POST /api/analyze`
In addition to `question`, `criteria`, and `use_llm`, accepts optional `case_id`, `source_template_id`, and `actor`. Every call saves a case run and returns its `case` identity.
