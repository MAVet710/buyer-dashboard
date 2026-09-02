# Execution

- Follow `PLAN.md`, `AGENTS.md`, and `docs/PERFORMANCE_CONTRACT.md`.
- Work one bounded milestone at a time and preserve a reviewable path back to the previous behavior.
- Summarize behavior, data-model/API, performance, migration, and test impact after each material step.

## Requirements

- Preserve approved UX/UI, navigation, mobile behavior, terminology, and functionality unless the task explicitly requests a product change.
- Preserve organization/facility/license isolation, permissions, append-only audit/history requirements, and canonical source-of-truth ownership.
- Use modular React/FastAPI/service structure; legacy Streamlit code is compatibility/reference, not the target for new production UI.
- Prefer deterministic domain services for business rules and mutations. AI must not become the ledger or bypass validation.
- Keep external traceability writes fail-closed until exact provider request/response/readback contracts are validated.
- Avoid per-row HTTP and SQL fan-out. Lists should use bounded summaries; expensive record detail should load on demand.
- Keep routine workspace rendering independent of optional external-provider latency unless the operator explicitly requested live-provider data.
- Do not trade correctness or compliance safety for lower latency, and do not trade performance for implementation convenience.
- Add regression coverage for the behavior being changed and run the applicable backend, frontend, browser, migration, container, security, and performance gates before merge.
