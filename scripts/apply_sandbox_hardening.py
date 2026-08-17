from __future__ import annotations

from pathlib import Path
import re


def read_text(path: str) -> tuple[Path, str, str]:
    p = Path(path)
    raw = p.read_bytes()
    newline = "\r\n" if b"\r\n" in raw else "\n"
    text = raw.decode("utf-8").replace("\r\n", "\n")
    return p, text, newline


def write_text(p: Path, text: str, newline: str) -> None:
    if newline == "\r\n":
        text = text.replace("\n", "\r\n")
    p.write_bytes(text.encode("utf-8"))


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one match, found {count}")
    return text.replace(old, new, 1)


# ---------------------------------------------------------------------------
# services/demo_data_buyer.py: align every generated identity to DEV Sandbox.
# ---------------------------------------------------------------------------
p, text, nl = read_text("services/demo_data_buyer.py")
text = replace_once(
    text,
    '''    return {\n        "company_name": overrides.get("company_name") or rng.choice(_COMPANIES),\n        "store_name": overrides.get("store_name") or "New Bedford Flagship",\n        "facility_name": overrides.get("facility_name") or "South Coast Production Campus",\n        "license_number": overrides.get("license_number") or "MP281999",\n        "state": overrides.get("state") or "MA",\n    }''',
    '''    return {\n        "company_name": overrides.get("company_name") or "DEV Sandbox",\n        "store_name": overrides.get("store_name") or "Sandbox Facility",\n        "facility_name": overrides.get("facility_name") or "Sandbox Facility",\n        "license_number": overrides.get("license_number") or "SANDBOX-MA-DEMO",\n        "state": overrides.get("state") or "MA",\n    }''',
    "sandbox company profile",
)
text = replace_once(
    text,
    '''            "room": "Vault",\n            "company_name": profile["company_name"],''',
    '''            "room": "Vault",\n            "company_name": profile["company_name"],\n            "store_name": profile["store_name"],\n            "facility_name": profile["facility_name"],\n            "license_number": profile["license_number"],''',
    "catalog sandbox identity",
)
text = replace_once(
    text,
    '''            "Store": "New Bedford Flagship",''',
    '''            "Store": p["store_name"],''',
    "sales sandbox facility",
)
text = replace_once(
    text,
    '''            "Package ID": p["package_id"], "Batch": p["batch"], "License Number": "MP281999",''',
    '''            "Package ID": p["package_id"], "Batch": p["batch"], "License Number": p["license_number"],''',
    "manifest sandbox license",
)
write_text(p, text, nl)


