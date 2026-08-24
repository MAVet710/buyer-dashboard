import os
from pathlib import Path

from alembic.config import Config as AlembicConfig
from alembic.script import ScriptDirectory
from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import Engine, inspect, text
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .config import get_settings
from .routers.inventory import router as inventory_router
from .routers.audits import router as audit_router
from .routers.plants import router as plants_router
from .routers.production import router as production_router
from .routers.commercial import router as commercial_router
from .routers.compliance import router as compliance_router
from .routers.compliance_qa import router as compliance_qa_router
from .routers.account import router as account_router
from .routers.data_hub import router as data_hub_router
from .routers.location_settings import router as location_settings_router
from .routers.home import router as home_router
from .routers.product_360 import router as product_360_router
from .routers.doobie import router as doobie_router
from .routers.ai_agents import router as ai_agents_router
from .routers.ai_knowledge import router as ai_knowledge_router
from .routers.extraction import router as extraction_router
from .routers.extraction_parity import router as extraction_parity_router
from .routers.extraction_parity_brief import router as extraction_parity_brief_router
from .routers.package_studio import router as package_studio_router
from .routers.product_master import router as product_master_router
from .routers.retail_insights import router as retail_insights_router
from .routers.purchasing import router as purchasing_router
from .routers.buying_budget_parity import router as buying_budget_parity_router
from .routers.po_parity import router as po_parity_router
from .routers.trial import router as trial_router
from .routers.legal import router as legal_router
from .routers.admin import router as admin_router
from .routers.admin_facilities import update_facility
from .routers.admin_user_create import router as admin_user_create_router
from .routers.admin_uploads import router as admin_uploads_router
from .routers.integrations import router as integrations_router
from .routers.parity_tools import router as parity_tools_router
from .routers.buyer_parity import router as buyer_parity_router
from .routers.buyer_legacy_overview import router as buyer_legacy_overview_router
from .routers.buyer_parity_actions import router as buyer_parity_actions_router
from .routers.slow_movers_parity import router as slow_movers_parity_router
from .routers.executive_reports import router as executive_reports_router
from .routers.coman_parity import router as coman_parity_router
from .routers.analytics import router as analytics_router
from .database import get_engine
from .observability import install_observability

settings = get_settings()
settings.validate_production()


def _expected_schema_revision() -> str:
    config = AlembicConfig(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    script = ScriptDirectory.from_config(config)
    heads = script.get_heads()
    if len(heads) != 1:
        raise RuntimeError(f"Expected exactly one Alembic head, found {heads}")
    return heads[0]


EXPECTED_SCHEMA_REVISION = _expected_schema_revision()
RELEASE_SHA = (os.getenv("RELEASE_SHA") or "development").strip()
DECLARED_SCHEMA_HEAD = (os.getenv("EXPECTED_SCHEMA_HEAD") or "").strip()

if not settings.is_development and DECLARED_SCHEMA_HEAD and DECLARED_SCHEMA_HEAD != EXPECTED_SCHEMA_REVISION:
    raise RuntimeError(
        "Deployed schema-head declaration does not match the API image: "
        f"declared={DECLARED_SCHEMA_HEAD} image={EXPECTED_SCHEMA_REVISION}"
    )

app = FastAPI(title=settings.app_name, version="0.1.0")
install_observability(app)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.trusted_hosts)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_BUYER_UPLOAD_BACKED_PREFIXES = (
    f"{settings.api_prefix}/buyer-parity",
    f"{settings.api_prefix}/buyer-legacy-overview",
    f"{settings.api_prefix}/slow-movers-parity",
    f"{settings.api_prefix}/buying-budget-parity",
    f"{settings.api_prefix}/po-parity",
    f"{settings.api_prefix}/executive-reports",
)


@app.middleware("http")
async def enforce_buyer_data_mode(request: Request, call_next):
    data_mode = str(request.headers.get("X-DoobieLogic-Data-Mode") or "Uploads").strip().casefold()
    if data_mode in {"dutchie live", "dutchie_live", "live"} and request.url.path.startswith(_BUYER_UPLOAD_BACKED_PREFIXES):
        return JSONResponse(
            status_code=409,
            content={
                "detail": (
                    "Dutchie Live mode is active. The Streamlit app did not silently fall back to uploaded files in this mode. "
                    "Live Dutchie API fetching is not yet implemented in the web runtime, so Buyer workflows are paused instead of showing stale upload data. "
                    "Configure the Dutchie integration when live fetching is available, or switch Data source back to Uploads."
                )
            },
        )
    return await call_next(request)


