"""Bounded performance caches for the CPU-heavy Buyer analytics path.

Render Free provides 0.1 CPU. Buyer Dashboard, overview, market intelligence,
and exports can otherwise parse the same files and rebuild the same pandas
forecast at nearly the same time. These caches share that immutable derived work
by tenant/facility, source fingerprint, and controls without changing business
logic or persistence semantics.
"""

from __future__ import annotations

import hashlib
from collections import OrderedDict
from functools import lru_cache, wraps
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
_PARSE_CACHE_MAX_ENTRIES = 4
_LOCK = RLock()
_CACHE: OrderedDict[tuple[Any, ...], tuple[float, Any]] = OrderedDict()
_PARSE_CACHE: OrderedDict[tuple[bytes, str], tuple[float, Any]] = OrderedDict()


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


def _install_scalar_memoizers() -> None:
    """Memoize pure row classifiers used thousands of times per sales file."""

    import services.web_buyer_parity as parity_service

    for name in ("_normalize_category", "_extract_size", "_extract_strain_type"):
        current = getattr(parity_service, name)
        if getattr(current, "_doobielogic_scalar_cache", False):
            continue
        memoized = lru_cache(maxsize=4096)(current)

        @wraps(current)
        def safe_cached(*args, __memoized=memoized, __current=current, **kwargs):
            try:
                return __memoized(*args, **kwargs)
            except TypeError:
                # Unhashable spreadsheet cell values are unusual, but preserving
                # the original classifier is safer than making caching a contract.
                return __current(*args, **kwargs)

        safe_cached._doobielogic_scalar_cache = True  # type: ignore[attr-defined]
        setattr(parity_service, name, safe_cached)


def _install_parser_cache(module: Any) -> None:
    current = module.read_tabular_bytes
    if getattr(current, "_doobielogic_parse_cache", False):
        return

    @wraps(current)
    def cached_parser(payload: bytes, filename: str):
        digest = hashlib.sha256(payload).digest()
        key = (digest, str(filename or "source.csv").casefold())
        now = monotonic()
        with _LOCK:
            cached = _PARSE_CACHE.get(key)
            if cached is not None and now - cached[0] <= _CACHE_TTL_SECONDS:
                _PARSE_CACHE.move_to_end(key)
                return cached[1].copy(deep=True)
            if cached is not None:
                _PARSE_CACHE.pop(key, None)

        frame = current(payload, filename)
        with _LOCK:
            _PARSE_CACHE[key] = (monotonic(), frame.copy(deep=True))
            _PARSE_CACHE.move_to_end(key)
            while len(_PARSE_CACHE) > _PARSE_CACHE_MAX_ENTRIES:
                _PARSE_CACHE.popitem(last=False)
        return frame

    cached_parser._doobielogic_parse_cache = True  # type: ignore[attr-defined]
    module.read_tabular_bytes = cached_parser


def install_buyer_model_cache(module: Any) -> Callable[..., Any]:
    """Install Buyer hotpath caches once and return the shared model callable."""

    _install_scalar_memoizers()
    _install_parser_cache(module)

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

            # Keep an identical miss under the lock. Parallel pandas copies on
            # 0.1 CPU only contend with one another; the waiting endpoint is
            # faster receiving the completed shared model than rebuilding it.
            result = current(context, engine, target_doh, velocity_adjustment, sales_days)
            _CACHE[key] = (monotonic(), result)
            _CACHE.move_to_end(key)
            while len(_CACHE) > _CACHE_MAX_ENTRIES:
                _CACHE.popitem(last=False)
            return result

    cached_model._doobielogic_cached_model = True  # type: ignore[attr-defined]
    module._model = cached_model
    return cached_model
