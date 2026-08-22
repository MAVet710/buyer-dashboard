from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import Engine

from modules.package_studio.service import (
    PackageStudioInputPlan,
    PackageStudioOutputPlan,
    PackageStudioPlan,
    PackageStudioService,
)
from ..auth import RequestContext, get_request_context
from ..database import get_engine


router = APIRouter(prefix="/package-studio", tags=["package-studio"])
COMMIT_ROLES = {"dev", "admin", "buyer", "planner", "supervisor", "operator", "qa"}


class InputPlan(BaseModel):
    lot_id: str
    quantity: float
    unit: str
    purpose: str = "source"


class OutputPlan(BaseModel):
    product_id: str
    lot_code: str
    inventory_quantity: float
    inventory_unit: str
    source_equivalent_quantity: float
    source_equivalent_unit: str
    compliance_package_id: str = ""
    purpose: str = "standard"
    location_code: str = "FINISHED-GOODS"
    notes: str = ""


class Plan(BaseModel):
    action_type: str
    inputs: list[InputPlan]
    outputs: list[OutputPlan]
    loss_quantity: float = 0
    source_unit: str = ""
    reason: str = ""
    notes: str = ""
    run_number: str = ""
    production_order_id: str | None = None
    commercial_order_id: str | None = None


def _plan(payload: Plan) -> PackageStudioPlan:
    return PackageStudioPlan(
        action_type=payload.action_type,
        inputs=tuple(PackageStudioInputPlan(**row.model_dump()) for row in payload.inputs),
        outputs=tuple(PackageStudioOutputPlan(**row.model_dump()) for row in payload.outputs),
        **payload.model_dump(exclude={"action_type", "inputs", "outputs"}),
    )


@router.get("/workspace")
def workspace(
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
):
    service = PackageStudioService(engine)
    return {
        "lots": [row.__dict__ for row in service.list_available_lots(context.organization_id, context.facility_id)],
        "products": [row.__dict__ for row in service.list_products(context.organization_id)],
        "runs": service.recent_runs(context.organization_id, context.facility_id),
        "can_commit": context.role.casefold() in COMMIT_ROLES,
    }


@router.get("/source-trail/{lot_id}")
def source_trail(
    lot_id: str,
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
):
    try:
        return PackageStudioService(engine).source_trail(
            lot_id,
            organization_id=context.organization_id,
            facility_id=context.facility_id,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/preview")
def preview(
    payload: Plan,
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
):
    try:
        return PackageStudioService(engine).preview(_plan(payload)).__dict__
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/commit", status_code=201)
def commit(
    payload: Plan,
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
):
    if context.role.casefold() not in COMMIT_ROLES:
        raise HTTPException(403, "Your role cannot commit package transformations.")
    try:
        return PackageStudioService(engine).commit(
            _plan(payload),
            organization_id=context.organization_id,
            facility_id=context.facility_id,
            actor=context.user_id,
        ).__dict__
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