@app.get("/health", tags=["system"])
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "service": "buyer-dash-api",
        "release_sha": RELEASE_SHA,
        "expected_schema_revision": EXPECTED_SCHEMA_REVISION,
    }


@app.get("/health/ready", tags=["system"])
def readiness(engine: Engine = Depends(get_engine)) -> dict:
    with engine.connect() as connection:
        connection.execute(text("select 1"))
        tables = set(inspect(connection).get_table_names())
        revision = connection.execute(text("select version_num from alembic_version")).scalar_one_or_none() if "alembic_version" in tables else None
    required = {"coman_organizations", "coman_facilities", "coman_products", "coman_inventory_lots", "coman_inventory_transactions", "retail_sales", "inventory_audits", "data_hub_imports", "legal_acceptance_events", "cultivation_plants", "retail_planning_policies", "integration_configurations"}
    missing = sorted(required - tables)
    revision_current = revision == EXPECTED_SCHEMA_REVISION or (settings.is_development and revision is None)
    ready = not missing and revision_current
    payload = {
        "status": "ready" if ready else "degraded",
        "service": "buyer-dash-api",
        "release_sha": RELEASE_SHA,
        "database": "connected",
        "schema_revision": revision,
        "expected_schema_revision": EXPECTED_SCHEMA_REVISION,
        "schema_matches": revision_current,
        "missing_tables": missing,
    }
    return payload if ready else JSONResponse(status_code=503, content=payload)


app.include_router(trial_router, prefix=settings.api_prefix)
app.include_router(inventory_router, prefix=settings.api_prefix)
app.include_router(audit_router, prefix=settings.api_prefix)
app.include_router(plants_router, prefix=settings.api_prefix)
app.include_router(production_router, prefix=settings.api_prefix)
app.include_router(commercial_router, prefix=settings.api_prefix)
app.include_router(compliance_router, prefix=settings.api_prefix)
app.include_router(compliance_qa_router, prefix=settings.api_prefix)
app.include_router(account_router, prefix=settings.api_prefix)
app.include_router(data_hub_router, prefix=settings.api_prefix)
app.include_router(location_settings_router, prefix=settings.api_prefix)
app.include_router(home_router, prefix=settings.api_prefix)
app.include_router(product_360_router, prefix=settings.api_prefix)
app.include_router(doobie_router, prefix=settings.api_prefix)
app.include_router(ai_agents_router, prefix=settings.api_prefix)
app.include_router(ai_knowledge_router, prefix=settings.api_prefix)
app.include_router(extraction_router, prefix=settings.api_prefix)
app.include_router(extraction_parity_router, prefix=settings.api_prefix)
app.include_router(extraction_parity_brief_router, prefix=settings.api_prefix)
app.include_router(package_studio_router, prefix=settings.api_prefix)
app.include_router(product_master_router, prefix=settings.api_prefix)
app.include_router(retail_insights_router, prefix=settings.api_prefix)
app.include_router(purchasing_router, prefix=settings.api_prefix)
app.include_router(buying_budget_parity_router, prefix=settings.api_prefix)
app.include_router(po_parity_router, prefix=settings.api_prefix)
app.include_router(legal_router, prefix=settings.api_prefix)
app.include_router(admin_router, prefix=settings.api_prefix)
app.add_api_route(
    f"{settings.api_prefix}/admin/facilities/{{target_facility_id}}/update",
    update_facility,
    methods=["POST"],
    tags=["admin"],
    name="update_facility",
)
app.include_router(admin_user_create_router, prefix=settings.api_prefix)
app.include_router(admin_uploads_router, prefix=settings.api_prefix)
app.include_router(integrations_router, prefix=settings.api_prefix)
app.include_router(parity_tools_router, prefix=settings.api_prefix)
app.include_router(buyer_parity_router, prefix=settings.api_prefix)
app.include_router(buyer_legacy_overview_router, prefix=settings.api_prefix)
app.include_router(buyer_parity_actions_router, prefix=settings.api_prefix)
app.include_router(slow_movers_parity_router, prefix=settings.api_prefix)
app.include_router(executive_reports_router, prefix=settings.api_prefix)
app.include_router(coman_parity_router, prefix=settings.api_prefix)
app.include_router(analytics_router, prefix=settings.api_prefix)
