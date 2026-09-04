from __future__ import annotations

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.app.auth import RequestContext
from backend.app.config import Settings
from backend.app.routers.alpha_sandbox_connections import (
    alpha_discover_metrc_sandbox_facilities,
    alpha_provision_metrc_sandbox_user,
    alpha_retry_metrc_sandbox_sync,
    alpha_run_metrc_sandbox_sync,
)
from backend.app.routers.sandbox_integrations import SandboxSyncRequest
from modules.alpha_mode import AlphaOperatingModeService
from modules.coman.models import Base, Facility, Organization


def _setup():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    with Session(engine) as session, session.begin():
        organization = Organization(name="Alpha DEV Guard", slug="alpha-dev-guard")
        session.add(organization)
        session.flush()
        facility = Facility(
            organization_id=organization.id,
            name="Alpha DEV Guard Facility",
            code="ALPHA-DEV",
            cultivation_enabled=True,
            production_enabled=True,
        )
        session.add(facility)
        session.flush()
        organization_id, facility_id = organization.id, facility.id
    context = RequestContext(
        user_id="alpha-dev",
        organization_id=organization_id,
        facility_id=facility_id,
        role="dev",
    )
    AlphaOperatingModeService(engine).set_mode(
        organization_id,
        facility_id,
        mode="doobielogic_sandbox",
        actor=context.user_id,
    )
    return engine, context


@pytest.mark.parametrize("call", ["provision", "discover", "sync", "retry"])
def test_direct_dev_metrc_provider_operations_fail_before_provider_setup(call):
    engine, context = _setup()
    settings = Settings(integration_encryption_key="alpha-dev-guard-encryption-key")

    with pytest.raises(HTTPException) as exc:
        if call == "provision":
            alpha_provision_metrc_sandbox_user(context=context, engine=engine, settings=settings)
        elif call == "discover":
            alpha_discover_metrc_sandbox_facilities(context=context, engine=engine, settings=settings)
        elif call == "sync":
            alpha_run_metrc_sandbox_sync(
                SandboxSyncRequest(resource=""),
                context=context,
                engine=engine,
                settings=settings,
            )
        else:
            alpha_retry_metrc_sandbox_sync(context=context, engine=engine, settings=settings)

    assert exc.value.status_code == 409
    assert "DoobieLogic Sandbox is active" in str(exc.value.detail)
