# Repository Audit (Milestone)

Date: 2026-04-04

## Objective
Audit the current codebase to document architecture, risks, and implementation status against `PLAN.md`.

## Current Architecture Snapshot
- **Framework/UI:** Streamlit single-app shell (`app.py`) with sidebar-driven navigation.
- **Core analytics:** Inventory, Trends, Delivery Impact, Slow Movers, PO Builder.
- **Extraction support:** Extraction Command Center with run/toll/compliance/input tabs plus AI Ops Brief.
- **AI layer:** Provider abstraction in `ai_providers.py` with OpenAI/Ollama selection and app-level fallback handling.
- **Compliance layer:** Structured retrieval model in `compliance_engine.py` with source-backed output requirements.

## Milestone Status vs PLAN
1. **Repository audit** ✅ (this document)
2. **Compliance data layer** ✅ (`compliance_engine.py`)
3. **Compliance Q&A page** ✅ (`app.py` Compliance Q&A section)
4. **AI provider abstraction** ✅ (`ai_providers.py` + app integration)
5. **Buyer intelligence** ✅ (`app.py` Buyer Intelligence section)
6. **Extraction module** ✅ (Extraction Command Center + AI Ops Brief)
7. **Admin tools** ✅ (`app.py` Admin Tools section)

## Risk / Debt Notes
- `app.py` remains a large monolith; helper functions are modular but still centralized in one file.
- No UI automation tests currently validate new Streamlit sections.
- AI-provider behavior is runtime/environment dependent; operator docs should define expected defaults per deployment.

## Recommended Next Iteration (Post-PLAN)
- Extract Buyer/Compliance/Extraction page logic into dedicated modules.
- Add lightweight integration tests for data-shaping helpers and provider fallback behavior.
- Add deployment profile docs (local-only/Ollama-first vs hosted/OpenAI-enabled).
