"""Bounded Buyer read model over the same current observation used by Inventory AI.

No forecasting, new ledger, provider requests, or implicit unit conversions.
Uploaded sales metadata is secondary and cannot replace current stock on failure.
"""
from __future__ import annotations

import math
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from modules.coman.models import DataHubImport
from services.ai.datasets import DatasetAccessContext
from ..auth import RequestContext
from .ai_inventory import CurrentInventoryObservation, InventoryEvidenceUnavailable

SALES_KEYS = ("product_sales", "sandbox_buyer_sales", "sandbox_delivery_sales")


def uploaded_source_evidence(engine: Engine, context: RequestContext, *, include_inventory: bool = False) -> dict:
    try:
        with Session(engine) as session:
            # Do not decompress files just to show provenance on a stock screen.
            rows = session.execute(select(
                DataHubImport.dataset_key, DataHubImport.filename,
                DataHubImport.row_count, DataHubImport.activated_at,
            ).where(
                DataHubImport.organization_id == context.organization_id,
                DataHubImport.facility_id == context.facility_id,
                DataHubImport.status == "active",
                DataHubImport.dataset_key.in_((*SALES_KEYS, "inventory", "sandbox_buyer_inventory") if include_inventory else SALES_KEYS),
            ).order_by(DataHubImport.dataset_key)).all()
        return {
            "state": "available" if rows else "missing",
            "items": [{"dataset": row.dataset_key, "filename": row.filename,
                       "rows": row.row_count, "published_at": row.activated_at}
                      for row in rows],
            "message": "Sales publication dates are not coverage dates. Uploaded forecast inputs remain historical and are not substituted for current inventory.",
        }
    except Exception:
        # DB errors may contain connection details; never send them to a browser.
        return {"state": "unavailable", "items": [],
                "message": "Sales-source metadata could not be read. Current inventory remains independent; no zero-sales conclusion can be drawn."}


def current_buyer_inventory(
    context: RequestContext, engine: Engine, *, search: str = "", status: str = "",
    unit: str = "", offset: int = 0, limit: int = 50,
) -> dict:
    if not 1 <= limit <= 100 or not 0 <= offset <= 10000 or len(search) > 160 or len(status) > 64 or len(unit) > 32:
        raise ValueError("Invalid current-inventory filter or page range.")
    # The route uses get_retail_context; the observation also validates the
    # real facility/capability against the DB, including manually built contexts.
    access = DatasetAccessContext(
        context.organization_id, context.facility_id, context.user_id, context.role,
        context.capabilities or frozenset({"retail"}), operation_type="retail", engine=engine,
    )
    observation = CurrentInventoryObservation(context, engine)
    frame = observation.inventory(access)  # Missing/oversized evidence fails closed.
    evidence = observation.evidence(access).iloc[0].to_dict()
    records = frame.astype(object).where(frame.notna(), None).to_dict(orient="records")
    facets = {
        "statuses": sorted({row["status"] for row in records}),
        "units": sorted({row["unit"] for row in records}),
    }
    term = search.strip().casefold()
    rows = [row for row in records if
            (not status or row["status"].casefold() == status.casefold()) and
            (not unit or row["unit"] == unit) and
            (not term or any(term in str(row[key] or "").casefold() for key in
                             ("package_id", "lot_code", "sku", "product_name", "location", "source_name")))]
    rows.sort(key=lambda row: (str(row["product_name"]).casefold(), row["sku"], row["unit"], row["id"]))
    totals: dict[str, dict] = {}
    for row in rows:
        group = totals.setdefault(row["unit"], {"unit": row["unit"], "on_hand": 0.0, "available": 0.0, "reserved": 0.0})
        for column in ("on_hand", "available", "reserved"):
            value = float(row[column])
            if not math.isfinite(value) or not math.isfinite(group[column] + value):
                raise InventoryEvidenceUnavailable("Current inventory contains invalid quantities. No stock total is supplied.")
            group[column] += value
    return {
        "evidence": evidence,
        "items": rows[offset:offset + limit],
        "total": len(rows), "offset": offset, "limit": limit,
        "has_more": offset + limit < len(rows), "facets": facets,
        "summary": {
            "package_count": len(rows), "product_count": len({row["product_id"] for row in rows}),
            "held_packages": sum(any(token in row["status"].casefold() for token in ("hold", "quarantine", "failed")) for row in rows),
            "totals_by_unit": [totals[key] for key in sorted(totals)],
            "scope": "all matching packages, not just the displayed page",
        },
        "sales_sources": uploaded_source_evidence(engine, context),
    }
