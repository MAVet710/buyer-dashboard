# DoobieLogic Native AI Runtime

## Purpose

DoobieLogic owns the agent architecture. Model providers are replaceable inference transports, not the source of agent identity, authorization, business calculations, retrieval policy, or tenant scope.

The runtime flow is:

`trusted RequestContext -> authorized DatasetRegistry/tools -> deterministic Python/SQL when sufficient -> local model -> validation -> optional cloud fallback`

Operational AI is read-only. No AI tool creates purchase orders, edits inventory, changes METRC/Dutchie, changes audits, edits products, or modifies users/permissions. Future actions must be implemented separately with typed actions, authorization, preview, explicit human approval, audit logging, and execution.

## Architecture

`services/agent_registry.py` defines provider-neutral AgentProfile identities. `services/ai/runtime.py` owns orchestration. `services/ai/provider.py` defines the stable provider protocol. `services/ai/providers/` contains local, Gemini, OpenAI, and Doobie adapters. Provider SDK objects must not escape those adapters.

`backend/app/services/ai_datasets.py` builds the application DatasetRegistry from existing repositories and services. Dataset scope comes from the authenticated server-side RequestContext, never from model-generated arguments. DatasetSpecs define domain, description, allowed agents, role/capability requirements, field allowlists, sensitive fields, freshness, and bounded tool-row limits.

`services/ai/tools.py` exposes bounded read-only generic and domain tools. `services/ai/analytics.py` performs arithmetic before any LLM. Existing extraction formulas remain in `services/extraction_agent.py` and are reused rather than duplicated.

`services/ai/retrieval/` owns local knowledge ingestion, embeddings, hybrid retrieval, citations, authority ranking, and tenant filtering. `services/ai/mapping_memory.py` stores approved header mappings. `services/ai/telemetry.py` stores non-sensitive provider/tool/retrieval performance metadata. `services/ai/evals/` provides sanitized provider-parity cases and deterministic scoring.

## Agents

Current provider-neutral agents are Operations, Buyer, Purchasing, Inventory, Inventory Audit, Compliance, Nomenclature, Repack, Co-Man Production, Extraction Scientist, Commercial, Commercial Finance, Cultivation, and Data Hub.

Receiving remains an Inventory/Purchasing workflow because the application does not contain a distinct receiving workspace that justifies a separate persona. Executive intelligence remains an Operations capability. Competitor intelligence remains within Buyer/Commercial unless a separate durable workflow is added later.

## Providers and routing

The default mode is `local_first` with provider order `local,gemini,openai,doobie`. Local inference uses an OpenAI-compatible API and therefore can be backed by Ollama for development, vLLM for production, or another compatible server without changing agent code.

Fallback is objective. Examples include local provider unavailable, timeout, unsupported capability, malformed structured output, tool-call failure, or validation failure. Model self-reported confidence is metadata only and is not a sufficient fallback reason.

Set `AI_ALLOW_CLOUD_FALLBACK=false` or `AI_PROVIDER_MODE=local_only` to prevent cloud escalation. If all providers are unavailable, only AI-specific requests degrade; normal operational pages and deterministic workflows remain usable.

## Local development with Ollama

Run Ollama separately from DoobieLogic. Do not add the model to the FastAPI image.

1. Install Ollama using its normal host installation method.
2. Start the Ollama service.
3. Pull a tool-capable instruct model appropriate for the developer machine.
4. Optionally pull a local embedding model.
5. Configure DoobieLogic:

```env
AI_PROVIDER_MODE=local_first
AI_PROVIDER_ORDER=local,gemini,openai,doobie
AI_ALLOW_CLOUD_FALLBACK=true
LOCAL_LLM_BASE_URL=http://127.0.0.1:11434
LOCAL_LLM_MODEL=<ollama-model-name>
LOCAL_LLM_API_KEY=
LOCAL_EMBEDDING_BASE_URL=http://127.0.0.1:11434
LOCAL_EMBEDDING_MODEL=<embedding-model-name>
```

When FastAPI itself runs inside Docker and Ollama runs on the host, use an address reachable from that container (for example Docker Desktop commonly exposes `host.docker.internal`) instead of `127.0.0.1`.

Ollama exposes OpenAI-compatible routes below `/v1`; the provider normalizes a base URL with or without `/v1`.

Start the normal FastAPI/React application. A missing local model does not prevent application startup.

## Production inference

Production should keep inference independently deployable and privately reachable:

`ops.doobielogic.io -> FastAPI -> private authenticated inference endpoint -> self-hosted model`

Do not place a GPU requirement on the normal API container. Scale the inference service independently. Use a private network where possible and set `LOCAL_LLM_API_KEY` when the inference gateway requires bearer authentication. Keep Gemini, OpenAI, and Doobie credentials independent so fallback can be enabled or disabled without changing the local provider.

Required/optional AI environment variables:

