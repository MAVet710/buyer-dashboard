from pathlib import Path

path = Path("modules/inventory_command_center.py")
text = path.read_text(encoding="utf-8")

replacements = [
    (
        '    normalized["Package ID"] = _text(source, PACKAGE_ALIASES)\n',
        '    normalized["Package ID"] = _text(source, PACKAGE_ALIASES)\n    normalized["External Package ID"] = normalized["Package ID"]\n',
    ),
    (
        '        normalized["Package ID"] = ""\n        normalized["Durable Lot ID"] = ""\n',
        '        normalized["Package ID"] = ""\n        normalized["External Package ID"] = ""\n        normalized["Durable Lot ID"] = ""\n',
    ),
    (
        '                "Package ID": lot.compliance_package_id or lot.lot_code,\n',
        '                "Package ID": lot.compliance_package_id or lot.lot_code,\n                "External Package ID": lot.compliance_package_id or lot.lot_code,\n',
    ),
    (
        '            for column in ("SKU", "Product", "Strain", "Package ID", "Vendor", "Room", "Category", "Tags")\n',
        '            for column in ("SKU", "Product", "Strain", "External Package ID", "Package ID", "Vendor", "Room", "Category", "Tags")\n',
    ),
    (
        'def _open_receive_inventory(state: MutableMapping[str, Any]) -> None:\n    state["inventory_receive_open"] = True\n    st.rerun()\n\n\ndef _add_products_to_po',
        '''def _open_receive_inventory(state: MutableMapping[str, Any]) -> None:\n    state["inventory_receive_open"] = True\n    st.rerun()\n\n\ndef _package_rows_for_selected(\n    state: MutableMapping[str, Any],\n    selected: pd.DataFrame,\n    *,\n    is_production: bool,\n    grain: str,\n) -> pd.DataFrame:\n    if selected is None or selected.empty:\n        return pd.DataFrame()\n    if is_production or str(grain).casefold() == "packages":\n        return selected.copy()\n    packages = build_retail_inventory_table(state, grain="Packages")\n    if packages.empty:\n        return pd.DataFrame()\n    product_keys = {_norm(value) for value in selected.get("Product", pd.Series(dtype=str)).tolist() if _norm(value)}\n    if not product_keys:\n        return pd.DataFrame()\n    return packages[packages["Product"].map(_norm).isin(product_keys)].reset_index(drop=True)\n\n\ndef _add_products_to_po''',
    ),
    (
        '        ["SKU", "Product", "Package ID", "Category", "Room", "Available", "Unit", "Status", "Attention"]\n',
        '        ["SKU", "Product", "External Package ID", "Category", "Room", "Available", "Unit", "Status", "Attention"]\n',
    ),
    (
        '            else ["SKU", "Product", "Package ID", "Strain", "Vendor", "Room", "Available", "Unit", "Reserved", "30d Sold", "DOH", "Category", "Status", "Attention"]\n',
        '            else ["SKU", "Product", "External Package ID", "Strain", "Vendor", "Room", "Available", "Unit", "Reserved", "30d Sold", "DOH", "Category", "Status", "Attention"]\n',
    ),
]

for old, new in replacements:
    if old not in text:
        raise SystemExit(f"Expected inventory command-center snippet not found: {old[:100]!r}")
    text = text.replace(old, new, 1)

old_selection = '''    if not selected.empty:\n        with st.container(key="inv2_selection_bar"):\n            st.caption(f"{len(selected)} selected")\n            cols = st.columns([1.1, 1.1, 1.1, 1.1, 1.3])\n            products = [str(value) for value in selected["Product"].dropna().tolist() if str(value).strip()]\n            if len(selected) == 1 and cols[0].button(\n                "Product 360", type="primary", width="stretch", key="inv2_open_product"\n            ):\n                _open_product(state, products[0])\n            if cols[1].button("Audit", width="stretch", key="inv2_audit_selected"):\n                _route_audit(state, list(dict.fromkeys(products)))\n            if not is_production and cols[2].button("Add to PO", width="stretch", key="inv2_add_po"):\n                if _add_products_to_po(state, products):\n                    st.rerun()\n            durable_ids = [\n                str(value)\n                for value in selected.get("Durable Lot ID", pd.Series(dtype=str)).dropna().tolist()\n                if str(value).strip()\n            ]\n            studio_disabled = len(selected) != 1 or not durable_ids\n            if cols[3].button(\n                "Work on package",\n                width="stretch",\n                key="inv2_work_package",\n                disabled=studio_disabled,\n            ):\n                state["package_studio_prefill_lot_id"] = durable_ids[0]\n                state["package_studio_prefill_action"] = "Pack Down"\n                state["package_studio_open"] = True\n                st.rerun()\n            cols[4].download_button(\n                "Export selected",\n                data=selected[display_columns].to_csv(index=False).encode("utf-8"),\n                file_name="buyer_dash_inventory_selected.csv",\n                mime="text/csv",\n                width="stretch",\n            )\n'''

