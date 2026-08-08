"""Phone-first Streamlit UI for resumable physical counts and reconciliation."""

from __future__ import annotations

from datetime import datetime
from io import BytesIO
import re

import pandas as pd
import streamlit as st

from modules.coman.db import ComanDatabaseConfigurationError, create_coman_engine
from modules.coman.repository import ComanRepository
from modules.inventory_audit.repository import InventoryAuditRepository
from modules.inventory_audit.workflow import EDITABLE_STATUSES, get_audit_events, set_audit_status

try:
    from streamlit_qrcode_scanner import qrcode_scanner
except ImportError:  # The rest of the audit remains usable with hardware/manual input.
    qrcode_scanner = None


@st.cache_resource
def _standalone_repositories(cache_version: str):
    del cache_version
    engine = create_coman_engine()
    return InventoryAuditRepository(engine), ComanRepository(engine)


def _actor() -> str:
    return str(st.session_state.get("admin_user") or st.session_state.get("user_user") or "system")


def _column_key(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value).casefold())


def _guess_column(columns, aliases: list[str]) -> str | None:
    keyed = {_column_key(column): str(column) for column in columns}
    for alias in aliases:
        if _column_key(alias) in keyed:
            return keyed[_column_key(alias)]
    return None


def _read_inventory_file(uploaded) -> pd.DataFrame:
    name = str(getattr(uploaded, "name", "")).casefold()
    if name.endswith(".csv"):
        return pd.read_csv(uploaded)
    return pd.read_excel(uploaded)


def _render_retail_snapshot_intake(
    repository: InventoryAuditRepository,
    organization_id: str,
    facility_id: str,
    *,
    expanded: bool = False,
) -> None:
    with st.expander("Load or refresh Dutchie retail inventory", expanded=expanded):
        st.caption(
            "Use Buyer Ops inventory already loaded in this session or upload a Dutchie CSV/XLSX export."
        )
        active = st.session_state.get("inv_raw_df")
        if not isinstance(active, pd.DataFrame) or active.empty:
            active = st.session_state.get("inv_df")
        has_active = isinstance(active, pd.DataFrame) and not active.empty
        choices = ["Upload Dutchie inventory export"]
        if has_active:
            choices.insert(0, "Use active Buyer Ops inventory")
        source = st.radio("Inventory source", choices, horizontal=True, key="retail_audit_snapshot_source")
        frame = active.copy() if source.startswith("Use active") and has_active else None
        reference = "Active Buyer Ops inventory"
        if source.startswith("Upload"):
            uploaded = st.file_uploader(
                "Dutchie inventory file", type=["csv", "xlsx", "xls"], key="retail_audit_inventory_upload"
            )
            if uploaded is not None:
                try:
                    frame = _read_inventory_file(uploaded)
                    reference = uploaded.name
                except Exception as exc:
                    st.error(f"The inventory file could not be read: {exc}")
                    return
        if not isinstance(frame, pd.DataFrame) or frame.empty:
            st.info("Choose current Buyer Ops inventory or upload a Dutchie inventory export to continue.")
            return

        columns = [str(column) for column in frame.columns]
        aliases = {
            "product_name": ["Product Name", "Item Name", "Name", "Product"],
            "quantity": ["Available", "Quantity", "Qty", "On Hand", "Quantity Available", "Inventory"],
            "sku": ["SKU", "Product SKU", "Item SKU"],
            "upc": ["UPC", "Barcode", "GTIN"],
            "external_product_id": ["Dutchie Product ID", "Product ID", "External Product ID"],
            "lot_code": ["Lot", "Lot Number", "Batch", "Batch ID"],
            "compliance_package_id": ["METRC Package ID", "Package ID", "Package Tag"],
            "external_inventory_id": ["Dutchie Inventory ID", "Inventory ID", "External Inventory ID"],
            "barcode_value": ["QR Code", "Barcode Value", "Label Code"],
            "location_code": ["Location", "Room", "Shelf", "Bin"],
            "unit": ["Unit", "UOM", "Unit of Measure"],
            "unit_cost": ["Unit Cost", "Cost", "Inventory Cost"],
            "retail_price": ["Retail Price", "Price", "Unit Price"],
        }
        product_guess = _guess_column(columns, aliases["product_name"]) or columns[0]
        quantity_guess = _guess_column(columns, aliases["quantity"]) or columns[0]
        left, right = st.columns(2)
        product_name = left.selectbox("Product name *", columns, index=columns.index(product_guess))
        quantity = right.selectbox("Quantity in stock *", columns, index=columns.index(quantity_guess))
        mapping = {"product_name": product_name, "quantity": quantity}
        optional = ["Not provided", *columns]
        for field, field_aliases in aliases.items():
            if field in mapping:
                continue
            guess = _guess_column(columns, field_aliases)
            mapping[field] = st.selectbox(
                field.replace("_", " ").title(),
                optional,
                index=optional.index(guess) if guess in optional else 0,
                key=f"retail_snapshot_map_{field}",
            )
        if st.button("Import durable retail snapshot", type="primary", width="stretch"):
            normalized_rows = []
            for _, source_row in frame.iterrows():
                target = {}
                for field, column in mapping.items():
                    value = "" if column == "Not provided" else source_row.get(column)
                    target[field] = "" if pd.isna(value) else value
                normalized_rows.append(target)
            try:
                result = repository.import_retail_snapshot(
                    organization_id,
                    facility_id,
                    rows=normalized_rows,
                    actor=_actor(),
                    reference=reference,
                )
            except Exception as exc:
                st.error(f"Retail inventory could not be imported: {exc}")
            else:
                st.success(
                    f"Imported {result['rows']} rows: {result['products_created']} products, "
                    f"{result['lots_created']} lots, {result['adjustments']} balance updates."
                )
                st.cache_resource.clear()
                st.rerun()


