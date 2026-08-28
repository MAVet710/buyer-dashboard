import logging
import os
from contextlib import asynccontextmanager
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
from .routers.production_mutations import router as production_mutations_router
from .routers.commercial import router as commercial_router
from .routers.warehouse import router as warehouse_router
from .routers.enterprise_control import router as enterprise_control_router
from .routers.traceability_actions import router as traceability_actions_router
from .routers.compliance import router as compliance_router
from .routers.compliance_qa import router as compliance_qa_router
from .routers.account import router as account_router
from .routers.data_hub import router as data_hub_router
from .routers.location_settings import router as location_settings_router
from .routers.home import router as home_router
from .routers.product_360 import router as product_360_router
from .routers.package_360 import router as package_360_router
from .routers.doobie import router as doobie_router
from .routers.ai_agents import router as ai_agents_router
from .routers.ai_knowledge import router as ai_knowledge_router
from .routers.extraction import router as extraction_router
from .routers.extraction_inventory import router as extraction_inventory_router
from .routers.extraction_parity import router as extraction_parity_router
from .routers.extraction_parity_brief import router as extraction_parity_brief_router
from .routers.package_studio import router as package_studio_router
from .routers.product_master import router as product_master_router
from .routers.retail_insights import router as retail_insights_router
from .routers.purchasing import router as purchasing_router
from .routers.buying_budget_parity import router as buying_budget_parity_router
from .routers.po_parity import router as po_parity_router
from .routers.trial import router as trial_router
from .routers.beta import router as beta_router
from .routers.legal import router as legal_router
from .routers.admin import router as admin_router
from .routers.admin_facilities import update_facility
from .routers.admin_storefronts import router as admin_storefronts_router
from .routers.admin_user_create import router as admin_user_create_router
from .routers.admin_uploads import router as admin_uploads_router
from .routers.integrations import router as integrations_router
from .routers.native_integrations import router as native_integrations_router
from .routers.sandbox_integrations import router as sandbox_integrations_router
from .routers.label_printing import router as label_printing_router
from .routers.printing_external import router as printing_external_router
from .routers.webhooks import router as webhooks_router, legacy_router as legacy_webhooks_router
from .routers.parity_tools import router as parity_tools_router
from .routers.buyer_parity import router as buyer_parity_router
from .routers.buyer_legacy_overview import router as buyer_legacy_overview_router
from .routers.buyer_parity_actions import router as buyer_parity_actions_router
from .routers.slow_movers_parity import router as slow_movers_parity_router
from .routers.executive_reports import router as executive_reports_router
from .routers.coman_parity import router as coman_parity_router
from .routers.analytics import router as analytics_router
from .routers.control_tower import router as control_tower_router, public_router as commerce_portal_router
from .routers.storefronts import router as storefront_router, public_router as public_storefront_router
from .routers.external_api import router as external_api_router
from .database import get_engine
from .observability import install_observability
from .services.sandbox_extraction import ensure_rich_extraction_sandbox
from .services.sandbox_sales import sync_sandbox_retail_sales

logger = logging.getLogger(__name__)
settings = get_settings()
settings.validate_production()

# Public hosted storefronts are served from customer-specific first-level
# DoobieLogic subdomains. Keep the normal explicit origin allowlist for the
# authenticated operations app, and allow only HTTPS origins that are actually
# under doobielogic.io for the hosted storefront browser runtime. CORS remains
# a browser boundary rather than an authorization mechanism; protected API
# routes still require their existing tenant/auth dependencies.
DOOBIELOGIC_SUBDOMAIN_ORIGIN_REGEX = r"^https://[a-z0-9-]+\.doobielogic\.io$"


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


@asynccontextmanager
async def lifespan(_: FastAPI):
    engine = get_engine()
    sync_sandbox_retail_sales(engine)
    try:
        ensure_rich_extraction_sandbox(engine)
    except Exception:
        logger.exception("DEV Sandbox extraction realism seed failed")
    yield


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.is_development else None,
    redoc_url="/redoc" if settings.is_development else None,
    openapi_url="/openapi.json" if settings.is_development else None,
)
install_observability(app)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.trusted_hosts)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_origin_regex=DOOBIELOGIC_SUBDOMAIN_ORIGIN_REGEX,
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
async def add_security_response_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Robots-Tag"] = "noindex, nofollow, noarchive, nosnippet"
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    return response


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
    return {"status": "ok"}


