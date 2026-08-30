# Hosted DoobieLogic AI using a workstation Ollama runtime

This document describes the supported development/beta topology for allowing the hosted DoobieLogic FastAPI service to use an Ollama instance running on a trusted workstation without exposing Ollama directly to the public internet.

## Architecture

```text
Hosted DoobieLogic frontend
        |
        v
Cloud Run FastAPI backend
        |
        | HTTPS + Cloudflare Access service-token headers
        v
https://ai-runtime.doobielogic.io
        |
        v
Cloudflare Access + Cloudflare Tunnel
        |
        v
Trusted workstation: http://127.0.0.1:11434
        |
        v
Ollama / qwen3:14b + embeddinggemma:latest
```

Do not port-forward TCP 11434 from the workstation and do not expose Ollama directly to the public internet.

## Cloudflare requirements

Create a named Cloudflare Tunnel on the trusted workstation and map the public hostname `ai-runtime.doobielogic.io` to `http://127.0.0.1:11434`.

Protect the hostname with Cloudflare Access and create a Service Auth policy backed by a service token. Store the token values only in the hosted deployment secret store:

- `LOCAL_LLM_ACCESS_CLIENT_ID`
- `LOCAL_LLM_ACCESS_CLIENT_SECRET`

The DoobieLogic local provider sends those values as `CF-Access-Client-Id` and `CF-Access-Client-Secret` headers.

## Hosted FastAPI configuration

Configure the hosted FastAPI service with:

```text
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

LOCAL_LLM_ACCESS_CLIENT_ID=<Cloudflare Access service-token client id>
LOCAL_LLM_ACCESS_CLIENT_SECRET=<Cloudflare Access service-token client secret>
```

The Cloudflare service-token credentials must never be committed to GitHub.

## Workstation requirements

The trusted workstation must remain powered on and connected to the internet while the hosted site is using it. Ollama and the Cloudflare Tunnel service must both be running.

Recommended Ollama models for the current runtime:

```text
qwen3:14b
embeddinggemma:latest
```

Verify Ollama locally before testing the hosted service:

```powershell
Invoke-RestMethod http://127.0.0.1:11434/v1/models | ConvertTo-Json -Depth 6
```

## Hosted verification

After the Cloud Run service has been configured and restarted, use the authenticated admin diagnostics endpoint:

```text
GET /api/v1/ai-agents/diagnostics
```

The local provider should report:

```json
{
  "configured": true,
  "reachable": true,
  "model": "qwen3:14b",
  "detail": "ok"
}
```

The embedding provider should likewise report reachable with `embeddinggemma:latest`.

If diagnostics report the local provider as unavailable, verify the tunnel first, then Cloudflare Access policy/service-token headers, then the configured public endpoint/model.

## Production note

This topology is intended for development, private beta, and low-volume testing. A production customer-facing deployment should move the same provider-neutral runtime to an always-on inference host rather than depend on a developer workstation.
