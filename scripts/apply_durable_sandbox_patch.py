from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise SystemExit(f"missing patch anchor: {label}")
    return text.replace(old, new, 1)


path = Path("services/demo_data.py")
text = path.read_text(encoding="utf-8")

text = replace_once(
    text,
    'from services.sandbox_readiness import validate_sandbox_payload\n',
    'from services.sandbox_readiness import validate_sandbox_payload\n'
    'from services.sandbox_persistence import persist_sandbox_sources, restore_sandbox_sources\n',
    "sandbox persistence import",
)
text = replace_once(
    text,
    'DEMO_DATA_VERSION = "full-app-simulation-v4-sandbox-grounded"',
    'DEMO_DATA_VERSION = "full-app-simulation-v5-supabase-durable"',
    "demo version",
)
text = replace_once(
    text,
    '    return {\n        "buyer_inventory": ("demo_inventory.csv", _csv(buyer["inventory"]), "text/csv"),',
    '    return {\n'
    '        "buyer_catalog": ("demo_buyer_catalog.csv", _csv(buyer["catalog"]), "text/csv"),\n'
    '        "buyer_inventory": ("demo_inventory.csv", _csv(buyer["inventory"]), "text/csv"),',
    "buyer catalog upload",
)

restore_helper = r'''

def _restored_csv(restored: Any, source_key: str) -> pd.DataFrame:
    source = restored.sources.get(source_key)
    if source is None:
        return pd.DataFrame()
    try:
        return pd.read_csv(io.BytesIO(source.payload))
    except Exception:
        return pd.DataFrame()


def _restore_persisted_demo_session(
    state: MutableMapping[str, Any], *, actor: str
) -> DemoSeedResult | None:
    """Restore DEV Sandbox from its Supabase-backed source set when available."""

    if not state.get("active_organization_id") or not state.get("active_facility_id"):
        return None
    try:
        restored = restore_sandbox_sources(state)
    except Exception as exc:
        state["_sandbox_supabase_error"] = f"{type(exc).__name__}: {exc}"
        return None
    if not restored.available:
        return None

    required = {
        "buyer_inventory",
        "buyer_sales",
        "buyer_extra_sales",
        "buyer_quarantine",
        "delivery_manifest",
        "delivery_sales",
        "compliance_sources",
        "extraction_inventory",
        "extraction_runs",
        "extraction_jobs",
        "nomenclature_catalog",
        "nomenclature_manifest",
        "commercial_partners",
        "commercial_orders",
        "commercial_order_lines",
        "commercial_ledger",
        "production_orders",
        "production_machines",
        "production_crew",
        "purchasing_budget",
    }
    if not required.issubset(restored.sources):
        state["_sandbox_supabase_error"] = (
            "Persisted sandbox source set is incomplete: "
            + ", ".join(sorted(required - set(restored.sources)))
        )
        return None

    manifest = dict(restored.manifest)
    state["demo_dataset_scale"] = str(manifest.get("scale") or "medium")
    state["demo_company_seed"] = int(manifest.get("company_seed") or 710)
    state["demo_catalog_seed"] = int(manifest.get("catalog_seed") or 811)
    state["demo_history_seed"] = int(manifest.get("history_seed") or 912)
    state["demo_problem_set"] = list(manifest.get("problems") or [])
    state["demo_selected_scenario"] = str(
        manifest.get("selected_scenario") or "Healthy baseline"
    )
    as_of = _as_date(manifest.get("as_of_date"))

    payload = build_demo_payload(
        today=as_of,
        scale=str(state["demo_dataset_scale"]),
        company_seed=int(state["demo_company_seed"]),
        catalog_seed=int(state["demo_catalog_seed"]),
        history_seed=int(state["demo_history_seed"]),
        problems=set(state["demo_problem_set"]),
    )
    source_map = {
        "buyer_catalog": "catalog",
        "buyer_inventory": "inventory",
        "buyer_sales": "sales",
        "buyer_quarantine": "quarantine",
        "delivery_manifest": "manifest",
        "compliance_sources": "compliance",
        "extraction_inventory": "extraction_inventory",
        "extraction_runs": "extraction_runs",
        "extraction_jobs": "extraction_jobs",
        "nomenclature_catalog": "nomenclature_catalog",
        "nomenclature_manifest": "nomenclature_manifest",
        "commercial_partners": "commercial_partners",
        "commercial_orders": "commercial_orders",
        "commercial_order_lines": "commercial_order_lines",
        "commercial_ledger": "commercial_ledger",
        "production_orders": "production_orders_export",
        "production_machines": "production_machines_export",
        "production_crew": "production_crew_export",
        "purchasing_budget": "budget",
    }
    for source_key, payload_key in source_map.items():
        frame = _restored_csv(restored, source_key)
        if not frame.empty:
            payload[payload_key] = frame

    extra_sales = _restored_csv(restored, "buyer_extra_sales")
    delivery_sales = _restored_csv(restored, "delivery_sales")
    payload["extra_sales"] = extra_sales if not extra_sales.empty else payload["sales"].copy()
    payload["delivery_sales"] = delivery_sales if not delivery_sales.empty else payload["sales"].copy()
    payload["detail"], payload["detail_product"] = _recompute_detail(
        payload["inventory"], payload["sales"], int(payload.get("reporting_days") or 60)
    )
    payload["uploads"] = {
        source_key: (source.filename, source.payload, "text/csv")
        for source_key, source in restored.sources.items()
    }
    payload["sandbox_readiness"] = validate_sandbox_payload(payload)

    result = _install_payload(state, payload, actor=actor, force=True, persist=False)
    state["_sandbox_supabase_restored"] = True
    state["_sandbox_supabase_persisted"] = True
    state["demo_data_banner"] = (
        "DEV Sandbox restored from Supabase. Session DataFrames are cached views of durable sandbox sources."
    )
    for cache_key, source_key in {
        "_cache_inv": "buyer_inventory",
        "_cache_sales": "buyer_sales",
        "_cache_extra_sales": "buyer_extra_sales",
        "_cache_quarantine": "buyer_quarantine",
    }.items():
        cached = state.get(cache_key)
        source = restored.sources.get(source_key)
        if isinstance(cached, dict) and source is not None:
            cached["durable"] = True
            cached["durable_id"] = source.id
            cached["fingerprint"] = source.fingerprint
    state["data_hub_import_history"] = [
        {
            "Dataset": key.replace("_", " ").title(),
            "File": source.filename,
            "Size": source.payload_size,
            "Status": "Supabase Sandbox",
            "Imported At": source.activated_at.isoformat() if source.activated_at else "",
            "Fingerprint": source.fingerprint,
        }
        for key, source in sorted(restored.sources.items())
    ]
    state.pop("_sandbox_supabase_error", None)
    return result
'''
text = replace_once(
    text,
    '\ndef _install_payload(\n',
    restore_helper + '\n\ndef _install_payload(\n',
    "restore helper insertion",
)
text = replace_once(
    text,
    'def _install_payload(\n    state: MutableMapping[str, Any], payload: dict[str, Any], *, actor: str, force: bool\n) -> DemoSeedResult:',
    'def _install_payload(\n'
    '    state: MutableMapping[str, Any],\n'
    '    payload: dict[str, Any],\n'
    '    *,\n'
    '    actor: str,\n'
    '    force: bool,\n'
    '    persist: bool = True,\n'
    ') -> DemoSeedResult:',
    "install payload signature",
)
text = replace_once(
    text,
    '    coman_seeded, coman_error = _seed_coman(state, actor, payload, force)\n'
    '    state["_coman_demo_seeded"] = coman_seeded\n'
    '    state["_coman_demo_error"] = coman_error\n',
    '    coman_seeded, coman_error = _seed_coman(state, actor, payload, force)\n'
    '    state["_coman_demo_seeded"] = coman_seeded\n'
    '    state["_coman_demo_error"] = coman_error\n'
    '    if persist and coman_seeded:\n'
    '        try:\n'
    '            persisted_count = persist_sandbox_sources(\n'
    '                state, payload, version=DEMO_DATA_VERSION, actor=actor\n'
    '            )\n'
    '            state["_sandbox_supabase_source_count"] = persisted_count\n'
    '            state["demo_data_banner"] = (\n'
    '                "DEV Sandbox is backed by Supabase. Session DataFrames are cached views of durable sandbox sources."\n'
    '            )\n'
    '        except Exception as exc:\n'
    '            state["_sandbox_supabase_persisted"] = False\n'
    '            state["_sandbox_supabase_error"] = f"{type(exc).__name__}: {exc}"\n',
    "persist after coman seed",
)
text = replace_once(
    text,
    '    _default_config(state, today)\n'
    '    if state.get("_full_app_demo_version") == DEMO_DATA_VERSION and not force:\n',
    '    _default_config(state, today)\n'
    '    if not force and state.get("_full_app_demo_version") != DEMO_DATA_VERSION:\n'
    '        restored = _restore_persisted_demo_session(state, actor=actor)\n'
    '        if restored is not None:\n'
    '            return restored\n'
    '    if state.get("_full_app_demo_version") == DEMO_DATA_VERSION and not force:\n',
    "prefer persisted sandbox",
)

path.write_text(text, encoding="utf-8")

readiness = Path("services/sandbox_readiness.py")
rtext = readiness.read_text(encoding="utf-8")
rtext = replace_once(
    rtext,
    'REQUIRED_UPLOADS = {\n    "buyer_inventory",',
    'REQUIRED_UPLOADS = {\n    "buyer_catalog",\n    "buyer_inventory",',
    "buyer catalog readiness",
)
readiness.write_text(rtext, encoding="utf-8")
