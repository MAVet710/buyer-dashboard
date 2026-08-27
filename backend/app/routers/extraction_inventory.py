from fastapi import APIRouter, Depends
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from modules.coman.models import Product
from modules.extraction.inventory_eligibility import classify_extraction_inventory
from modules.extraction.repository import ExtractionRepository
from modules.product_master.models import ProductMasterProfile
from ..auth import RequestContext, get_request_context, get_production_context
from ..database import get_engine

router = APIRouter(
    prefix="/extraction-inventory",
    tags=["extraction"],
    dependencies=[Depends(get_production_context)],
)


@router.get("/lots")
def eligible_lots(
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
):
    """Return the shared facility inventory projected for extraction work.

    This endpoint never mutates or hides inventory globally. It excludes
    consumer-ready finished goods and unrelated production materials from the
    Extraction workspace while retaining cannabis source material, extraction
    WIP/intermediates, and explicitly bulk extraction outputs.
    """

    rows = ExtractionRepository(engine).list_available_lots(
        context.organization_id,
        context.facility_id,
    )
    if not rows:
        return []

    product_ids = {str(row.get("product_id") or "") for row in rows if row.get("product_id")}
    with Session(engine) as session:
        products = {
            row.id: row
            for row in session.scalars(
                select(Product).where(
                    Product.organization_id == context.organization_id,
                    Product.id.in_(product_ids),
                )
            )
        }
        profiles = {
            row.product_id: row
            for row in session.scalars(
                select(ProductMasterProfile).where(
                    ProductMasterProfile.organization_id == context.organization_id,
                    ProductMasterProfile.product_id.in_(product_ids),
                )
            )
        }

    eligible = []
    for row in rows:
        product = products.get(str(row.get("product_id") or ""))
        if product is None:
            continue
        profile = profiles.get(product.id)
        if profile is not None and not profile.production_enabled:
            continue
        classification = classify_extraction_inventory(
            item_type=product.item_type,
            product_name=product.name,
            sku=product.sku,
            base_unit=product.base_unit,
            category=profile.category if profile else "",
            subcategory=profile.subcategory if profile else "",
            product_format=profile.product_format if profile else "",
        )
        if not classification.eligible:
            continue
        eligible.append(
            {
                **row,
                "item_type": product.item_type,
                "material_type": (
                    (profile.category or profile.product_format)
                    if profile
                    else product.item_type.replace("_", " ").title()
                ),
                "extraction_role": classification.role,
                "eligibility_reason": classification.reason,
            }
        )
    return eligible
