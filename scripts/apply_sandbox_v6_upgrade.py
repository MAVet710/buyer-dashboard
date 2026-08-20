from __future__ import annotations

from pathlib import Path
import re


def replace_once(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text()
    if old not in text:
        raise RuntimeError(f"Expected text not found in {path}: {old[:120]!r}")
    file.write_text(text.replace(old, new, 1))


def regex_once(path: str, pattern: str, replacement: str) -> None:
    file = Path(path)
    text = file.read_text()
    updated, count = re.subn(pattern, replacement, text, count=1, flags=re.S)
    if count != 1:
        raise RuntimeError(f"Expected one regex match in {path}, found {count}: {pattern[:120]!r}")
    file.write_text(updated)


# 1) Every sandbox scale has the same 120-day history. Scale controls volume only.
replace_once(
    "services/demo_data_buyer.py",
    '''DATASET_SCALES = {\n    "small": {"products": 28, "sales_rows": 950, "days": 45},\n    "medium": {"products": 96, "sales_rows": 6200, "days": 75},\n    "enterprise": {"products": 280, "sales_rows": 24000, "days": 120},\n}''',
    '''DATASET_SCALES = {\n    "small": {"products": 28, "sales_rows": 950, "days": 120},\n    "medium": {"products": 96, "sales_rows": 6200, "days": 120},\n    "enterprise": {"products": 280, "sales_rows": 24000, "days": 120},\n}''',
)

# 2) Retail inventory carries the fields the Inventory command center, receiving,
# audits, purchasing, Product 360, nomenclature, and reporting need.
regex_once(
    "services/demo_data_buyer.py",
    r'''def _inventory\(catalog: list\[dict\[str, Any\]\], today: date, problems: set\[str\]\) -> pd\.DataFrame:\n.*?\n\ndef _weighted_choice''',
    '''def _inventory(catalog: list[dict[str, Any]], today: date, problems: set[str]) -> pd.DataFrame:\n    rows = []\n    for idx, p in enumerate(catalog):\n        expiry_days = 20 + (idx * 17) % 360\n        if "expiring_inventory" in problems and idx % 11 == 0:\n            expiry_days = 8 + idx % 18\n        received_days = 5 + (idx * 11) % 150\n        received_date = today - timedelta(days=received_days)\n        total_on_hand = int(p["on_hand"])\n        reserved = min(total_on_hand, int(round(total_on_hand * 0.08))) if idx % 9 == 0 else 0\n        available = max(0, total_on_hand - reserved)\n        on_hold = "qa_hold" in problems and idx % 19 == 0\n        status = "Quarantine" if on_hold else "Available"\n        lab_status = "Pending" if on_hold else "Passed"\n        rows.append({\n            "Product Name": p["product_name"],\n            "Category": p["category"],\n            "Inventory Class": "Finished Retail",\n            "Item Type": "finished_good",\n            "Status": status,\n            "Available": available,\n            "Reserved": reserved,\n            "On Hand Total": total_on_hand,\n            "Inventory Unit": "unit",\n            "Batch": p["batch"],\n            "Room": p["room"],\n            "SKU": p["sku"],\n            "UPC": f"8500710{idx + 1:05d}",\n            "External Product ID": f"DEMO-DUTCHIE-PRODUCT-{idx + 1:05d}",\n            "Cost": p["unit_cost"],\n            "Med Price": p["retail_price"],\n            "Wholesale Price": p["wholesale_price"],\n            "Brand": p["brand"],\n            "Vendor": p["vendor"],\n            "Package Size": p["size_label"],\n            "Unit Size g": p["unit_size_g"],\n            "Unit Gross Profit": p["retail_gross_profit"],\n            "Gross Margin %": p["retail_gross_margin_pct"],\n            "Inventory Cost": round(available * p["unit_cost"], 2),\n            "Retail Value": round(available * p["retail_price"], 2),\n            "Received Date": received_date.isoformat(),\n            "Expiration Date": (today + timedelta(days=expiry_days)).isoformat(),\n            "Strain": p["strain"],\n            "EComm Strain Type": p["strain_type"],\n            "Package ID": p["package_id"],\n            "METRC Package ID": p["package_id"],\n            "Source Production Order": p["source_production_order"],\n            "Source Extraction Batch": p["source_extraction_batch"],\n            "COA ID": p["coa_id"],\n            "Lab Status": lab_status,\n            "Tags": "retail-ready;metrc-linked",\n            "License Number": p["license_number"],\n        })\n    return pd.DataFrame(rows)\n\n\ndef _weighted_choice''',
)

# 3) Guarantee the sales file spans all 120 calendar days and expose explicit
# reporting boundaries so every downstream velocity calculation uses the same window.
regex_once(
    "services/demo_data_buyer.py",
    r'''def _sales\(catalog: list\[dict\[str, Any\]\], today: date, count: int, days: int,\n           rng: random\.Random, delivery_products: set\[str\]\) -> pd\.DataFrame:\n.*?\n\ndef _calibrate_inventory_to_sales''',
    '''def _sales(catalog: list[dict[str, Any]], today: date, count: int, days: int,\n           rng: random.Random, delivery_products: set[str]) -> pd.DataFrame:\n    start = today - timedelta(days=days - 1)\n    rows: list[dict[str, Any]] = []\n    for idx in range(count):\n        p = _weighted_choice(catalog, rng)\n        sold_date = start + timedelta(days=rng.randrange(days))\n        delivery_boost = p["sku"] in delivery_products and sold_date >= today - timedelta(days=14)\n        qty = rng.choices([1, 2, 3, 4], [68, 22, 8, 2], k=1)[0]\n        if delivery_boost:\n            qty += rng.choice([0, 1, 1, 2])\n        discount = rng.uniform(0.78, 1.0)\n        order_time = datetime.combine(sold_date, time(rng.randint(9, 20), rng.randrange(0, 60)))\n        gross_sales = round(p["retail_price"] * qty, 2)\n        net_sales = round(gross_sales * discount, 2)\n        cogs = round(p["unit_cost"] * qty, 2)\n        gross_profit = round(net_sales - cogs, 2)\n        rows.append({\n            "Product Name": p["product_name"],\n            "Master Category": p["category"],\n            "Quantity Sold": qty,\n            "Gross Sales": gross_sales,\n            "Discount": round(gross_sales - net_sales, 2),\n            "Net Sales": net_sales,\n            "Unit Cost": p["unit_cost"],\n            "COGS": cogs,\n            "Gross Profit": gross_profit,\n            "Gross Margin %": round(gross_profit / net_sales * 100.0, 2) if net_sales else 0.0,\n            "Order ID": f"ORD-{idx // rng.choice([1, 1, 2, 3]) + 100000:07d}",\n            "Order Time": order_time.isoformat(sep=" "),\n            "Report Start": start.isoformat(),\n            "Report End": today.isoformat(),\n            "SKU": p["sku"],\n            "Batch ID": p["batch"],\n            "Package ID": p["package_id"],\n            "Brand": p["brand"],\n            "Vendor": p["vendor"],\n            "Package Size": p["size_label"],\n            "Store": p["store_name"],\n            "Customer Type": rng.choice(["Adult Use", "Adult Use", "Medical"]),\n            "Payment Type": rng.choice(["Cash", "Debit", "Cashless ATM"]),\n            "Source Production Order": p["source_production_order"],\n            "Source Extraction Batch": p["source_extraction_batch"],\n            "COA ID": p["coa_id"],\n        })\n    frame = pd.DataFrame(rows)\n    if len(frame) >= 2:\n        frame.loc[frame.index[0], "Order Time"] = datetime.combine(start, time(9, 5)).isoformat(sep=" ")\n        frame.loc[frame.index[1], "Order Time"] = datetime.combine(today, time(20, 5)).isoformat(sep=" ")\n    return frame\n\n\ndef _calibrate_inventory_to_sales''',
)

# 4) Production inventory is a first-class sandbox dataset, not an incidental
# extraction table. It remains linked to the same bulk material rows.
replace_once(
    "services/demo_data_operations.py",
    '''            "input_category": "Cannabis Input", "current_weight_g": input_g, "reserved_weight_g": reserved,\n            "available_weight_g": available, "cost_per_g": cost_per_g, "total_cost": round(input_g * cost_per_g, 2),\n            "status": "Quarantine" if "qa_hold" in problems and idx % 5 == 0 else ("Reserved" if reserved else "Available"),\n            "storage_location": f"Freezer-{idx % 4 + 1}" if method in {"BHO", "Rosin"} else f"Vault-{idx % 3 + 1}",\n            "intended_method": method, "notes": f"Synthetic demo lot linked to {run_id}",''',
    '''            "input_category": "Cannabis Input", "inventory_class": "Bulk / WIP", "item_type": "cannabis",\n            "inventory_unit": "g", "current_weight_g": input_g, "reserved_weight_g": reserved,\n            "available_weight_g": available, "cost_per_g": cost_per_g, "total_cost": round(input_g * cost_per_g, 2),\n            "status": "Quarantine" if "qa_hold" in problems and idx % 5 == 0 else ("Reserved" if reserved else "Available"),\n            "lab_status": "Pending" if "qa_hold" in problems and idx % 5 == 0 else "Passed",\n            "storage_location": f"Freezer-{idx % 4 + 1}" if method in {"BHO", "Rosin"} else f"Vault-{idx % 3 + 1}",\n            "source_extraction_batch": run_id, "facility_name": company["facility_name"],\n            "license_number": company["license_number"], "tags": "bulk;production;metrc-linked",\n            "intended_method": method, "notes": f"Synthetic demo lot linked to {run_id}",''',
)
replace_once(
    "services/demo_data_operations.py",
    '''    return {\n        "extraction_inventory": pd.DataFrame(inventory_rows),\n        "extraction_runs": pd.DataFrame(run_rows),\n        "extraction_jobs": pd.DataFrame(jobs),\n    }''',
    '''    production_inventory = pd.DataFrame(inventory_rows)\n    return {\n        "production_inventory": production_inventory.copy(),\n        "extraction_inventory": production_inventory.copy(),\n        "extraction_runs": pd.DataFrame(run_rows),\n        "extraction_jobs": pd.DataFrame(jobs),\n    }''',
)

# 5) Version the durable source contract. Old persisted v5 data must not be
# accepted as current, and selecting DEV Sandbox must restore/persist by scope
# even if login generated an in-memory demo before tenant selection.
replace_once(
    "services/demo_data.py",
    'DEMO_DATA_VERSION = "full-app-simulation-v5-supabase-durable"',
    'DEMO_DATA_VERSION = "full-app-simulation-v6-120d-inventory-complete"',
)
replace_once(
    "services/demo_data.py",
    '    "demo_production_orders_df",\n',
    '    "demo_production_orders_df",\n    "demo_production_inventory_df",\n    "production_inventory_df",\n',
)
replace_once(
    "services/demo_data.py",
    '''        "extraction_inventory": (\n            "demo_extraction_inventory.csv",\n            _csv(operations["extraction_inventory"]),\n            "text/csv",\n        ),''',
    '''        "production_inventory": (\n            "demo_production_inventory.csv",\n            _csv(operations["production_inventory"]),\n            "text/csv",\n        ),\n        "extraction_inventory": (\n            "demo_extraction_inventory.csv",\n            _csv(operations["extraction_inventory"]),\n            "text/csv",\n        ),''',
)
replace_once(
    "services/demo_data.py",
    '        "extraction_inventory",\n        "extraction_runs",',
    '        "production_inventory",\n        "extraction_inventory",\n        "extraction_runs",',
)
replace_once(
    "services/demo_data.py",
    '''    manifest = dict(restored.manifest)\n    state["demo_dataset_scale"] = str(manifest.get("scale") or "medium")''',
    '''    manifest = dict(restored.manifest)\n    persisted_version = str(manifest.get("version") or "")\n    if persisted_version != DEMO_DATA_VERSION:\n        state["_sandbox_supabase_error"] = (\n            f"Persisted sandbox version {persisted_version or 'unknown'} is stale; "\n            f"{DEMO_DATA_VERSION} is required."\n        )\n        return None\n    state["demo_dataset_scale"] = str(manifest.get("scale") or "medium")''',
)
replace_once(
    "services/demo_data.py",
    '        "extraction_inventory": "extraction_inventory",\n        "extraction_runs": "extraction_runs",',
    '        "production_inventory": "production_inventory",\n        "extraction_inventory": "extraction_inventory",\n        "extraction_runs": "extraction_runs",',
)
replace_once(
    "services/demo_data.py",
    'int(payload.get("reporting_days") or 60)',
    'int(payload.get("reporting_days") or 120)',
)
replace_once(
    "services/demo_data.py",
    'reporting_days = int(payload.get("reporting_days") or 60)',
    'reporting_days = int(payload.get("reporting_days") or 120)',
)
replace_once(
    "services/demo_data.py",
    'min_date = pd.Timestamp(payload["as_of_date"] - timedelta(days=180))',
    'min_date = pd.Timestamp(payload["as_of_date"] - timedelta(days=119))',
)
replace_once(
    "services/demo_data.py",
    '''        "demo_production_orders_df": "production_orders_export",\n        "demo_production_machines_df": "production_machines_export",''',
    '''        "demo_production_orders_df": "production_orders_export",\n        "demo_production_inventory_df": "production_inventory",\n        "demo_production_machines_df": "production_machines_export",''',
)
replace_once(
    "services/demo_data.py",
    '''        "ecc_inventory_log": "extraction_inventory",\n        "ecc_run_log": "extraction_runs",''',
    '''        "production_inventory_df": "production_inventory",\n        "ecc_inventory_log": "extraction_inventory",\n        "ecc_run_log": "extraction_runs",''',
)
regex_once(
    "services/demo_data.py",
    r'''def ensure_full_app_demo_session\(\n    state: MutableMapping\[str, Any\],\n    \*,\n    actor: str = "demo",\n    force: bool = False,\n    today: date \| None = None,\n\) -> DemoSeedResult:\n.*?\n\ndef regenerate_demo_company''',
    '''def ensure_full_app_demo_session(\n    state: MutableMapping[str, Any],\n    *,\n    actor: str = "demo",\n    force: bool = False,\n    today: date | None = None,\n) -> DemoSeedResult:\n    if not demo_enabled_for_state(state):\n        return DemoSeedResult(False, DEMO_DATA_VERSION, ())\n    _default_config(state, today)\n\n    has_scope = bool(state.get("active_organization_id") and state.get("active_facility_id"))\n    needs_scoped_hydration = bool(has_scope and not state.get("_sandbox_supabase_restored"))\n\n    # Authentication can build an in-memory demo before a tenant is selected.\n    # Once DEV Sandbox has a real org/facility scope, always try the durable\n    # Supabase source set even when the in-memory version already looks current.\n    if not force and has_scope and (\n        needs_scoped_hydration or state.get("_full_app_demo_version") != DEMO_DATA_VERSION\n    ):\n        restored = _restore_persisted_demo_session(state, actor=actor)\n        if restored is not None:\n            return restored\n\n    if (\n        state.get("_full_app_demo_version") == DEMO_DATA_VERSION\n        and not force\n        and not needs_scoped_hydration\n    ):\n        return DemoSeedResult(\n            False,\n            DEMO_DATA_VERSION,\n            tuple(state.get("_full_app_demo_sections", ())),\n            bool(state.get("_coman_demo_seeded")),\n            str(state.get("_coman_demo_error") or ""),\n        )\n\n    # If the selected sandbox has no durable v6 source set yet, regenerate the\n    # deterministic baseline and persist it into the selected Supabase scope.\n    payload = build_demo_payload(\n        today=_as_date(today or state.get("demo_as_of_date")),\n        scale=str(state.get("demo_dataset_scale") or "medium"),\n        company_seed=int(state.get("demo_company_seed") or 710),\n        catalog_seed=int(state.get("demo_catalog_seed") or 811),\n        history_seed=int(state.get("demo_history_seed") or 912),\n        problems=set(state.get("demo_problem_set") or []),\n    )\n    return _install_payload(state, payload, actor=actor, force=force or needs_scoped_hydration)\n\n\ndef regenerate_demo_company''',
)

# 6) Readiness means complete, coherent data -- not merely non-empty frames.
replace_once(
    "services/sandbox_readiness.py",
    '    "extraction_inventory",\n    "extraction_runs",',
    '    "production_inventory",\n    "extraction_inventory",\n    "extraction_runs",',
)
replace_once(
    "services/sandbox_readiness.py",
    '    "extraction_inventory",\n    "extraction_runs",',
    '    "production_inventory",\n    "extraction_inventory",\n    "extraction_runs",',
)
replace_once(
    "services/sandbox_readiness.py",
    '''EXTRACTION_REQUIRED_COLUMNS = {''',
    '''RETAIL_INVENTORY_REQUIRED_COLUMNS = {\n    "Product Name", "SKU", "Category", "Inventory Class", "Item Type",\n    "Status", "Available", "Reserved", "On Hand Total", "Inventory Unit",\n    "Batch", "Room", "Cost", "Med Price", "Brand", "Vendor",\n    "Package Size", "Received Date", "Expiration Date", "Strain",\n    "Package ID", "METRC Package ID", "COA ID", "Lab Status",\n    "Source Production Order", "Source Extraction Batch",\n}\n\nPRODUCTION_INVENTORY_REQUIRED_COLUMNS = {\n    "received_date", "material_name", "material_type", "strain",\n    "source_vendor", "batch_id_internal", "metrc_package_id",\n    "inventory_class", "item_type", "inventory_unit", "current_weight_g",\n    "reserved_weight_g", "available_weight_g", "cost_per_g", "total_cost",\n    "status", "lab_status", "storage_location", "source_extraction_batch",\n    "facility_name", "license_number",\n}\n\nSALES_REQUIRED_COLUMNS = {\n    "Product Name", "Master Category", "Quantity Sold", "Gross Sales",\n    "Net Sales", "Unit Cost", "COGS", "Gross Profit", "Order ID",\n    "Order Time", "Report Start", "Report End", "SKU", "Package ID",\n    "Brand", "Vendor", "Store",\n}\n\nEXTRACTION_REQUIRED_COLUMNS = {''',
)
replace_once(
    "services/sandbox_readiness.py",
    '''    sales = _frame(payload, "sales")\n    if not sales.empty and "Store" in sales.columns:\n        store_match = sales["Store"].astype(str).eq(SANDBOX_FACILITY_NAME).all()\n        checks["retail.store_identity"] = bool(store_match)\n        if not store_match:\n            issues.append("Retail sales Store values do not consistently match Sandbox Facility")\n\n    compliance = _frame(payload, "compliance")''',
    '''    inventory = _frame(payload, "inventory")\n    if not inventory.empty:\n        missing = RETAIL_INVENTORY_REQUIRED_COLUMNS - set(map(str, inventory.columns))\n        checks["retail_inventory.required_columns"] = not missing\n        if missing:\n            issues.append("Retail sandbox inventory is missing required fields: " + ", ".join(sorted(missing)))\n        classes = set(inventory.get("Inventory Class", pd.Series(dtype=str)).astype(str))\n        checks["retail_inventory.finished_retail"] = "Finished Retail" in classes\n        if "Finished Retail" not in classes:\n            issues.append("Retail sandbox inventory does not contain finished retail-ready products")\n\n    production_inventory = _frame(payload, "production_inventory")\n    if not production_inventory.empty:\n        missing = PRODUCTION_INVENTORY_REQUIRED_COLUMNS - set(map(str, production_inventory.columns))\n        checks["production_inventory.required_columns"] = not missing\n        if missing:\n            issues.append("Production sandbox inventory is missing required fields: " + ", ".join(sorted(missing)))\n        has_bulk = production_inventory.get("inventory_class", pd.Series(dtype=str)).astype(str).str.contains("Bulk", case=False, na=False).any()\n        checks["production_inventory.bulk_or_wip"] = bool(has_bulk)\n        if not has_bulk:\n            issues.append("Production sandbox inventory does not contain bulk/WIP packages")\n\n    sales = _frame(payload, "sales")\n    if not sales.empty:\n        missing = SALES_REQUIRED_COLUMNS - set(map(str, sales.columns))\n        checks["retail_sales.required_columns"] = not missing\n        if missing:\n            issues.append("Retail sandbox sales are missing required fields: " + ", ".join(sorted(missing)))\n        if "Store" in sales.columns:\n            store_match = sales["Store"].astype(str).eq(SANDBOX_FACILITY_NAME).all()\n            checks["retail.store_identity"] = bool(store_match)\n            if not store_match:\n                issues.append("Retail sales Store values do not consistently match Sandbox Facility")\n        order_times = pd.to_datetime(sales.get("Order Time"), errors="coerce").dropna()\n        span_days = int((order_times.max().normalize() - order_times.min().normalize()).days) + 1 if not order_times.empty else 0\n        checks["retail_sales.120_day_window"] = span_days == 120\n        if span_days != 120:\n            issues.append(f"Retail sandbox sales must span exactly 120 days; found {span_days}")\n\n    compliance = _frame(payload, "compliance")''',
)

# 7) Inventory v2 can still show production data if the durable ledger is
# temporarily unavailable; the session source is the same persisted sandbox data.
insert_pattern = r'''def build_production_inventory_table\(state: MutableMapping\[str, Any\]\) -> pd\.DataFrame:\n    """Read facility-scoped durable production packages from the shared ledger\."""'''
insert_replacement = '''def _production_inventory_session_fallback(state: MutableMapping[str, Any]) -> pd.DataFrame:\n    source = _first_frame(state, "production_inventory_df", "demo_production_inventory_df", "ecc_inventory_log")\n    if source.empty:\n        return pd.DataFrame()\n    now = pd.Timestamp.now().normalize()\n    received_col = _column(source, ("received_date", "received date", "received_at"))\n    received = pd.to_datetime(source[received_col], errors="coerce") if received_col else pd.Series(pd.NaT, index=source.index)\n    status = _text(source, ("status",), "Available").replace("", "Available")\n    frame = pd.DataFrame({\n        "SKU": _text(source, ("batch_id_internal", "sku")),\n        "Product": _text(source, ("material_name", "product name", "product")),\n        "Strain": _text(source, ("strain",)),\n        "Package ID": _text(source, ("metrc_package_id", "package id")),\n        "Lot": _text(source, ("batch_id_internal", "lot")),\n        "Vendor": _text(source, ("source_vendor", "vendor")),\n        "Room": _text(source, ("storage_location", "room", "location")),\n        "Category": _text(source, ("material_type", "category")),\n        "Status": status,\n        "Tags": _text(source, ("tags",)),\n        "Available": _number(source, ("available_weight_g", "available")),\n        "Reserved": _number(source, ("reserved_weight_g", "reserved")),\n        "Unit": _text(source, ("inventory_unit", "unit"), "g").replace("", "g"),\n        "30d Sold": 0.0,\n        "Daily Velocity": 0.0,\n        "DOH": pd.NA,\n        "Cost": _number(source, ("cost_per_g", "cost")),\n        "Retail": 0.0,\n        "Margin": pd.NA,\n        "Age": (now - received.dt.normalize()).dt.days.clip(lower=0).fillna(0).astype(int),\n        "Days to Expiry": pd.NA,\n        "Durable Lot ID": "",\n    })\n    frame["Attention"] = "Production ready"\n    frame.loc[status.astype(str).str.contains("quarantine|hold|failed", case=False, regex=True, na=False), "Attention"] = "Hold"\n    frame.loc[status.astype(str).str.contains("reserved", case=False, na=False), "Attention"] = "Reserved"\n    frame["_product_key"] = frame["Product"].map(_norm)\n    return frame\n\n\ndef build_production_inventory_table(state: MutableMapping[str, Any]) -> pd.DataFrame:\n    """Read facility-scoped durable production packages from the shared ledger."""'''
regex_once("modules/inventory_command_center.py", insert_pattern, insert_replacement)
replace_once(
    "modules/inventory_command_center.py",
    '''    except (ComanDatabaseConfigurationError, Exception):\n        return pd.DataFrame()''',
    '''    except (ComanDatabaseConfigurationError, Exception):\n        return _production_inventory_session_fallback(state)''',
)
replace_once(
    "modules/inventory_command_center.py",
    '''    return pd.DataFrame(rows)\n\n\ndef apply_inventory_filters''',
    '''    frame = pd.DataFrame(rows)\n    return frame if not frame.empty else _production_inventory_session_fallback(state)\n\n\ndef apply_inventory_filters''',
)

# 8) Co-Man demo product master should cover the full sandbox catalog at each scale.
replace_once(
    "modules/coman/demo_data.py",
    'DEMO_DATA_VERSION = "full-app-simulation-v5-unified-dev-sandbox"',
    'DEMO_DATA_VERSION = "full-app-simulation-v6-120d-inventory-complete"',
)
replace_once(
    "modules/coman/demo_data.py",
    'product_limit = {"small": 12, "medium": 42, "enterprise": 120}.get(str(payload.get("scale")), 42)',
    'product_limit = {"small": 28, "medium": 96, "enterprise": 280}.get(str(payload.get("scale")), len(catalog))',
)

print("Sandbox v6 upgrade applied successfully.")
