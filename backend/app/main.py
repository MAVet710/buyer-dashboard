from fastapi import Depends, FastAPI
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
from .routers.account import router as account_router
from .routers.data_hub import router as data_hub_router
from .routers.home import router as home_router
from .routers.doobie import router as doobie_router
from .routers.extraction import router as extraction_router
from .routers.package_studio import router as package_studio_router
from .routers.product_master import router as product_master_router
from .routers.retail_insights import router as retail_insights_router
from .routers.purchasing import router as purchasing_router
from .routers.legal import router as legal_router
from .routers.admin import router as admin_router
from .routers.integrations import router as integrations_router
from .database import get_engine
from .observability import install_observability

settings = get_settings()
settings.validate_production()
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


@app.get("/health", tags=["system"])
def health() -> dict[str, str]:
    return {"status": "ok", "service": "buyer-dash-api"}


@app.get("/health/ready", tags=["system"])
def readiness(engine: Engine = Depends(get_engine)) -> dict:
    with engine.connect() as connection:
        connection.execute(text("select 1"))
        tables = set(inspect(connection).get_table_names())
        revision = connection.execute(text("select version_num from alembic_version")).scalar_one_or_none() if "alembic_version" in tables else None
    required = {"coman_organizations", "coman_facilities", "coman_products", "coman_inventory_lots", "coman_inventory_transactions", "retail_sales", "inventory_audits", "data_hub_imports", "legal_acceptance_events", "cultivation_plants", "retail_planning_policies", "integration_configurations"}
    missing = sorted(required - tables)
    revision_current = revision in {None, "0036_supabase_data_api_hardening"}
    payload = {"status": "ready" if not missing and revision_current else "degraded", "service": "buyer-dash-api", "database": "connected", "schema_revision": revision, "expected_schema_revision": "0036_supabase_data_api_hardening", "missing_tables": missing}
    return payload if not missing and revision_current else JSONResponse(status_code=503, content=payload)


app.include_router(inventory_router, prefix=settings.api_prefix)
app.include_router(audit_router, prefix=settings.api_prefix)
app.include_router(plants_router, prefix=settings.api_prefix)
app.include_router(production_router, prefix=settings.api_prefix)
app.include_router(commercial_router, prefix=settings.api_prefix)
app.include_router(compliance_router, prefix=settings.api_prefix)
app.include_router(account_router, prefix=settings.api_prefix)
app.include_router(data_hub_router, prefix=settings.api_prefix)
app.include_router(home_router, prefix=settings.api_prefix)
app.include_router(doobie_router, prefix=settings.api_prefix)
app.include_router(extraction_router, prefix=settings.api_prefix)
app.include_router(package_studio_router, prefix=settings.api_prefix)
app.include_router(product_master_router, prefix=settings.api_prefix)
app.include_router(retail_insights_router, prefix=settings.api_prefix)
app.include_router(purchasing_router, prefix=settings.api_prefix)
app.include_router(legal_router, prefix=settings.api_prefix)
app.include_router(admin_router, prefix=settings.api_prefix)
app.include_router(integrations_router, prefix=settings.api_prefix)