# ---------------------------------------------------------------------------
# services/demo_data_operations.py: add measured extraction sandbox evidence.
# No operational pressure/temperature recipes are seeded.
# ---------------------------------------------------------------------------
p, text, nl = read_text("services/demo_data_operations.py")
text = replace_once(
    text,
    '''    company = company or {"company_name": "DoobieLogic Cannabis Group", "facility_name": "South Coast Production Campus", "license_number": "MP281999"}''',
    '''    company = company or {"company_name": "DEV Sandbox", "facility_name": "Sandbox Facility", "license_number": "SANDBOX-MA-DEMO"}''',
    "operations sandbox identity",
)
text = replace_once(
    text,
    '''        gross_profit = revenue - cogs\n        run_date = today - timedelta(days=(idx * 5) % 90)''',
    '''        gross_profit = revenue - cogs\n        run_date = today - timedelta(days=(idx * 5) % 90)\n        input_terpene_pct = round(rng.uniform(1.8, 4.8), 2)\n        retention_floor = {"BHO": 62.0, "Rosin": 70.0, "Ethanol": 28.0, "CO2": 48.0}[method]\n        terpene_retention_pct = round(min(96.0, max(20.0, rng.gauss(retention_floor, 7.5))), 1)\n        finished_terpene_pct = round(input_terpene_pct * terpene_retention_pct / 100.0, 2)\n        turnaround_hours = round({"BHO": 18.0, "Rosin": 14.0, "Ethanol": 30.0, "CO2": 26.0}[method] + rng.uniform(-3.0, 8.0), 1)\n        downtime_minutes = int(max(0, round(rng.gauss(24 + (idx % 4) * 9, 18))))\n        rework_required = bool(("low_yield" in problems and idx % 4 == 0) or idx % 11 == 7)\n        rework_reason = "Low yield / process review" if rework_required else ""\n        residual_solvent_status = (\n            "Not Applicable"\n            if method == "Rosin"\n            else ("Failed" if "failed_coa" in problems and idx % 7 == 0 else ("Pending" if coa_status == "Pending" else "Passed"))\n        )\n        settings_verified = True\n        sop_reference = f"SANDBOX-SOP-{method.upper()}-001"''',
    "extraction measured fields",
)
text = replace_once(
    text,
    '''            "coa_status": coa_status, "qa_hold": qa_hold, "notes": f"Feeds production orders: {', '.join(product_orders) or 'demo queue'}",''',
    '''            "coa_status": coa_status, "qa_hold": qa_hold,\n            "input_terpene_pct": input_terpene_pct, "finished_terpene_pct": finished_terpene_pct,\n            "terpene_retention_pct": terpene_retention_pct, "turnaround_hours": turnaround_hours,\n            "rework_required": rework_required, "rework_reason": rework_reason,\n            "residual_solvent_status": residual_solvent_status, "downtime_minutes": downtime_minutes,\n            "settings_verified": settings_verified, "sop_reference": sop_reference,\n            "run_settings_reference": "Validated facility SOP / equipment envelope; synthetic sandbox contains no operating setpoint recipe.",\n            "notes": f"Feeds production orders: {', '.join(product_orders) or 'demo queue'}",''',
    "extraction run fields",
)
write_text(p, text, nl)


# ---------------------------------------------------------------------------
# services/extraction_agent.py: make availability and new metrics first-class.
# ---------------------------------------------------------------------------
p, text, nl = read_text("services/extraction_agent.py")
text = replace_once(
    text,
    '''    out["cogs_usd"] = _num(raw, ("total_cogs_usd", "cogs_usd", "cogs"))\n\n    valid_input = out["input_weight_g"].gt(0)''',
    '''    out["cogs_usd"] = _num(raw, ("total_cogs_usd", "cogs_usd", "cogs"))\n    out["input_terpene_pct"] = _num(raw, ("input_terpene_pct", "starting_terpene_pct"))\n    out["finished_terpene_pct"] = _num(raw, ("finished_terpene_pct", "output_terpene_pct"))\n    out["terpene_retention_pct"] = _num(raw, ("terpene_retention_pct",))\n    out["turnaround_hours"] = _num(raw, ("turnaround_hours", "tat_hours"))\n    out["downtime_minutes"] = _num(raw, ("downtime_minutes",))\n    out["rework_required"] = _bool(raw, ("rework_required", "rework"))\n    out["rework_reason"] = _text(raw, ("rework_reason",))\n    out["residual_solvent_status"] = _text(raw, ("residual_solvent_status",))\n    out["settings_verified"] = _bool(raw, ("settings_verified",))\n    out["sop_reference"] = _text(raw, ("sop_reference", "validated_sop"))\n\n    valid_input = out["input_weight_g"].gt(0)''',
    "extraction derived optional fields",
)
text = replace_once(
    text,
    '''    output: dict[str, pd.DataFrame] = {"extraction_run_analysis": derived}\n\n    summary = _method_summary(derived)''',
    '''    output: dict[str, pd.DataFrame] = {"extraction_run_analysis": derived}\n    availability = pd.DataFrame([\n        {\n            "measurement": "terpene retention",\n            "available": bool(raw[[c for c in ("input_terpene_pct", "finished_terpene_pct", "terpene_retention_pct") if c in raw.columns]].shape[1] == 3),\n        },\n        {"measurement": "turnaround", "available": "turnaround_hours" in raw.columns},\n        {"measurement": "rework", "available": "rework_required" in raw.columns},\n        {"measurement": "residual solvent", "available": "residual_solvent_status" in raw.columns},\n        {"measurement": "downtime", "available": "downtime_minutes" in raw.columns},\n        {\n            "measurement": "validated run settings",\n            "available": {"settings_verified", "sop_reference"}.issubset(set(raw.columns)),\n        },\n    ])\n    output["extraction_data_availability"] = availability\n\n    summary = _method_summary(derived)''',
    "extraction availability dataset",
)
write_text(p, text, nl)