```env
AI_PROVIDER_MODE=local_first
AI_PROVIDER_ORDER=local,gemini,openai,doobie
AI_ALLOW_CLOUD_FALLBACK=true
LOCAL_LLM_BASE_URL=https://private-inference.example.internal
LOCAL_LLM_API_KEY=<secret-if-required>
LOCAL_LLM_MODEL=<configured-model>
LOCAL_LLM_TIMEOUT_SECONDS=30
LOCAL_LLM_MAX_TOKENS=1400
LOCAL_LLM_TEMPERATURE=0.2
LOCAL_EMBEDDING_BASE_URL=https://private-embedding.example.internal
LOCAL_EMBEDDING_API_KEY=<secret-if-required>
LOCAL_EMBEDDING_MODEL=<configured-embedding-model>
LOCAL_EMBEDDING_TIMEOUT_SECONDS=20
GEMINI_API_KEY=<optional>
GEMINI_MODEL=gemini-3.5-flash-lite
OPENAI_API_KEY=<optional>
OPENAI_MODEL=<optional>
OPENAI_BASE_URL=https://api.openai.com
DOOBIE_AI_MODEL=doobie-cloud
AI_GEMINI_INPUT_COST_PER_MILLION=0
AI_GEMINI_OUTPUT_COST_PER_MILLION=0
AI_OPENAI_INPUT_COST_PER_MILLION=0
AI_OPENAI_OUTPUT_COST_PER_MILLION=0
```

Never expose these secrets through frontend environment values. LEVEL DEV may save the Local AI Runtime secret through the existing encrypted integration settings path; browser responses return only status/hints.

### Hosted workstation runtime (beta)

The current low-cost production path is:

`browser -> ops.doobielogic.io -> buyer-dash-api (Cloud Run) -> Cloudflare Access -> ai-runtime.doobielogic.io -> named Cloudflare Tunnel -> 127.0.0.1:11434`

Only the FastAPI backend may call the tunnel. Do not add `ai-runtime.doobielogic.io` or Access credentials to React/Vite configuration. Ollama remains bound to loopback and the tunnel makes outbound connections; TCP 11434 must not be forwarded by the router.

Workstation requirements:

- Ollama endpoint: `http://127.0.0.1:11434`
- generation model: `qwen3:14b`
- embedding model: `embeddinggemma:latest`
- tunnel name: `doobielogic-ai`
- tunnel UUID: `a0f60d07-a684-4f65-91ad-a622455a815f`
- tunnel config: `%USERPROFILE%\.cloudflared\config.yml` (never commit its credential file)
- Windows service: `cloudflared`, automatic startup

Production values for `buyer-dash-api` in project `rebelle-vendor-tools`, region `us-east1`:

```env
AI_PROVIDER_MODE=local_only
AI_PROVIDER_ORDER=local
AI_ALLOW_CLOUD_FALLBACK=false
LOCAL_LLM_BASE_URL=https://ai-runtime.doobielogic.io
LOCAL_LLM_MODEL=qwen3:14b
LOCAL_LLM_TIMEOUT_SECONDS=120
LOCAL_LLM_MAX_TOKENS=1400
LOCAL_LLM_TEMPERATURE=0.2
LOCAL_EMBEDDING_BASE_URL=https://ai-runtime.doobielogic.io
LOCAL_EMBEDDING_MODEL=embeddinggemma:latest
```

Map `LOCAL_LLM_ACCESS_CLIENT_ID` and `LOCAL_LLM_ACCESS_CLIENT_SECRET` to Google Secret Manager versions. Both generation and embedding providers use those same credentials as `CF-Access-Client-Id` and `CF-Access-Client-Secret`. Never store their values in Git, ordinary Cloud Run environment values, diagnostics, or logs.

The admin-only diagnostic route is `/api/v1/ai-agents/diagnostics`. It reports the effective base URL/model and bounded provider health, but never credential values.

Operational checks on Windows:

```powershell
Invoke-RestMethod http://127.0.0.1:11434/v1/models
Get-Service cloudflared
cloudflared tunnel info doobielogic-ai
Restart-Service cloudflared
```

An anonymous request to `https://ai-runtime.doobielogic.io/v1/models` must return an Access denial. A backend request carrying the service-token headers must return HTTP 200. If anonymous access succeeds, treat that as a security incident and disable the public hostname until the Access policy is corrected.

Troubleshooting by symptom:

- `local:unavailable:ConnectionError`: check Ollama, then the Windows service, then tunnel connectivity.
- `configured model not found`: compare `LOCAL_LLM_MODEL` with `/v1/models`; `name` and `name:latest` are treated as aliases.
- Cloudflare Access 403: confirm the Access application covers the hostname and both Secret Manager references are attached to the active Cloud Run revision.
- `provider timeout`: confirm workstation load/connectivity; generation is bounded by `LOCAL_LLM_TIMEOUT_SECONDS=120`.
- embedding health failure: test `/v1/embeddings` with `embeddinggemma:latest`; retrieval continues with tenant-filtered lexical fallback.

When Ollama, the workstation, or the tunnel is offline, the FastAPI health route and deterministic operational workflows must remain available. AI requests fail with a bounded provider-unavailable response; `local_only` must not silently invoke Gemini or OpenAI. Restore service with `Restart-Service cloudflared` and confirm Ollama is running; no application data repair is required.

