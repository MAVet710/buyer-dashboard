from __future__ import annotations

from pathlib import Path


def read_text(path: str) -> tuple[Path, str, str]:
    p = Path(path)
    raw = p.read_bytes()
    newline = "\r\n" if b"\r\n" in raw else "\n"
    return p, raw.decode("utf-8").replace("\r\n", "\n"), newline


def write_text(path: Path, text: str, newline: str) -> None:
    if newline == "\r\n":
        text = text.replace("\n", "\r\n")
    path.write_bytes(text.encode("utf-8"))


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one match, found {count}")
    return text.replace(old, new, 1)


p, text, nl = read_text("modules/data_hub.py")

text = replace_once(
    text,
    "from modules.data_hub_repository import DataHubRepository, hydrate_durable_sources\n",
    "from modules.data_hub_repository import DataHubRepository, hydrate_durable_sources\nfrom services.data_mapping_agent import suggest_column_mapping\n",
    "mapping agent import",
)

text = replace_once(
    text,
    '''    "Product Sales": {\n        "Product": ("product", "product name", "item", "item name", "name"),\n        "Units sold": ("quantity sold", "qty sold", "units sold", "items sold", "total inventory sold"),\n    },''',
    '''    "Product Sales": {\n        "Product": ("product", "product name", "item", "item name", "name"),\n        "Units sold": ("quantity sold", "qty sold", "units sold", "items sold", "total inventory sold"),\n        "Category": ("category", "subcategory", "master category", "department"),\n    },''',
    "product sales category requirement",
)

requirements_end = '''}\n\nRETAIL_CACHE_KEYS = tuple(str(spec["cache_key"]) for spec in RETAIL_DATASETS)'''
canonical_block = '''}\n\nCANONICAL_COLUMN_NAMES = {\n    "Inventory": {"Product": "Product Name", "Category": "Category", "On hand": "On Hand"},\n    "Product Sales": {\n        "Product": "Product Name",\n        "Units sold": "Quantity Sold",\n        "Category": "Category",\n    },\n    "Sales / Pricing Detail": {"Product": "Product Name", "Revenue": "Net Sales"},\n    "Quarantine": {"Product": "Product Name"},\n}\n\nRETAIL_CACHE_KEYS = tuple(str(spec["cache_key"]) for spec in RETAIL_DATASETS)'''
text = replace_once(text, requirements_end, canonical_block, "canonical column names")

file_bytes_block = '''def _file_bytes(uploaded_file: Any) -> bytes:\n    if hasattr(uploaded_file, "getvalue"):\n        return bytes(uploaded_file.getvalue())\n    uploaded_file.seek(0)\n    payload = bytes(uploaded_file.read())\n    uploaded_file.seek(0)\n    return payload\n\n\ndef stage_uploaded_dataset('''
helper_block = '''def _file_bytes(uploaded_file: Any) -> bytes:\n    if hasattr(uploaded_file, "getvalue"):\n        return bytes(uploaded_file.getvalue())\n    uploaded_file.seek(0)\n    payload = bytes(uploaded_file.read())\n    uploaded_file.seek(0)\n    return payload\n\n\nclass _MappedUpload(BytesIO):\n    pass\n\n\ndef build_mapped_upload(\n    uploaded_file: Any,\n    dataset_label: str,\n    matches: Mapping[str, str],\n) -> Any:\n    """Return a reviewed source rewritten to canonical Buyer Dashboard headers."""\n    requirements = DATASET_REQUIREMENTS.get(dataset_label, {})\n    canonical = CANONICAL_COLUMN_NAMES.get(dataset_label, {})\n    missing = [field for field in requirements if not str(matches.get(field) or "").strip()]\n    if missing:\n        raise ValueError("Required mapping is unresolved: " + ", ".join(missing))\n\n    payload = _file_bytes(uploaded_file)\n    name = str(getattr(uploaded_file, "name", dataset_label))\n    extension = Path(name).suffix.casefold()\n    if extension == ".csv":\n        frame = pd.read_csv(BytesIO(payload))\n    elif extension in {".xlsx", ".xls"}:\n        frame = pd.read_excel(BytesIO(payload))\n    else:\n        raise ValueError("Use a CSV, XLSX, or XLS file.")\n\n    columns = [str(column) for column in frame.columns]\n    invalid = [\n        f"{field} -> {source}"\n        for field, source in matches.items()\n        if field in requirements and str(source) not in columns\n    ]\n    if invalid:\n        raise ValueError("Mapped source column no longer exists: " + ", ".join(invalid))\n\n    selected_sources = {str(source) for source in matches.values() if source}\n    rename: dict[str, str] = {}\n    for field, source in matches.items():\n        if field not in canonical:\n            continue\n        source = str(source)\n        target = str(canonical[field])\n        if target in frame.columns and source != target and target not in selected_sources:\n            frame = frame.rename(columns={target: f"Unmapped {target}"})\n        rename[source] = target\n    frame = frame.rename(columns=rename)\n\n    output = BytesIO()\n    normalized_name = name\n    content_type = str(getattr(uploaded_file, "type", "") or "")\n    if extension == ".csv":\n        frame.to_csv(output, index=False)\n        content_type = "text/csv"\n    else:\n        frame.to_excel(output, index=False)\n        if extension == ".xls":\n            normalized_name = str(Path(name).with_suffix(".xlsx"))\n        content_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"\n\n    mapped = _MappedUpload(output.getvalue())\n    mapped.name = normalized_name\n    mapped.type = content_type\n    mapped.source_name = name\n    mapped.column_mapping = dict(matches)\n    return mapped\n\n\ndef stage_uploaded_dataset('''
text = replace_once(text, file_bytes_block, helper_block, "mapped upload helper")

