# 🔑 DoobieLogic Key Setup (Simple Guide)

## Step 1 — Pick a key

Just make one up:

```
doobie-secret-420
```

---

## Step 2 — Put it in DoobieLogic (backend)

Where you run the API:

```bash
DOOBIELOGIC_API_KEY=doobie-secret-420
```

---

## Step 3 — Put it in Streamlit (dashboard)

Go to:
Settings → Secrets

Add:

```toml
DOOBIELOGIC_URL = "http://localhost:8000"
DOOBIELOGIC_API_KEY = "doobie-secret-420"
```

---

## Step 4 — Start the backend

```bash
uvicorn doobielogic.api_v2:app --host 0.0.0.0 --port 8000
```

---

## Step 5 — Test

1. Upload your CSVs like normal
2. Click AI button
3. If it works → you're done

---

## Troubleshooting

- "not configured" → URL missing
- "API error" → backend not running
- no response → wrong key

---

## That’s it

You now have a secure connection between:

Dashboard ↔ DoobieLogic Brain