This workstation is intentionally a beta inference host, not a highly available production architecture. Availability depends on workstation power, network, Ollama, `cloudflared`, and Cloudflare. The provider abstraction allows migration to a dedicated GPU host or another OpenAI-compatible endpoint without changing agent business logic.

Rollback production AI configuration without deleting revisions:

1. Record the currently active revision with `gcloud run services describe buyer-dash-api --region us-east1`.
2. Route 100% traffic to the previously known-good revision with `gcloud run services update-traffic buyer-dash-api --region us-east1 --to-revisions <revision>=100`.
3. If only AI must be disabled, clear the AI endpoint/model values or route to a revision without them; keep the normal API revision healthy.
4. Do not delete the tunnel, Access policy, secrets, or previous Cloud Run revisions during rollback.

## Health and diagnostics

Authorized diagnostics report provider configuration/reachability, selected model, structured-output/tool support, embedding health, knowledge-index health, last successful local call, last fallback, cloud-fallback state, and DatasetRegistry keys. Secrets are removed before the response is constructed.

AI telemetry records request ID, tenant identifiers, agent/task, provider/model, local/cloud status, latency, tool/retrieval counts, token estimates, configured cloud-cost estimate, fallback reason, validation result, and success. It does not store raw prompts, API keys, or raw operational datasets.

Use telemetry to measure local utilization and cloud fallback instead of guessing savings. Deterministic routes produce no model call; local-first reasoning produces no paid cloud call when the local provider succeeds.

## Dataset security

Every AI DatasetSpec must:

1. require organization scope;
2. require facility scope where operational data is facility-bound;
3. load data through an existing repository/service when one exists;
4. enforce role/capability requirements before tool registration;
5. define a field allowlist or bounded business-field policy;
6. strip sensitive fields centrally;
7. document source/freshness;
8. return bounded data to tools;
9. fail closed.

Do not add organization/facility arguments to model tool schemas. Tenant scope must remain immutable server-side RequestContext state.

## Knowledge and compliance grounding

Supported ingestion formats are PDF, DOCX, TXT, Markdown, and HTML/text exports. Documents and chunks store organization/facility/global scope, title/source/source type, authority level, jurisdiction, effective/upload date, version/hash, page/section, and optional source URL.

Authority levels distinguish government/regulatory material, approved facility SOP/equipment material, manufacturer documentation, technical/peer-reviewed references, industry material, and community/field-practice material. Lower-authority material must never silently become regulatory authority.

The Compliance Agent does not declare a practice compliant/noncompliant from model memory. Regulatory questions require retrieved authoritative evidence. When the appropriate source is missing, the runtime returns an evidence-missing response instead of inventing a rule.

Local embeddings are optional. If embedding inference or vector capability is unavailable, retrieval remains operational through tenant-filtered lexical relevance plus metadata/authority weighting.

## Persistent mapping memory

The mapping flow is:

`approved mapping -> deterministic aliases -> local-first header mapper -> validation -> human review -> approved memory`

Memory is scoped by organization, facility where applicable, dataset type, source/vendor, normalized source header, canonical field, and schema fingerprint. Row values are not sent to the mapping model.

## Evaluation and benchmark

CI does not require a live cloud provider. Provider-independent unit tests use fakes/mocks and deterministic fixtures.

Run the manual sanitized provider benchmark for one configured provider:

```bash
python -m services.ai.evals.runner --provider local
python -m services.ai.evals.runner --provider gemini
python -m services.ai.evals.runner --provider openai
python -m services.ai.evals.runner --provider doobie
```

Run every configured provider and emit machine-readable output:

```bash
python -m services.ai.evals.runner --provider all --json
```

Metrics include required facts, unsupported facts, structured-output validity, expected tool selection for deterministic cases, retrieval-grounding expectation, latency, estimated cost, provider, and model.

## Adding an agent

1. Add a provider-neutral `AgentProfile` to `services/agent_registry.py` only when the application has a genuinely distinct workflow.
2. Grant only required DatasetSpecs to the profile.
3. Register deterministic tools before relying on model arithmetic.
4. Define knowledge/retrieval requirements and source authority rules.
5. Reuse existing permission/capability semantics.
6. Add deterministic and provider-independent eval/test cases.

## Adding a dataset

1. Reuse the existing repository/service loader.
2. Register a `DatasetSpec` with description/domain/freshness.
3. Enforce trusted organization/facility scope in the loader.
4. Define explicit allowed fields and sensitive fields.
5. Restrict agents, roles, and capabilities.
6. Bound tool rows.
7. Add cross-tenant and sanitization tests.

## Adding a provider

Implement the `AIProvider` protocol: `health`, `generate`, `supports_tools`, and `supports_structured_output`. Convert provider-specific SDK responses into `AIResponse` and `ToolCall`. Do not expose provider SDK objects to agents, routers, datasets, or frontend callers.

## Future tuning

Feedback/eval persistence is only a foundation. Rows are not training-approved by default. Export includes only records separately marked `training_approved`; prompt/answer text is sanitized before storage and tenant identifiers are excluded from export output. Do not automatically train on customer operational data.
