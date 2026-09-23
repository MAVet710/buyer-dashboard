"""Bounded history over existing label runs, never a second label ledger.

Search is server-side so an older tag remains discoverable after the first page.
The list does not hydrate COAs, event histories, QR graphics, or live inventory.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
import json
from typing import Any

from sqlalchemy import Engine, func, or_, select
from sqlalchemy.orm import Session

from modules.label_studio_workflow import LabelProductionEvent, LabelProductionRun, RUN_STATUSES


def _snapshot(value: str) -> dict[str, Any]:
    try:
        parsed = json.loads(value or "{}")
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def list_label_run_history(
    engine: Engine,
    organization_id: str,
    facility_id: str,
    *,
    search: str = "",
    status: str = "",
    created_from: date | None = None,
    created_to: date | None = None,
    offset: int = 0,
    limit: int = 50,
) -> dict[str, Any]:
    """Return summary metadata; dates are inclusive UTC calendar dates."""
    if not organization_id or not facility_id:
        raise ValueError("Choose an organization and facility before reading label history.")
    if not 1 <= limit <= 100 or offset < 0:
        raise ValueError("History page size must be 1–100 and offset must be nonnegative.")
    if status and status not in RUN_STATUSES:
        raise ValueError("Unknown label-run status.")
    if created_from and created_to and created_from > created_to:
        raise ValueError("The start date must not be after the end date.")
    terms = [
        LabelProductionRun.organization_id == organization_id,
        LabelProductionRun.facility_id == facility_id,
    ]
    if status:
        terms.append(LabelProductionRun.status == status)
    if created_from:
        terms.append(LabelProductionRun.created_at >= datetime.combine(created_from, time.min, tzinfo=timezone.utc))
    if created_to:
        terms.append(LabelProductionRun.created_at < datetime.combine(created_to + timedelta(days=1), time.min, tzinfo=timezone.utc))
    needle = search.strip()
    if needle:
        escaped = needle.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        pattern = f"%{escaped}%"
        terms.append(or_(
            LabelProductionRun.metrc_package_tag.ilike(pattern, escape="\\"),
            LabelProductionRun.id.ilike(pattern, escape="\\"),
            # Historical names/batches remain searchable after Product Master changes.
            LabelProductionRun.label_snapshot_json.ilike(pattern, escape="\\"),
        ))
    with Session(engine) as session:
        total = int(session.scalar(select(func.count()).select_from(LabelProductionRun).where(*terms)) or 0)
        runs = session.scalars(
            select(LabelProductionRun).where(*terms)
            .order_by(LabelProductionRun.created_at.desc(), LabelProductionRun.id.desc())
            .offset(offset).limit(limit)
        ).all()
        ids = [run.id for run in runs]
        print_counts: dict[str, tuple[int, Any]] = {}
        if ids:
            events = session.execute(
                select(LabelProductionEvent.run_id, func.count(), func.max(LabelProductionEvent.occurred_at))
                .where(
                    LabelProductionEvent.organization_id == organization_id,
                    LabelProductionEvent.facility_id == facility_id,
                    LabelProductionEvent.run_id.in_(ids),
                    LabelProductionEvent.event_type.in_(("printed", "reprinted")),
                ).group_by(LabelProductionEvent.run_id)
            ).all()
            print_counts = {run_id: (int(count), last_print) for run_id, count, last_print in events}
        items = []
        for run in runs:
            snapshot = _snapshot(run.label_snapshot_json)
            label = snapshot.get("label") or {}
            product = snapshot.get("product") or {}
            sources = snapshot.get("sources") or [snapshot.get("source") or {}]
            layout = snapshot.get("custom_design") or snapshot.get("print_layout") or {}
            count, last_print = print_counts.get(run.id, (0, None))
            items.append({
                "id": run.id,
                "product_id": run.product_id,
                "product_name": str(label.get("product_name") or product.get("name") or "Saved label"),
                "sku": str(product.get("sku") or ""),
                "package_tag": run.metrc_package_tag or "",
                "source_packages": [str(source.get("package_id") or source.get("lot_code") or "") for source in sources if isinstance(source, dict)],
                "quantity": run.quantity,
                "status": run.status,
                "created_by": run.created_by,
                "created_at": run.created_at,
                "printed_at": run.printed_at,
                "print_requests": count,
                "last_print_request_at": last_print,
                "width_in": layout.get("width_in"),
                "height_in": layout.get("height_in"),
                "design_revision": snapshot.get("design_revision", 0),
                "sandbox_test_pass": bool((snapshot.get("sandbox") or {}).get("sandbox_test_pass")),
            })
        return {"items": items, "total": total, "offset": offset, "limit": limit, "has_more": offset + len(items) < total}