# ---------------------------------------------------------------------------
# services/doobie_client.py: Extraction Brief now uses local grounded service.
# ---------------------------------------------------------------------------
p, text, nl = read_text("services/doobie_client.py")
pattern = re.compile(
    r'''    def extraction_brief\(\n        self,\n        data: dict\[str, Any\],\n        state: str \| None = None,\n        question: str \| None = None,\n    \) -> dict\[str, Any\]:\n        return self\.call_endpoint\(\n            "/api/v1/support/extraction_brief",\n            self\._brief_payload\(\n                data,\n                state=state,\n                question=question,\n                default_question="Which extraction risks and process opportunities matter most\?",\n            \),\n        \)\n'''
)
replacement = '''    def extraction_brief(\n        self,\n        data: dict[str, Any],\n        state: str | None = None,\n        question: str | None = None,\n    ) -> dict[str, Any]:\n        # Extraction is intentionally local/data-first. The remote rules endpoint\n        # produced generic curriculum text and could recommend measurements that\n        # were not present in the current run data.\n        from services.extraction_brief import generate_extraction_brief\n\n        return generate_extraction_brief(data, state=state, question=question)\n'''
text, count = pattern.subn(replacement, text, count=1)
if count != 1:
    raise RuntimeError(f"extraction brief route: expected 1 regex match, found {count}")
write_text(p, text, nl)


# ---------------------------------------------------------------------------
# services/demo_data.py: readiness report + safe durable seeding behavior.
# ---------------------------------------------------------------------------
p, text, nl = read_text("services/demo_data.py")
text = replace_once(
    text,
    '''from services.demo_data_operations import build_operations_demo\n\nDEMO_DATA_VERSION = "full-app-simulation-v3"''',
    '''from services.demo_data_operations import build_operations_demo\nfrom services.sandbox_readiness import validate_sandbox_payload\n\nDEMO_DATA_VERSION = "full-app-simulation-v4-sandbox-grounded"''',
    "demo version/readiness import",
)
text = replace_once(
    text,
    '''    "demo_selected_scenario",\n    "_full_app_demo_version",''',
    '''    "demo_selected_scenario",\n    "demo_sandbox_readiness",\n    "_full_app_demo_version",''',
    "readiness session key",
)
old_return = '''    return {\n        **buyer,\n        **operations,\n        **cross_workspace,\n        "uploads": _build_uploads(buyer, operations, cross_workspace),\n        "as_of_date": as_of,\n        "scale": normalized_scale,\n        "problems": sorted(problem_set),\n    }'''
new_return = '''    payload = {\n        **buyer,\n        **operations,\n        **cross_workspace,\n        "uploads": _build_uploads(buyer, operations, cross_workspace),\n        "as_of_date": as_of,\n        "scale": normalized_scale,\n        "problems": sorted(problem_set),\n    }\n    payload["sandbox_readiness"] = validate_sandbox_payload(payload)\n    return payload'''
text = replace_once(text, old_return, new_return, "payload readiness")
text = replace_once(
    text,
    '''        result = ensure_coman_demo_dataset(\n            state=state, actor=actor, payload=payload, force=force\n        )''',
    '''        # Session simulation refreshes must never destroy durable QA work.\n        # Durable Co-Man data is replaced only through the explicit database-reset path.\n        result = ensure_coman_demo_dataset(\n            state=state, actor=actor, payload=payload, force=False\n        )''',
    "non-destructive durable seed",
)
text = replace_once(
    text,
    '''    state["demo_problem_set"] = list(payload["problems"])\n    state["data_hub_import_history"] = [''',
    '''    state["demo_problem_set"] = list(payload["problems"])\n    state["demo_sandbox_readiness"] = dict(payload.get("sandbox_readiness") or {})\n    state["data_hub_import_history"] = [''',
    "install readiness report",
)
write_text(p, text, nl)