def _primary_code(lot, product) -> str:
    return str(
        getattr(lot, "barcode_value", "")
        or getattr(lot, "compliance_package_id", "")
        or getattr(lot, "external_inventory_id", "")
        or getattr(lot, "lot_code", "")
        or getattr(product, "upc", "")
        or getattr(product, "sku", "")
    )


def _line_rows(lines, products_by_id, lots_by_id) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for line in lines:
        lot = lots_by_id.get(line.lot_id)
        product = products_by_id.get(getattr(lot, "product_id", ""))
        rows.append(
            {
                "line_id": line.id,
                "Product Name": getattr(product, "name", "Unknown product"),
                "SKU / UPC": getattr(product, "upc", "") or getattr(product, "sku", ""),
                "Lot / Batch": getattr(lot, "lot_code", line.lot_id),
                "METRC Package": getattr(lot, "compliance_package_id", ""),
                "Location": getattr(lot, "location_code", "UNASSIGNED"),
                "Expected": float(line.expected_quantity),
                "First Count": line.first_count_quantity,
                "Recount": line.recount_quantity,
                "Final Count": line.counted_quantity,
                "Variance": float(line.variance_quantity),
                "Unit": line.unit,
                "Reason": line.reason,
                "Notes": line.notes,
                "Counted By": line.counted_by,
                "Unit Cost": float(getattr(product, "unit_cost", 0.0) or 0.0),
                "Retail Price": float(getattr(product, "retail_price", 0.0) or 0.0),
            }
        )
    return rows


