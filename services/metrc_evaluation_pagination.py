"""Full-page Metrc reads for proficiency-evaluation evidence.

The evaluation workbook contains list/read tasks whose result may span multiple
Metrc pages. This helper never treats page one as the complete answer. It walks
all provider-reported pages, fails closed if any page fails, and returns one
combined evidence envelope without exposing credentials.
"""

from __future__ import annotations

from typing import Any, Callable

from modules.regulatory.metrc_resources import METRC_V2_MAX_PAGE_SIZE
from services.metrc_client import fetch_metrc_resource


MAX_EVALUATION_PAGES = 10_000
DEFAULT_PAGE_SIZE = METRC_V2_MAX_PAGE_SIZE


def _total_pages(payload: Any) -> int:
    if not isinstance(payload, dict):
        return 1
    for key in ("TotalPages", "totalPages"):
        if payload.get(key) not in (None, ""):
            try:
                return max(1, int(payload[key]))
            except (TypeError, ValueError):
                return 1
    return 1


def fetch_all_metrc_resource_pages(
    *,
    state: str,
    user_api_key: str,
    integrator_api_key: str,
    resource: str,
    environment: str = "sandbox",
    license_number: str = "",
    path_parameters: dict[str, Any] | None = None,
    query: dict[str, Any] | None = None,
    page_size: int = DEFAULT_PAGE_SIZE,
    timeout_seconds: int = 30,
    max_pages: int = MAX_EVALUATION_PAGES,
    fetch_fn: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Fetch every provider page for one normalized Metrc resource.

    A non-paginated resource naturally completes after page one because its
    normalized read plan does not return a pagination envelope. Paginated reads
    continue through ``TotalPages``. A later-page failure invalidates the whole
    evaluation read; previously collected rows remain included only as diagnostic
    evidence and ``passed`` stays false.
    """

    fetch = fetch_fn or fetch_metrc_resource
    size = max(1, min(int(page_size), METRC_V2_MAX_PAGE_SIZE))
    ceiling = max(1, int(max_pages))
    page = 1
    total_pages = 1
    records: list[dict[str, Any]] = []
    pages: list[dict[str, Any]] = []

    while page <= total_pages:
        if page > ceiling:
            return {
                "ok": False,
                "passed": False,
                "status": "page_safety_ceiling",
                "resource": resource,
                "page_count": len(pages),
                "total_pages": total_pages,
                "records": records,
                "pages": pages,
                "message": f"Metrc reported more than the {ceiling}-page evaluation safety ceiling.",
            }
        result = fetch(
            state=state,
            user_api_key=user_api_key,
            integrator_api_key=integrator_api_key,
            resource=resource,
            environment=environment,
            license_number=license_number,
            path_parameters=path_parameters,
            query=query,
            page_size=size,
            page_number=page,
            timeout_seconds=timeout_seconds,
        )
        page_evidence = {
            "page_number": page,
            "http_status": int(result.get("http_status") or 0),
            "ok": bool(result.get("ok")),
            "correlation_id": str(result.get("correlation_id") or ""),
            "record_count": len(result.get("records") or []),
        }
        pages.append(page_evidence)
        if not result.get("ok") or int(result.get("http_status") or 0) != 200:
            return {
                "ok": False,
                "passed": False,
                "status": str(result.get("status") or "provider_error"),
                "resource": resource,
                "page_count": len(pages),
                "total_pages": total_pages,
                "failed_page": page,
                "records": records,
                "pages": pages,
                "message": str(result.get("message") or f"Metrc page {page} did not return HTTP 200."),
                "last_result": result,
            }
        records.extend(dict(row) for row in (result.get("records") or []) if isinstance(row, dict))
        total_pages = max(total_pages, _total_pages(result.get("payload")))
        page += 1

    return {
        "ok": True,
        "passed": True,
        "status": "complete",
        "resource": resource,
        "page_count": len(pages),
        "total_pages": total_pages,
        "records": records,
        "pages": pages,
        "message": f"Metrc read completed across {len(pages)} page(s).",
    }