new_selection = '''    if state.pop("inventory_adjustment_flash", ""):\n        st.success(state.get("inventory_adjustment_flash_last") or "Inventory adjustment posted.")\n\n    if not selected.empty:\n        with st.container(key="inv2_selection_bar"):\n            st.caption(f"{len(selected)} selected")\n            cols = st.columns([1.0, 1.0, 1.0, 1.15, 1.0, 1.0, 1.15])\n            products = [str(value) for value in selected["Product"].dropna().tolist() if str(value).strip()]\n            package_rows = _package_rows_for_selected(\n                state, selected, is_production=is_production, grain=grain\n            )\n            if len(selected) == 1 and cols[0].button(\n                "Product 360", type="primary", width="stretch", key="inv2_open_product"\n            ):\n                _open_product(state, products[0])\n            if cols[1].button("Audit", width="stretch", key="inv2_audit_selected"):\n                _route_audit(state, list(dict.fromkeys(products)))\n            if not is_production and cols[2].button("Add to PO", width="stretch", key="inv2_add_po"):\n                if _add_products_to_po(state, products):\n                    st.rerun()\n            durable_ids = [\n                str(value)\n                for value in selected.get("Durable Lot ID", pd.Series(dtype=str)).dropna().tolist()\n                if str(value).strip()\n            ]\n            studio_disabled = len(selected) != 1 or not durable_ids\n            if cols[3].button(\n                "Work on package",\n                width="stretch",\n                key="inv2_work_package",\n                disabled=studio_disabled,\n            ):\n                state["package_studio_prefill_lot_id"] = durable_ids[0]\n                state["package_studio_prefill_action"] = "Pack Down"\n                state["package_studio_open"] = True\n                st.rerun()\n            external_ids = (\n                package_rows.get("External Package ID", pd.Series(dtype=str)).fillna("").astype(str).str.strip()\n                if not package_rows.empty\n                else pd.Series(dtype=str)\n            )\n            print_disabled = package_rows.empty or not external_ids.ne("").any()\n            if cols[4].button(\n                "Print labels", width="stretch", key="inv2_print_labels", disabled=print_disabled\n            ):\n                from modules.inventory_labels import open_inventory_label_dialog\n\n                if open_inventory_label_dialog(state, package_rows):\n                    st.rerun()\n            try:\n                from modules.inventory_adjustments import can_adjust_inventory\n\n                adjust_allowed = can_adjust_inventory(state)\n            except Exception:\n                adjust_allowed = False\n            if cols[5].button(\n                "Adjust",\n                width="stretch",\n                key="inv2_adjust_inventory",\n                disabled=print_disabled or not adjust_allowed,\n            ):\n                from modules.inventory_adjustments import open_inventory_adjustment_dialog\n\n                if open_inventory_adjustment_dialog(state, package_rows, operation_mode=operation_mode):\n                    st.rerun()\n            cols[6].download_button(\n                "Export selected",\n                data=selected[display_columns].to_csv(index=False).encode("utf-8"),\n                file_name="buyer_dash_inventory_selected.csv",\n                mime="text/csv",\n                width="stretch",\n            )\n'''

if old_selection not in text:
    raise SystemExit("Expected selected-row action block was not found")
text = text.replace(old_selection, new_selection, 1)

old_dialogs = '''    if bool(state.get("package_studio_open", False)):\n        from modules.package_studio.ui import render_package_studio_dialog\n\n        render_package_studio_dialog(state)\n'''
new_dialogs = '''    if bool(state.get("package_studio_open", False)):\n        from modules.package_studio.ui import render_package_studio_dialog\n\n        render_package_studio_dialog(state)\n    if bool(state.get("inventory_label_open", False)):\n        from modules.inventory_labels import render_inventory_label_dialog\n\n        render_inventory_label_dialog(state)\n    if bool(state.get("inventory_adjustment_open", False)):\n        from modules.inventory_adjustments import render_inventory_adjustment_dialog\n\n        render_inventory_adjustment_dialog(state)\n'''
if old_dialogs not in text:
    raise SystemExit("Expected dialog tail was not found")
text = text.replace(old_dialogs, new_dialogs, 1)

# Fix flash handling to preserve the exact success message through the rerun.
text = text.replace(
    '    if state.pop("inventory_adjustment_flash", ""):\n        st.success(state.get("inventory_adjustment_flash_last") or "Inventory adjustment posted.")\n',
    '    adjustment_flash = state.pop("inventory_adjustment_flash", "")\n    if adjustment_flash:\n        st.success(str(adjustment_flash))\n',
    1,
)

path.write_text(text, encoding="utf-8")