# ---------------------------------------------------------------------------
# modules/coman/demo_data.py: version mismatch alone must never clear data.
# ---------------------------------------------------------------------------
p, text, nl = read_text("modules/coman/demo_data.py")
text = replace_once(
    text,
    '''        if existing_count and not force and existing_version == DEMO_DATA_VERSION:\n            state["active_organization_id"] = organization.id\n            state["active_facility_id"] = facility.id\n            return {\n                "seeded": False,\n                "already_present": True,\n                "organization_id": organization.id,\n                "facility_id": facility.id,\n            }\n        if existing_count:\n            _clear_demo_children(session, organization.id, facility.id)\n            session.flush()''',
    '''        if existing_count and not force:\n            state["active_organization_id"] = organization.id\n            state["active_facility_id"] = facility.id\n            return {\n                "seeded": False,\n                "already_present": True,\n                "organization_id": organization.id,\n                "facility_id": facility.id,\n                "version": existing_version,\n                "refresh_available": existing_version != DEMO_DATA_VERSION,\n            }\n        if existing_count and force:\n            _clear_demo_children(session, organization.id, facility.id)\n            session.flush()''',
    "safe version mismatch",
)
write_text(p, text, nl)


# ---------------------------------------------------------------------------
# Extend regression tests without rewriting their existing coverage.
# ---------------------------------------------------------------------------
p, text, nl = read_text("tests/test_demo_simulation.py")
append = '''\n\ndef test_demo_identity_and_readiness_are_unified():\n    payload = demo_data.build_demo_payload(date(2026, 8, 17), scale="small")\n    assert payload["company_profile"]["company_name"] == "DEV Sandbox"\n    assert payload["company_profile"]["store_name"] == "Sandbox Facility"\n    assert payload["company_profile"]["facility_name"] == "Sandbox Facility"\n    assert payload["sandbox_readiness"]["ready"] is True, payload["sandbox_readiness"]["issues"]\n\n\ndef test_session_refresh_does_not_request_destructive_coman_reseed(monkeypatch):\n    calls = []\n\n    def fake_seed(*, state, actor, payload, force=False, **kwargs):\n        calls.append(force)\n        return {"seeded": False, "already_present": True}\n\n    import modules.coman.demo_data as coman_demo\n    monkeypatch.setattr(coman_demo, "ensure_coman_demo_dataset", fake_seed)\n    state = _state()\n    demo_data.ensure_full_app_demo_session(state, actor="safe-seed")\n    demo_data.regenerate_demo_company(state, actor="safe-refresh")\n    assert calls\n    assert calls == [False, False]\n'''
if "test_demo_identity_and_readiness_are_unified" not in text:
    text += append
write_text(p, text, nl)

p, text, nl = read_text("tests/test_extraction_agent.py")
text = replace_once(
    text,
    '''    assert "extraction_method_summary" in datasets\n    assert "extraction_qa_holds" in datasets''',
    '''    assert "extraction_method_summary" in datasets\n    assert "extraction_qa_holds" in datasets\n    assert "extraction_data_availability" in datasets''',
    "extraction availability test",
)
write_text(p, text, nl)

print("Sandbox hardening patches applied successfully.")
