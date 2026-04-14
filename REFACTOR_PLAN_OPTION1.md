# Option 1 Refactor Plan

## Goal
Keep the current manual upload workflow and split the giant `app.py` into smaller modules so DoobieLogic can be wired in safely.

## What stays exactly the same
- Manual inventory uploads
- Manual sales uploads
- Quarantine uploads
- Delivery impact uploads
- PO Builder workflow
- Existing KPI math and parsing logic
- Streamlit UI behavior

## What changes
- `app.py` becomes a thinner router
- Buyer Intelligence calls `doobielogic_client.py`
- Extraction AI calls `doobielogic_client.py`
- Shared helpers move into modules

## Suggested module split
- `auth_utils.py`
- `ai_utils.py`
- `buyer_intelligence_view.py`
- `extraction_view.py`
- `inventory_parsing.py`
- `po_builder_view.py`
- `delivery_impact_view.py`
- `doobielogic_client.py`

## Phase order
1. Extract helper functions with no UI impact
2. Extract Buyer Intelligence section
3. Extract Extraction Command Center section
4. Replace local AI brief buttons with DoobieLogic API calls
5. Keep fallback local AI paths in place until API is confirmed live

## Required secrets for buyer dashboard
```toml
DOOBIELOGIC_URL = "https://your-doobielogic-api-url"
DOOBIELOGIC_API_KEY = "your-secret-key"
```

## Required environment variable for DoobieLogic backend
```bash
DOOBIELOGIC_API_KEY=your-secret-key
```
