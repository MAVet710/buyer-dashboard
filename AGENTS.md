# Project

This repository is a private cannabis operations platform built in Python and Streamlit.

The platform supports three major workflows:
- Compliance and regulatory research
- Retail buying and inventory intelligence
- Extraction operations support

## Core instructions
- Do not remove existing functionality unless explicitly instructed.
- Preserve the current look and feel of the Streamlit UI.
- Prefer additive changes over destructive rewrites.
- Keep modules separated by concern.
- Do not hardcode a single AI provider into business logic.
- Use an AI provider abstraction layer.
- Compliance answers must rely on retrieval from structured source material, not model memory.

Every compliance answer must include:
- state
- medical or adult-use scope
- source citation
- source URL
- last updated date
- confidence or review status

## Guardrails
- Never invent regulations from model memory.
- Never silently remove functionality.
