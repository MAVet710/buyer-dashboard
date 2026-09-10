"""Small bounded cache for the CPU-heavy Buyer forecast model.

The free API runtime has only a fraction of a CPU. Buyer Dashboard, overview,
market intelligence, and exports often request the same normalized forecast at
nearly the same time. Rebuilding it for each endpoint multiplies latency. This
module shares that work by source fingerprint and request controls while keeping
cache entries tenant/facility scoped and bounded in memory.
"""

from __future__ import annotations

from collections import OrderedDict
from functools import wraps
from threading import RLock
from time import monotonic
from typing import Any, Callable

from sqlalchemy import Engine

from modules.data_hub_repository import DataHubRepository

from ..auth import RequestContext

_INVENTORY_KEYS = ("inventory", "sandbox_buyer_inventory")
_SALES_KEYS = ("product_sales", "sandbox_buyer_sales", "sandbox_delivery_sales")
_SOURCE_KEYS = tuple(dict.fromkeys((*_INVENTORY_KEYS, *_SALES_KEYS)))
_CACHE_TTL_SECONDS = 300.0
_CACHE_MAX_ENTRIES = 4
_LOCK = RLock()
_CACHE: OrderedDict[tuple[Any, ...], tuple[float, Any]] = OrderedDict()


def _pick_fingerprint(sources: dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        source = sources.get(key)
        if source is not None:
            return str(source.fingerprint or "")
    return "missing"


def _cache_key(
    context: RequestContext,
    engine: Engine,
    target_doh: int,
    velocity_adjustment: float,
    sales_days: int,
) -> tuple[Any, ...]:
    rows = DataHubRepository(engine).list_active_sources(
        context.organization_id,
        context.facility_id,
        dataset_keys=_SOURCE_KEYS,
    )
    sources = {row.dataset_key: row for row in rows}
    return (
        id(engine),
        context.organization_id,
        context.facility_id,
        str(context.data_mode or ""),
        _pick_fingerprint(sources, _INVENTORY_KEYS),
        _pick_fingerprint(sources, _SALES_KEYS),
        int(target_doh),
        round(float(velocity_adjustment), 6),
        int(sales_days),
    )


def install_buyer_model_cache(module: Any) -> Callable[..., Any]:
    """Wrap ``buyer_parity._model`` once and return the installed callable."""

    current = module._model
    if getattr(current, "_doobielogic_cached_model", False):
        return current

    @wraps(current)
    def cached_model(
        context: RequestContext,
        engine: Engine,
        target_doh: int,
        velocity_adjustment: float,
        sales_days: int,
    ):
        if str(context.data_mode or "").strip().casefold() == "dutchie live":
            return current(context, engine, target_doh, velocity_adjustment, sales_days)

        key = _cache_key(context, engine, target_doh, velocity_adjustment, sales_days)
        now = monotonic()
        with _LOCK:
            cached = _CACHE.get(key)
            if cached is not None and now - cached[0] <= _CACHE_TTL_SECONDS:
                _CACHE.move_to_end(key)
                return cached[1]
            if cached is not None:
                _CACHE.pop(key, None)

            # Keep the miss computation under the lock. On the 0.1 CPU free
            # runtime, parallel copies of the same pandas pipeline only compete
            # for the same CPU and make every request slower. The next endpoint
            # receives the completed shared result instead of rebuilding it.
            result = current(context, engine, target_doh, velocity_adjustment, sales_days)
            _CACHE[key] = (monotonic(), result)
            _CACHE.move_to_end(key)
            while len(_CACHE) > _CACHE_MAX_ENTRIES:
                _CACHE.popitem(last=False)
            return result

    cached_model._doobielogic_cached_model = True  # type: ignore[attr-defined]
    module._model = cached_model
    return cached_model