@app.get("/health/ready", tags=["system"])
def readiness(engine: Engine = Depends(get_engine)) -> dict:
    with engine.connect() as connection:
        connection.execute(text("select 1"))
        tables = set(inspect(connection).get_table_names())
        revision = connection.execute(text("select version_num from alembic_version")).scalar_one_or_none() if "alembic_version" in tables else None
    required = {
        "coman_organizations",
        "coman_facilities",
        "coman_products",
        "coman_inventory_lots",
        "coman_inventory_transactions",
        "retail_sales",
        "inventory_audits",
        "data_hub_imports",
        "legal_acceptance_events",
        "cultivation_plants",
        "retail_planning_policies",
        "integration_configurations",
        "sop_documents",
        "label_reviews",
        "machine_telemetry_events",
        "cultivation_harvests",
        "accounting_sync_links",
        "printer_profiles",
        "label_print_jobs",
        "commerce_storefronts",
        "commerce_storefront_products",
        "commerce_storefront_order_requests",
    }
    missing = required - tables
    revision_current = revision == EXPECTED_SCHEMA_REVISION or (settings.is_development and revision is None)
    ready = not missing and revision_current
    payload = {
        "status": "ready" if ready else "degraded",
        "release_sha": RELEASE_SHA,
        "schema_revision": revision,
        "expected_schema_revision": EXPECTED_SCHEMA_REVISION,
        "schema_matches": revision_current,
    }
    return payload if ready else JSONResponse(status_code=503, content=payload)


app.include_router(trial_router, prefix=settings.api_prefix)
app.include_router(beta_router, prefix=settings.api_prefix)
app.include_router(inventory_router, prefix=settings.api_prefix)
app.include_router(audit_router, prefix=settings.api_prefix)
app.include_router(plants_router, prefix=settings.api_prefix)
app.include_router(production_router, prefix=settings.api_prefix)
app.include_router(production_mutations_router, prefix=settings.api_prefix)
app.include_router(commercial_router, prefix=settings.api_prefix)
app.include_router(warehouse_router, prefix=settings.api_prefix)
app.include_router(enterprise_control_router, prefix=settings.api_prefix)
app.include_router(traceability_actions_router, prefix=settings.api_prefix)
app.include_router(compliance_router, prefix=settings.api_prefix)
app.include_router(compliance_qa_router, prefix=settings.api_prefix)
app.include_router(account_router, prefix=settings.api_prefix)
app.include_router(data_hub_router, prefix=settings.api_prefix)
app.include_router(location_settings_router, prefix=settings.api_prefix)
app.include_router(home_router, prefix=settings.api_prefix)
app.include_router(product_360_router, prefix=settings.api_prefix)
app.include_router(package_360_router, prefix=settings.api_prefix)
app.include_router(doobie_router, prefix=settings.api_prefix)
app.include_router(ai_agents_router, prefix=settings.api_prefix)
app.include_router(ai_knowledge_router, prefix=settings.api_prefix)
app.include_router(extraction_router, prefix=settings.api_prefix)
app.include_router(extraction_inventory_router, prefix=settings.api_prefix)
app.include_router(extraction_parity_router, prefix=settings.api_prefix)
app.include_router(extraction_parity_brief_router, prefix=settings.api_prefix)
app.include_router(package_studio_router, prefix=settings.api_prefix)
app.include_router(product_master_router, prefix=settings.api_prefix)
app.include_router(retail_insights_router, prefix=settings.api_prefix)
app.include_router(purchasing_router, prefix=settings.api_prefix)
app.include_router(buying_budget_parity_router, prefix=settings.api_prefix)
app.include_router(po_parity_router, prefix=settings.api_prefix)
app.include_router(legal_router, prefix=settings.api_prefix)
app.include_router(legacy_webhooks_router, prefix=settings.api_prefix)
app.include_router(control_tower_router, prefix=settings.api_prefix)
app.include_router(commerce_portal_router, prefix=settings.api_prefix)
app.include_router(storefront_router, prefix=settings.api_prefix)
app.include_router(public_storefront_router, prefix=settings.api_prefix)
app.include_router(external_api_router, prefix=settings.api_prefix)
app.include_router(printing_external_router, prefix=settings.api_prefix)
app.include_router(admin_user_create_router, prefix=settings.api_prefix)
app.include_router(admin_router, prefix=settings.api_prefix)
app.include_router(admin_storefronts_router, prefix=settings.api_prefix)
app.add_api_route(
    f"{settings.api_prefix}/admin/facilities/{{target_facility_id}}/update",
    update_facility,
    methods=["POST"],
    tags=["admin"],
    name="update_facility",
)
app.include_router(admin_uploads_router, prefix=settings.api_prefix)
app.include_router(integrations_router, prefix=settings.api_prefix)
app.include_router(native_integrations_router, prefix=settings.api_prefix)
app.include_router(sandbox_integrations_router, prefix=settings.api_prefix)
app.include_router(label_printing_router, prefix=settings.api_prefix)
app.include_router(webhooks_router, prefix=settings.api_prefix)
app.include_router(parity_tools_router, prefix=settings.api_prefix)
app.include_router(buyer_parity_router, prefix=settings.api_prefix)
app.include_router(buyer_legacy_overview_router, prefix=settings.api_prefix)
app.include_router(buyer_parity_actions_router, prefix=settings.api_prefix)
app.include_router(slow_movers_parity_router, prefix=settings.api_prefix)
app.include_router(executive_reports_router, prefix=settings.api_prefix)
app.include_router(coman_parity_router, prefix=settings.api_prefix)
app.include_router(analytics_router, prefix=settings.api_prefix)
