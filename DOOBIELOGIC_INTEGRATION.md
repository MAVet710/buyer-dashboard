# DoobieLogic Integration

## Required environment variables / secrets

Add these to Streamlit secrets or environment variables:

```toml
DOOBIELOGIC_URL = "https://your-doobielogic-service-url"
DOOBIELOGIC_API_KEY = "your-secure-api-key"
```

## Dashboard client

The repo now includes `doobielogic_client.py` with two call helpers:
- `buyer_intelligence(question, state, inventory_payload)`
- `extraction_intelligence(question, state, run_payload)`

## Intended insertion points in `app.py`

### Buyer Intelligence section
Replace the current AI brief button path in the `🧠 Buyer Intelligence` section with:

```python
from doobielogic_client import buyer_intelligence

if st.button("Generate AI Buyer Brief", key="buyer_intel_ai_brief"):
    with st.spinner("Generating buyer brief..."):
        payload = by_product.to_dict(orient="list")
        response, err = buyer_intelligence(
            question="What should I reorder, watch, and markdown based on this buyer dataset?",
            state="MA",
            inventory_payload=payload,
        )
    if err:
        st.error(err)
    elif response:
        st.markdown(response["answer"])
        if response.get("recommendations"):
            st.markdown("#### Recommended Actions")
            for rec in response["recommendations"]:
                st.write(f"- {rec}")
```

### Extraction Command Center
Replace the current extraction AI brief button path in `render_extraction_command_center()` with:

```python
from doobielogic_client import extraction_intelligence

if st.button("Generate AI Extraction Brief", key="ecc_ai_ops_brief"):
    with st.spinner("Analyzing extraction operations..."):
        run_payload = run_df.to_dict(orient="list")
        response, err = extraction_intelligence(
            question="What process, chemistry, QA, and release issues matter most in these extraction runs?",
            state="MA",
            run_payload=run_payload,
        )
    if err:
        st.error(err)
    elif response:
        st.markdown(response["answer"])
        if response.get("recommendations"):
            st.markdown("#### Recommended Actions")
            for rec in response["recommendations"]:
                st.write(f"- {rec}")
```

## API backend

In the DoobieLogic repo, use `doobielogic/api_v2.py` and run it with FastAPI/Uvicorn.

Example:

```bash
uvicorn doobielogic.api_v2:app --host 0.0.0.0 --port 8000
```