def _report_frame(rows: list[dict[str, object]]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame()
    frame = pd.DataFrame(rows).drop(columns=["line_id"], errors="ignore")
    frame["Cost Impact"] = frame["Variance"] * frame["Unit Cost"]
    frame["Revenue Impact"] = frame["Variance"] * frame["Retail Price"]
    frame["Scan Status"] = frame["Final Count"].apply(lambda value: "Scanned" if pd.notna(value) else "Not scanned")
    return frame


def _excel_report_bytes(audit, report: pd.DataFrame, events) -> bytes:
    output = BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        pd.DataFrame(
            [
                {
                    "Audit": audit.audit_number,
                    "Status": audit.status,
                    "Scope": audit.scope_label,
                    "Started": audit.started_at,
                    "Created By": audit.created_by,
                    "Generated": datetime.now().astimezone(),
                }
            ]
        ).to_excel(writer, sheet_name="Summary", index=False)
        report.to_excel(writer, sheet_name="Audit Detail", index=False)
        pd.DataFrame(
            [
                {
                    "Action": event.action,
                    "Actor": event.actor,
                    "Time": event.created_at,
                    "Changes": event.changes_json,
                }
                for event in events
            ]
        ).to_excel(writer, sheet_name="Activity", index=False)
    return output.getvalue()


def _audit_progress(lines) -> tuple[int, int, int]:
    scanned = sum(line.first_count_quantity is not None for line in lines)
    recounts = sum(bool(line.recount_required) for line in lines)
    return scanned, len(lines), recounts


def _queue_count_dialog(
    repository: InventoryAuditRepository,
    organization_id: str,
    facility_id: str,
    audit,
    *,
    raw_code: str,
    recount: bool,
    pending_key: str,
    error_key: str,
) -> None:
    try:
        line = repository.preview_scanned_item(
            organization_id,
            facility_id,
            audit.id,
            raw_code=raw_code,
            actor=_actor(),
            recount=recount,
        )
    except Exception as exc:
        st.session_state[error_key] = str(exc)
    else:
        st.session_state[pending_key] = {"line_id": line.id, "raw_code": str(raw_code).strip()}
    st.rerun()


@st.dialog("Enter inventory count", width="small")
def _scan_count_dialog(
    repository: InventoryAuditRepository,
    organization_id: str,
    facility_id: str,
    audit,
    *,
    pending: dict[str, str],
    recount: bool,
    pending_key: str,
    lots_by_id,
    products_by_id,
) -> None:
    line = next((item for item in repository.list_lines(organization_id, audit.id) if item.id == pending.get("line_id")), None)
    if line is None:
        st.error("That audit item is no longer available.")
        if st.button("Close and rescan", width="stretch"):
            st.session_state.pop(pending_key, None)
            st.rerun()
        return
    lot = lots_by_id.get(line.lot_id)
    product = products_by_id.get(getattr(lot, "product_id", ""))
    product_name = getattr(product, "name", "Unknown product")
    st.markdown(f"### {product_name}")
    st.caption(f"{getattr(lot, 'lot_code', '')} · {getattr(lot, 'location_code', 'UNASSIGNED')}")
    if recount or not audit.blind_count:
        st.metric("Expected quantity", f"{float(line.expected_quantity):,.3f} {line.unit}")
    else:
        st.info("Blind count is active. Expected inventory stays hidden during the first pass.")
    with st.form(f"scan_count_dialog_{audit.id}_{line.id}_{'recount' if recount else 'first'}"):
        quantity = st.number_input("Physical quantity in stock", min_value=0.0, step=1.0, format="%.3f")
        reason = st.selectbox(
            "Variance reason",
            ["", "Count correction", "Damage", "Waste", "Return", "Transfer timing", "Receiving timing", "Unknown"],
        )
        notes = st.text_input("Count note (optional)")
        save, cancel = st.columns(2)
        save_clicked = save.form_submit_button("Save & scan next", type="primary", width="stretch")
        cancel_clicked = cancel.form_submit_button("Cancel", width="stretch")
    if cancel_clicked:
        st.session_state.pop(pending_key, None)
        st.rerun()
    if save_clicked:
        try:
            repository.record_scanned_count(
                organization_id,
                facility_id,
                audit.id,
                raw_code=pending.get("raw_code", ""),
                quantity=quantity,
                actor=_actor(),
                recount=recount,
                reason=reason,
                notes=notes,
            )
        except Exception as exc:
            st.error(f"Count was not saved: {exc}")
        else:
            st.session_state.pop(pending_key, None)
            st.toast(f"Saved {quantity:,.3f} {line.unit} for {product_name}.", icon="✅")
            st.rerun()


def _live_count_form(
    repository: InventoryAuditRepository,
    organization_id: str,
    facility_id: str,
    audit,
    *,
    recount: bool,
    lots_by_id,
    products_by_id,
) -> None:
    stage = "recount" if recount else "first"
    pending_key = f"audit_pending_scan_{stage}_{audit.id}"
    error_key = f"audit_scanner_error_{stage}_{audit.id}"
    camera_value_key = f"audit_last_camera_value_{stage}_{audit.id}"
    st.markdown("### Recount scanner" if recount else "### Scan and count")
    st.caption("Camera, Bluetooth/USB scanner, typed code, and manual product selection all remain available.")

    pending = st.session_state.get(pending_key)
    if pending:
        _scan_count_dialog(
            repository,
            organization_id,
            facility_id,
            audit,
            pending=pending,
            recount=recount,
            pending_key=pending_key,
            lots_by_id=lots_by_id,
            products_by_id=products_by_id,
        )

    scan_error = st.session_state.pop(error_key, None)
    if scan_error:
        st.error(scan_error)
    if qrcode_scanner is None:
        st.warning("Live camera scanning is unavailable. Use a Bluetooth/USB scanner or manual lookup below.")
    else:
        # Keep this key stable and keep the component rendered while the count
        # dialog is open. Remounting the browser camera can cause mobile Safari
        # or Chrome to request permission again after every scan.
        scanned_code = qrcode_scanner(key=f"live_audit_scanner_{stage}_{audit.id}")
        if not pending:
            if not scanned_code:
                st.session_state.pop(camera_value_key, None)
            elif st.session_state.get(camera_value_key) != str(scanned_code):
                st.session_state[camera_value_key] = str(scanned_code)
                _queue_count_dialog(
                    repository,
                    organization_id,
                    facility_id,
                    audit,
                    raw_code=str(scanned_code),
                    recount=recount,
                    pending_key=pending_key,
                    error_key=error_key,
                )
    with st.expander("Bluetooth / USB scanner or typed code", expanded=qrcode_scanner is None):
        with st.form(f"audit_code_lookup_{stage}_{audit.id}", clear_on_submit=True):
            scan_code = st.text_input("Scan or enter item code", placeholder="Dutchie ID, UPC, SKU, lot, or METRC package ID")
            if st.form_submit_button("Find item", type="primary", width="stretch", disabled=bool(pending)):
                _queue_count_dialog(
                    repository,
                    organization_id,
                    facility_id,
                    audit,
                    raw_code=scan_code,
                    recount=recount,
                    pending_key=pending_key,
                    error_key=error_key,
                )
    with st.expander("Cannot scan? Choose the inventory item", expanded=False):
        eligible = []
        for line in repository.list_lines(organization_id, audit.id):
            if recount and not line.recount_required:
                continue
            if not recount and line.first_count_quantity is not None:
                continue
            lot = lots_by_id.get(line.lot_id)
            product = products_by_id.get(getattr(lot, "product_id", ""))
            eligible.append((line, lot, product))
        if not eligible:
            st.success("No items remain in this count stage.")
            return
        selection = st.selectbox(
            "Inventory item",
            options=[line.id for line, _, _ in eligible],
            format_func=lambda line_id: next(
                f"{getattr(product, 'name', 'Unknown')} · {getattr(lot, 'lot_code', '')} · {getattr(lot, 'location_code', '')}"
                for line, lot, product in eligible
                if line.id == line_id
            ),
            key=f"audit_manual_line_{stage}_{audit.id}",
            disabled=bool(pending),
        )
        if st.button(
            "Enter count for selected item",
            key=f"audit_manual_open_{stage}_{audit.id}",
            width="stretch",
            disabled=bool(pending),
        ):
            line, lot, product = next(item for item in eligible if item[0].id == selection)
            st.session_state[pending_key] = {"line_id": line.id, "raw_code": _primary_code(lot, product)}
            st.rerun()


def _create_audit_form(
    repository,
    organization_id: str,
    facility_id: str,
    lots,
    products_by_id,
    audits,
    operation_type: str,
) -> None:
    retail = operation_type == "retail"
    lot_options = {
        lot.id: f"{getattr(products_by_id.get(lot.product_id), 'name', 'Unknown')} · {lot.lot_code} · {lot.location_code}"
        for lot in lots
    }
    if not lots:
        st.info("Load inventory for this facility before starting an audit.")
        return
    with st.form(f"inventory_audit_create_{operation_type}"):
        prefix = "RTL" if retail else "PROD"
        generated = f"{prefix}-{datetime.now():%Y%m%d-%H%M%S}"
        left, right = st.columns(2)
        audit_number = left.text_input("Audit name / number", value=generated)
        scope = right.text_input("Scope", value="Full store" if retail else "Full facility")
        selected_lots = st.multiselect(
            "Inventory to count",
            options=list(lot_options),
            default=list(lot_options),
            format_func=lambda lot_id: lot_options[lot_id],
        )
        settings_left, settings_right = st.columns(2)
        blind_count = settings_left.checkbox("Blind first count", value=True)
        tolerance = settings_right.number_input("Recount tolerance", min_value=0.0, value=0.0, step=0.1)
        notes = st.text_area("Notes (optional)", height=70)
        submitted = st.form_submit_button("Start New Audit", type="primary", width="stretch")
    if submitted:
        try:
            audit = repository.create_audit(
                organization_id,
                facility_id,
                audit_number=audit_number,
                actor=_actor(),
                scope_label=scope,
                notes=notes,
                lot_ids=selected_lots,
                operation_type=operation_type,
                blind_count=blind_count,
                recount_tolerance=tolerance,
            )
            set_audit_status(
                repository,
                organization_id,
                facility_id,
                audit.id,
                status="in_progress",
                actor=_actor(),
            )
        except Exception as exc:
            st.error(f"We couldn’t start the audit. Nothing was opened: {exc}")
        else:
            st.session_state[f"current_audit_id_{operation_type}"] = audit.id
            st.success("Audit started. You can leave it, start another, and return later.")
            st.rerun()


def _render_audit_dashboard(repository, organization_id, facility_id, audits, products_by_id, lots_by_id, operation_type):
    st.markdown("### Audit Dashboard")
    if not audits:
        st.info("No audit history yet. Start the first audit above.")
        return None
    groups = [
        ("Active", {"in_progress", "draft"}),
        ("Paused", {"paused"}),
        ("Stopped", {"stopped"}),
        ("Completed", {"completed"}),
        ("Cancelled", {"cancelled"}),
    ]
    current_key = f"current_audit_id_{operation_type}"
    selected = st.session_state.get(current_key)
    for heading, statuses in groups:
        group = [audit for audit in audits if audit.status in statuses]
        if not group:
            continue
        st.markdown(f"#### {heading} Audits")
        for audit in group:
            lines = repository.list_lines(organization_id, audit.id)
            scanned, total, recounts = _audit_progress(lines)
            completion = (scanned / max(total, 1)) * 100
            with st.container(border=True):
                top, action = st.columns([4, 1])
                top.markdown(f"**{audit.audit_number}**  \n{audit.scope_label} · {audit.status.replace('_', ' ').title()}")
                top.caption(f"{scanned}/{total} scanned · {completion:.0f}% · {recounts} recount(s) waiting · Started by {audit.created_by}")
                if audit.status == "in_progress":
                    label = "Open"
                elif audit.status in {"paused", "draft"}:
                    label = "Resume"
                else:
                    label = "Review"
                if action.button(label, key=f"open_audit_{audit.id}", width="stretch"):
                    if audit.status in {"paused", "draft"}:
                        set_audit_status(
                            repository,
                            organization_id,
                            facility_id,
                            audit.id,
                            status="in_progress",
                            actor=_actor(),
                        )
                    st.session_state[current_key] = audit.id
                    st.rerun()
                if selected == audit.id:
                    st.caption("Currently open")
    return selected


def _render_report_tools(repository, organization_id: str, audit, rows) -> None:
    report = _report_frame(rows)
    events = get_audit_events(repository, organization_id, audit.id)
    st.markdown("### Audit Report")
    status_label = "Partial" if audit.status in EDITABLE_STATUSES else audit.status.replace("_", " ").title()
    st.info(f"Report status: **{status_label}**. Unscanned items remain visible and are not presented as completed counts.")
    if report.empty:
        st.info("No audit detail is available yet.")
        return
    st.dataframe(report, hide_index=True, width="stretch")
    c1, c2 = st.columns(2)
    c1.download_button(
        "Export CSV",
        data=report.to_csv(index=False).encode("utf-8"),
        file_name=f"inventory_audit_{audit.audit_number}_{audit.status}.csv",
        mime="text/csv",
        width="stretch",
    )
    c2.download_button(
        "Export Excel",
        data=_excel_report_bytes(audit, report, events),
        file_name=f"inventory_audit_{audit.audit_number}_{audit.status}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        width="stretch",
    )
    with st.expander("Activity log", expanded=False):
        st.dataframe(
            pd.DataFrame(
                [
                    {"Action": event.action, "Actor": event.actor, "Time": event.created_at, "Changes": event.changes_json}
                    for event in events
                ]
            ),
            hide_index=True,
            width="stretch",
        )


def _render_open_audit(repository, organization_id, facility_id, audit, products_by_id, lots_by_id, operation_type):
    current_key = f"current_audit_id_{operation_type}"
    lines = repository.list_lines(organization_id, audit.id)
    rows = _line_rows(lines, products_by_id, lots_by_id)
    scanned, total, recounts = _audit_progress(lines)
    pending = total - scanned
    scans = repository.list_scans(organization_id, audit.id)
    exceptions = [scan for scan in scans if scan.match_status != "matched"]

    st.divider()
    st.markdown(f"## {audit.audit_number}")
    st.caption(f"Audit ID: {audit.id} · {audit.scope_label} · {audit.status.replace('_', ' ').title()}")
    metrics = st.columns(4)
    metrics[0].metric("Products scanned", f"{scanned}/{total}")
    metrics[1].metric("Remaining", pending)
    metrics[2].metric("Recounts", recounts)
    metrics[3].metric("Scan exceptions", len(exceptions))

    nav1, nav2, nav3, nav4 = st.columns(4)
    if nav1.button("Back to Dashboard", width="stretch"):
        st.session_state.pop(current_key, None)
        st.rerun()
    if audit.status in EDITABLE_STATUSES and nav2.button("Pause Audit", width="stretch"):
        set_audit_status(repository, organization_id, facility_id, audit.id, status="paused", actor=_actor())
        st.session_state.pop(current_key, None)
        st.rerun()
    if audit.status in EDITABLE_STATUSES and nav3.button("Stop & Review", width="stretch"):
        set_audit_status(repository, organization_id, facility_id, audit.id, status="stopped", actor=_actor())
        st.session_state[current_key] = audit.id
        st.rerun()
    show_report = nav4.button("Generate Current Report", width="stretch")

    if audit.status in EDITABLE_STATUSES:
        if pending:
            st.info(f"First pass in progress: {pending} item(s) remain. You can pause or stop at any time.")
            _live_count_form(
                repository,
                organization_id,
                facility_id,
                audit,
                recount=False,
                lots_by_id=lots_by_id,
                products_by_id=products_by_id,
            )
        elif recounts:
            st.warning(f"First pass complete. {recounts} item(s) require recount.")
            _live_count_form(
                repository,
                organization_id,
                facility_id,
                audit,
                recount=True,
                lots_by_id=lots_by_id,
                products_by_id=products_by_id,
            )
        else:
            st.success("The intended count scope is fully counted and ready for completion.")
            confirm = st.checkbox(
                "I reviewed the count and confirm the intended audit scope is complete",
                key=f"audit_confirm_{audit.id}",
            )
            post_adjustments = st.checkbox(
                "Post approved corrections to the append-only inventory ledger",
                value=True,
                key=f"audit_post_{audit.id}",
            )
            if st.button("Complete Audit", type="primary", disabled=not confirm, width="stretch"):
                try:
                    repository.complete_audit(
                        organization_id,
                        facility_id,
                        audit.id,
                        actor=_actor(),
                        post_adjustments=post_adjustments,
                    )
                except Exception as exc:
                    st.error(f"Unable to complete the audit: {exc}")
                else:
                    st.success("Audit completed.")
                    st.rerun()
    elif audit.status == "stopped":
        st.warning("This audit was stopped before completion. Its current results are preserved.")
        if st.button("Reopen Audit", type="primary", width="stretch"):
            set_audit_status(repository, organization_id, facility_id, audit.id, status="in_progress", actor=_actor())
            st.rerun()
    elif audit.status == "paused":
        if st.button("Resume Audit", type="primary", width="stretch"):
            set_audit_status(repository, organization_id, facility_id, audit.id, status="in_progress", actor=_actor())
            st.rerun()
    elif audit.status == "completed":
        st.success("This audit is completed and preserved as historical record.")
    else:
        st.info(f"Audit status: {audit.status.replace('_', ' ').title()}")

    if exceptions:
        with st.expander(f"Scan exceptions ({len(exceptions)})", expanded=False):
            st.dataframe(
                pd.DataFrame(
                    [
                        {
                            "Scanned Code": scan.raw_code,
                            "Result": scan.match_status.title(),
                            "Stage": scan.scan_stage.replace("_", " ").title(),
                            "Scanned By": scan.scanned_by,
                            "Time": scan.scanned_at,
                        }
                        for scan in exceptions
                    ]
                ),
                hide_index=True,
                width="stretch",
            )

    if show_report or audit.status in {"stopped", "completed", "cancelled"}:
        _render_report_tools(repository, organization_id, audit, rows)


def render_inventory_audits(
    repository: InventoryAuditRepository,
    organization_id: str,
    facility_id: str,
    products,
    lots,
    *,
    operation_type: str = "production",
) -> None:
    """Render independent audit sessions with pause, stop, resume, scan, and reporting."""

    retail = operation_type == "retail"
    st.subheader("Retail Scan Audit" if retail else "Inventory Audit & Reconciliation")
    st.caption(
        "Each audit is an independent saved workspace. Start another audit at any time, pause one, return later, or stop and report on partial work."
    )
    audits = repository.list_audits(organization_id, facility_id, operation_type)
    products_by_id = {product.id: product for product in products}
    lots_by_id = {lot.id: lot for lot in lots}

    with st.expander("Start New Audit", expanded=not audits):
        _create_audit_form(
            repository,
            organization_id,
            facility_id,
            lots,
            products_by_id,
            audits,
            operation_type,
        )

    current_id = _render_audit_dashboard(
        repository,
        organization_id,
        facility_id,
        audits,
        products_by_id,
        lots_by_id,
        operation_type,
    )
    if not current_id:
        return
    audit_by_id = {audit.id: audit for audit in repository.list_audits(organization_id, facility_id, operation_type)}
    audit = audit_by_id.get(current_id)
    if audit is None:
        st.session_state.pop(f"current_audit_id_{operation_type}", None)
        st.rerun()
    _render_open_audit(
        repository,
        organization_id,
        facility_id,
        audit,
        products_by_id,
        lots_by_id,
        operation_type,
    )


def render_inventory_audit_workspace(operation_type: str = "retail") -> None:
    """Standalone entry point used by Retail Ops."""

    organization_id = st.session_state.get("active_organization_id")
    facility_id = st.session_state.get("active_facility_id")
    if not organization_id or not facility_id:
        st.warning("Select an organization and facility before opening Inventory Counts.")
        return
    try:
        audits, coman = _standalone_repositories("inventory-audits-session-v2")
        products = coman.list_products(organization_id)
        lots = coman.list_inventory_lots(organization_id, facility_id)
        if operation_type == "retail":
            _render_retail_snapshot_intake(audits, organization_id, facility_id, expanded=not lots)
            products = coman.list_products(organization_id)
            lots = coman.list_inventory_lots(organization_id, facility_id)
        render_inventory_audits(
            audits,
            organization_id,
            facility_id,
            products,
            lots,
            operation_type=operation_type,
        )
    except ComanDatabaseConfigurationError:
        st.error("Supabase is not configured. Add COMAN_DATABASE_URL to the Streamlit app secrets.")
    except Exception as exc:
        message = str(exc)
        if "inventory_audits" in message or "ck_inventory_audit_status" in message:
            st.error("Inventory Counts needs database migration 0015 before resumable audits can load.")
            st.code("migrations/versions/0015_inventory_audit_lifecycle.sql")
        else:
            st.error(f"Inventory Counts could not load: {exc}")