old_mapping_ui = '''    mapping_rows = [\n        {\n            "Required field": purpose,\n            "Detected column": inspection["matches"].get(purpose, "Not detected"),\n            "Status": "Matched" if purpose in inspection["matches"] else "Review",\n        }\n        for purpose in DATASET_REQUIREMENTS.get(selected_label, {})\n    ]\n    if mapping_rows:\n        st.dataframe(pd.DataFrame(mapping_rows), width="stretch", hide_index=True)\n    if inspection["missing"]:\n        st.warning(\n            "These fields were not detected automatically: "\n            + ", ".join(inspection["missing"])\n            + ". You can still publish the source and confirm the mapping in Buyer Operations."\n        )\n    with st.expander("Preview first 8 rows", expanded=not inspection["missing"]):\n        st.dataframe(inspection["preview"], width="stretch", hide_index=True)\n'''
new_mapping_ui = '''    requirements = DATASET_REQUIREMENTS.get(selected_label, {})\n    source_columns = list(dict.fromkeys(str(column) for column in inspection["preview"].columns))\n    file_token = hashlib.sha256(_file_bytes(uploaded)).hexdigest()[:12]\n    agent_state_key = f"data_hub_mapping_agent_{spec['dataset_key']}_{file_token}"\n    agent_result = st.session_state.get(agent_state_key)\n\n    if inspection["missing"]:\n        st.warning(\n            "These required fields were not detected automatically: "\n            + ", ".join(inspection["missing"])\n            + ". Use the Mapping Agent or choose the source columns manually before publishing."\n        )\n        if st.button(\n            "Ask Mapping Agent",\n            key=f"ask_mapping_agent_{spec['dataset_key']}_{file_token}",\n            type="secondary",\n        ):\n            agent_result = suggest_column_mapping(\n                source_columns,\n                requirements,\n                existing_matches=inspection["matches"],\n                dataset_label=selected_label,\n            )\n            st.session_state[agent_state_key] = agent_result\n            for proposal in agent_result.get("proposals", []):\n                field = str(proposal.get("required_field") or "")\n                source = str(proposal.get("source_column") or "")\n                selector_key = (\n                    f"data_hub_map_{spec['dataset_key']}_{file_token}_{_normalize_column(field).replace(' ', '_')}"\n                )\n                if field in requirements and source in source_columns:\n                    st.session_state[selector_key] = source\n\n    agent_by_field: dict[str, dict[str, Any]] = {}\n    if isinstance(agent_result, dict):\n        proposals = [dict(row) for row in agent_result.get("proposals", []) if isinstance(row, dict)]\n        agent_by_field = {str(row.get("required_field") or ""): row for row in proposals}\n        if proposals:\n            st.markdown("##### Mapping Agent suggestions")\n            st.dataframe(\n                pd.DataFrame(\n                    [\n                        {\n                            "Required field": row.get("required_field", ""),\n                            "Suggested column": row.get("source_column", ""),\n                            "Confidence": row.get("confidence", ""),\n                            "Why": row.get("reason", ""),\n                        }\n                        for row in proposals\n                    ]\n                ),\n                width="stretch",\n                hide_index=True,\n            )\n        st.caption(\n            str(\n                agent_result.get("privacy_note")\n                or "The mapping assistant evaluates headers only; row values are not sent to Gemini."\n            )\n        )\n\n    st.markdown("##### Confirm column mapping")\n    confirmed_matches: dict[str, str] = {}\n    for purpose in requirements:\n        options = ["Not mapped", *source_columns]\n        suggested = str(\n            inspection["matches"].get(purpose)\n            or agent_by_field.get(purpose, {}).get("source_column")\n            or "Not mapped"\n        )\n        selector_key = (\n            f"data_hub_map_{spec['dataset_key']}_{file_token}_{_normalize_column(purpose).replace(' ', '_')}"\n        )\n        if selector_key not in st.session_state:\n            st.session_state[selector_key] = suggested if suggested in options else "Not mapped"\n        selected = st.selectbox(\n            purpose,\n            options,\n            key=selector_key,\n            help="Choose the source column that represents this required Buyer Dashboard field.",\n        )\n        if selected != "Not mapped":\n            confirmed_matches[purpose] = selected\n\n    duplicate_mapping = len(set(confirmed_matches.values())) != len(confirmed_matches)\n    inspection["matches"] = confirmed_matches\n    inspection["missing"] = [purpose for purpose in requirements if purpose not in confirmed_matches]\n    inspection["quality"] = "Ready" if not inspection["missing"] and not duplicate_mapping else "Review mapping"\n    inspection["mapping_provider"] = (\n        str(agent_result.get("provider") or "manual") if isinstance(agent_result, dict) else "manual"\n    )\n    if duplicate_mapping:\n        st.error("One source column is assigned to more than one required field. Choose a unique column for each field.")\n    elif not inspection["missing"]:\n        st.success("Required fields are mapped and ready to normalize for Buyer Dashboard.")\n\n    with st.expander("Preview first 8 rows", expanded=bool(inspection["missing"])):\n        st.dataframe(inspection["preview"], width="stretch", hide_index=True)\n'''
text = replace_once(text, old_mapping_ui, new_mapping_ui, "interactive mapping UI")

