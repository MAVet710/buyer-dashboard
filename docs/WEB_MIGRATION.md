# Buyer Dash web migration

Buyer Dash is moving from a Streamlit-only application to a React client and
FastAPI service without removing the existing application before parity.

Production targets are `https://ops.doobielogic.io` for the React application
and `https://api.doobielogic.io` for the API. DNS is managed through Spaceship.
The mandatory release criteria
are tracked in `docs/WEB_CUTOVER_GATES.md`.

## Inventory source of truth

Retail and Production Inventory use the same durable SQL primitives:

- `coman_inventory_lots` identifies the facility-scoped package or lot.
- `coman_inventory_transactions` is the append-only quantity ledger.
- `coman_material_reservations` records committed material.
- `coman_products` supplies the canonical product or material identity.

The active organization, facility, and operating license determine whether the
ledger is projected as Retail or Production Inventory. Product `item_type` must
not determine the operation because cannabis flower may be either bulk material
or a sellable product depending on its licensed facility and package state.

Retail adds sales velocity, days on hand, pricing, margins, and purchasing
signals. Production adds material state, weight, QA, readiness, transformation
lineage, and optional plant inventory. These are projections over one durable
ledger, not separate session-state inventory systems.

## Local development

Backend:

```powershell
python -m pip install -r backend/requirements.txt
uvicorn backend.app.main:app --reload
```

Frontend:

```powershell
cd frontend
pnpm install
pnpm dev
```

During development, set `VITE_ORGANIZATION_ID` and `VITE_FACILITY_ID` in
`frontend/.env`. Production requests must use a Supabase bearer token and the
API must be configured with either `SUPABASE_JWT_SECRET` or
`SUPABASE_JWKS_URL`.