text = replace_once(
    text,
    '''        disabled=not confirmed,\n        key=f"publish_{spec['widget_key']}",''',
    '''        disabled=not confirmed or bool(inspection["missing"]) or duplicate_mapping,\n        key=f"publish_{spec['widget_key']}",''',
    "publish mapping gate",
)

text = replace_once(
    text,
    '''            staged = stage_uploaded_dataset(\n                st.session_state,\n                uploaded,\n                cache_key=spec["cache_key"],\n                dataset_label=selected_label,\n            )\n            _publish_durable_source(spec, staged, inspection)''',
    '''            mapped_upload = build_mapped_upload(\n                uploaded,\n                selected_label,\n                inspection["matches"],\n            )\n            staged = stage_uploaded_dataset(\n                st.session_state,\n                mapped_upload,\n                cache_key=spec["cache_key"],\n                dataset_label=selected_label,\n            )\n            staged["source_name"] = inspection["name"]\n            staged["column_mapping"] = dict(inspection["matches"])\n            staged["mapping_provider"] = inspection.get("mapping_provider", "manual")\n            _publish_durable_source(spec, staged, inspection)''',
    "publish normalized mapping",
)

write_text(p, text, nl)

p, text, nl = read_text("tests/test_data_hub.py")
text = replace_once(
    text,
    '''    assert inspection["quality"] == "Review mapping"\n    assert inspection["missing"] == ["Units sold"]''',
    '''    assert inspection["quality"] == "Review mapping"\n    assert inspection["missing"] == ["Units sold", "Category"]''',
    "product sales required category test",
)
write_text(p, text, nl)

print("Data Hub mapping-agent patches applied successfully.")
