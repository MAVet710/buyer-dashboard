"""Phone-first Streamlit UI for physical counts and reconciliation."""

from __future__ import annotations

from datetime import date
from io import BytesIO
import re

import pandas as pd
import streamlit as st

from modules.coman.db import ComanDatabaseConfigurationError, create_coman_engine
from modules.coman.repository import ComanRepository
from modules.inventory_audit.repository import InventoryAuditRepository


@st.cache_resource
def _standalone_repositories(cache_version: str):
    del cache_version
    engine = create_coman_engine()
    return InventoryAuditRepository(engine), ComanRepository(engine)


def _actor() -> str:
    return str(st.session_state.get("admin_user") or st.session_state.get("user_user") or "system")


def _decode_camera_label(photo) -> tuple[str, str]:
    if photo is None:
        return "", ""
    try:
        from PIL import Image
        import zxingcpp

        result = zxingcpp.read_barcode(Image.open(BytesIO(photo.getvalue())))
    except ImportError:
        return "", "Camera decoding is unavailable until the barcode-scanner dependency is installed."
    except Exception as exc:
        return "", f"The image could not be decoded: {exc}"
    if not result:
        return "", "No QR code or barcode was detected. Move closer, avoid glare, and try again."
    return str(result.text).strip(), ""


def _column_key(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value).casefold())


def _guess_column(columns, aliases: list[str]) -> str | None:
    keyed = {_column_key(column): str(column) for column in columns}
    for alias in aliases:
        if _column_key(alias) in keyed:
            return keyed[_column_key(alias)]
    for alias in aliases:
        target = _column_key(alias)
        for key, original in keyed.items():
            if target and (target in key or key in target):
                return original
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
) -> None:
    with st.expander("Load or refresh Dutchie retail inventory", expanded=False):
        st.caption(
            "Use the active Buyer Ops inventory or upload a Dutchie CSV/XLSX export. The importer preserves an append-only synchronization trail."
        )
        active = st.session_state.get("inv_raw_df")
        if not isinstance(active, pd.DataFrame) or active.empty:
            active = st.session_state.get("inv_df")
        has_active = isinstance(active, pd.DataFrame) and not active.empty
        sources = ["Upload Dutchie inventory export"]
        if has_active:
            sources.insert(0, "Use active Buyer Ops inventory")
        source = st.radio("Inventory source", sources, horizontal=True, key="retail_audit_snapshot_source")
        frame = active.copy() if source.startswith("Use active") and has_active else None
        reference = "Active Buyer Ops inventory"
        if source.startswith("Upload"):
            uploaded = st.file_uploader(
                "Dutchie inventory file",
                type=["csv", "xlsx", "xls"],
                key="retail_audit_inventory_upload",
            )
            if uploaded is not None:
                try:
                    frame = _read_inventory_file(uploaded)
                    reference = uploaded.name
                except Exception as exc:
                    st.error(f"The inventory file could not be read: {exc}")
                    frame = None
        if not isinstance(frame, pd.DataFrame) or frame.empty:
            st.info("Choose the current Buyer Ops inventory or upload a Dutchie inventory export to continue.")
            return
        st.dataframe(frame.head(8), hide_index=True, width="stretch")
        columns = [str(column) for column in frame.columns]
        optional = ["Not provided", *columns]
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

        def choose(label: str, field: str, required: bool = False):
            guess = _guess_column(columns, aliases[field])
            choices = columns if required else optional
            default = guess if guess in choices else choices[0]
            return st.selectbox(
                label,
                choices,
                index=choices.index(default),
                key=f"retail_snapshot_map_{field}",
            )

        st.markdown("**Confirm column mapping**")
        required_left, required_right = st.columns(2)
        product_name = required_left.selectbox(
            "Product name *",
            columns,
            index=columns.index(_guess_column(columns, aliases["product_name"]) or columns[0]),
            key="retail_snapshot_map_product_name",
        )
        quantity_guess = _guess_column(columns, aliases["quantity"])
        quantity = required_right.selectbox(
            "Quantity in stock *",
            columns,
            index=columns.index(quantity_guess or columns[0]),
            key="retail_snapshot_map_quantity",
        )
        mapping = {"product_name": product_name, "quantity": quantity}
        mapping_labels = [
            ("SKU", "sku"),
            ("UPC / barcode", "upc"),
            ("Dutchie product ID", "external_product_id"),
            ("Lot / batch", "lot_code"),
            ("METRC package ID", "compliance_package_id"),
            ("Dutchie inventory ID", "external_inventory_id"),
            ("QR / label value", "barcode_value"),
            ("Location / shelf", "location_code"),
            ("Unit of measure", "unit"),
            ("Unit cost", "unit_cost"),
            ("Retail price", "retail_price"),
        ]
        for index in range(0, len(mapping_labels), 2):
            cols = st.columns(2)
            for offset, (label, field) in enumerate(mapping_labels[index:index + 2]):
                with cols[offset]:
                    mapping[field] = choose(label, field)
        if st.button("Import durable retail snapshot", type="primary", width="stretch"):
            normalized_rows = []
            for _, source_row in frame.iterrows():
                target = {}
                for field, column in mapping.items():
                    if column == "Not provided":
                        target[field] = ""
                    else:
                        value = source_row.get(column)
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
                    f"Imported {result['rows']} rows: {result['products_created']} new products, "
                    f"{result['lots_created']} new lots, and {result['adjustments']} ledger updates."
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


def _count_form(
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
    title = "Recount scanner" if recount else "Scan and count"
    st.markdown(f"### {title}")
    st.caption(
        "Use a phone camera or place the cursor in the code field and scan with a USB/Bluetooth scanner."
    )
    decoded = ""
    with st.expander("Use phone or tablet camera", expanded=False):
        st.caption(
            "Allow camera access when prompted. On mobile devices, switch to the rear camera "
            "for the clearest Dutchie, UPC, QR, or METRC label scan."
        )
        photo = st.camera_input(
            "Photograph the Dutchie QR, UPC, or package label",
            key=f"audit_camera_{stage}_{audit.id}",
            help="Hold the label flat, fill most of the frame, and avoid glare.",
            resolution="720p",
            width="stretch",
        )
        decoded, decode_error = _decode_camera_label(photo)
        if decoded:
            st.success(f"Label read: {decoded}")
        elif decode_error:
            st.warning(decode_error)

    with st.form(f"audit_scan_form_{stage}_{audit.id}", clear_on_submit=True):
        scan_code = st.text_input(
            "Scanned code",
            value=decoded,
            placeholder="Scan QR/barcode or enter Dutchie, UPC, SKU, lot, or METRC package ID",
        )
        left, right = st.columns([1, 1.3])
        quantity = left.number_input("Physical quantity", min_value=0.0, step=1.0, format="%.3f")
        reason = right.selectbox(
            "Variance reason",
            ["", "Count correction", "Damage", "Waste", "Return", "Transfer timing", "Receiving timing", "Unknown"],
        )
        notes = st.text_input("Count note (optional)")
        submit_label = "Save recount" if recount else "Save count"
        if st.form_submit_button(submit_label, type="primary", width="stretch"):
            try:
                line = repository.record_scanned_count(
                    organization_id,
                    facility_id,
                    audit.id,
                    raw_code=scan_code,
                    quantity=quantity,
                    actor=_actor(),
                    recount=recount,
                    reason=reason,
                    notes=notes,
                )
            except Exception as exc:
                st.error(f"Count was not saved: {exc}")
            else:
                lot = lots_by_id.get(line.lot_id)
                product = products_by_id.get(getattr(lot, "product_id", ""))
                st.success(
                    f"Saved {quantity:,.3f} {line.unit} for "
                    f"{getattr(product, 'name', 'product')} · {getattr(lot, 'lot_code', '')}."
                )
                st.rerun()

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
        if eligible:
            selection = st.selectbox(
                "Inventory item",
                options=[line.id for line, _, _ in eligible],
                format_func=lambda line_id: next(
                    f"{getattr(product, 'name', 'Unknown')} · {getattr(lot, 'lot_code', '')} · {getattr(lot, 'location_code', '')}"
                    for line, lot, product in eligible
                    if line.id == line_id
                ),
                key=f"audit_manual_line_{stage}_{audit.id}",
            )
            selected = next(item for item in eligible if item[0].id == selection)
            manual_quantity = st.number_input(
                "Physical quantity",
                min_value=0.0,
                step=1.0,
                format="%.3f",
                key=f"audit_manual_qty_{stage}_{audit.id}",
            )
            if st.button("Save manual count", key=f"audit_manual_save_{stage}_{audit.id}", width="stretch"):
                line, lot, product = selected
                try:
                    repository.record_scanned_count(
                        organization_id,
                        facility_id,
                        audit.id,
                        raw_code=_primary_code(lot, product),
                        quantity=manual_quantity,
                        actor=_actor(),
                        recount=recount,
                        notes="Manual item selection",
                    )
                except Exception as exc:
                    st.error(f"Count was not saved: {exc}")
                else:
                    st.success("Manual count saved.")
                    st.rerun()
        else:
            st.success("No items remain in this count stage.")


def _final_totals(rows: list[dict[str, object]]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame()
    frame = pd.DataFrame(rows)
    completed = frame[frame["Final Count"].notna()].copy()
    if completed.empty:
        return pd.DataFrame()
    completed["Cost Impact"] = completed["Variance"] * completed["Unit Cost"]
    completed["Revenue Impact"] = completed["Variance"] * completed["Retail Price"]
    return (
        completed.groupby("Unit", dropna=False)
        .agg(
            **{
                "Expected": ("Expected", "sum"),
                "Physical": ("Final Count", "sum"),
                "Variance": ("Variance", "sum"),
                "Absolute Variance": ("Variance", lambda values: values.abs().sum()),
                "Cost Impact": ("Cost Impact", "sum"),
                "Revenue Impact": ("Revenue Impact", "sum"),
            }
        )
        .reset_index()
    )


def render_inventory_audits(
    repository: InventoryAuditRepository,
    organization_id: str,
    facility_id: str,
    products,
    lots,
    *,
    operation_type: str = "production",
) -> None:
    """Render audit creation, scan counting, recount, final totals, and history."""

    retail = operation_type == "retail"
    st.subheader("Retail inventory counts" if retail else "Inventory audit & reconciliation")
    st.caption(
        "Scan Dutchie labels, UPCs, SKUs, lots, or METRC packages. First-pass variances move into a required recount queue before approval."
    )
    audits = repository.list_audits(organization_id, facility_id, operation_type)
    products_by_id = {product.id: product for product in products}
    lots_by_id = {lot.id: lot for lot in lots}
    lot_options = {
        lot.id: (
            f"{getattr(products_by_id.get(lot.product_id), 'name', 'Unknown')} · "
            f"{lot.lot_code} · {lot.location_code}"
        )
        for lot in lots
    }

    with st.expander("Start a physical count", expanded=not audits):
        if not lots:
            st.info("Load inventory lots for this facility before starting an audit.")
        else:
            with st.form(f"inventory_audit_create_{operation_type}"):
                left, right = st.columns(2)
                prefix = "RTL" if retail else "PROD"
                audit_number = left.text_input(
                    "Audit number", value=f"{prefix}-{date.today():%Y%m%d}-{len(audits) + 1:03d}"
                )
                scope = right.text_input("Scope", value="Full store" if retail else "Full facility")
                selected_lots = st.multiselect(
                    "Inventory to count",
                    options=list(lot_options),
                    default=list(lot_options),
                    format_func=lambda lot_id: lot_options[lot_id],
                )
                settings_left, settings_right = st.columns(2)
                blind_count = settings_left.checkbox(
                    "Blind first count",
                    value=True,
                    help="Expected quantities remain hidden until the first pass is complete.",
                )
                tolerance = settings_right.number_input(
                    "Recount tolerance",
                    min_value=0.0,
                    value=0.0,
                    step=0.1,
                    help="A variance greater than this amount requires a recount.",
                )
                notes = st.text_area("Instructions / notes", height=70)
                if st.form_submit_button("Start count", type="primary", width="stretch"):
                    try:
                        repository.create_audit(
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
                    except Exception as exc:
                        st.error(f"Unable to start the count: {exc}")
                    else:
                        st.success("Count started and expected inventory captured.")
                        st.rerun()

    if not audits:
        st.info("No count history yet. Start the first audit above.")
        return

    audit_by_id = {audit.id: audit for audit in audits}
    open_ids = [audit.id for audit in audits if audit.status in {"draft", "in_progress"}]
    default_id = open_ids[0] if open_ids else audits[0].id
    selected_id = st.selectbox(
        "Audit session",
        options=list(audit_by_id),
        index=list(audit_by_id).index(default_id),
        format_func=lambda audit_id: (
            f"{audit_by_id[audit_id].audit_number} · "
            f"{audit_by_id[audit_id].status.replace('_', ' ').title()} · {audit_by_id[audit_id].scope_label}"
        ),
    )
    audit = audit_by_id[selected_id]
    lines = repository.list_lines(organization_id, audit.id)
    rows = _line_rows(lines, products_by_id, lots_by_id)
    first_complete = sum(line.first_count_quantity is not None for line in lines)
    pending = len(lines) - first_complete
    recount_lines = [line for line in lines if line.recount_required]
    variances = [line for line in lines if line.counted_quantity is not None and abs(line.variance_quantity) > 1e-9]
    scans = repository.list_scans(organization_id, audit.id)
    exceptions = [scan for scan in scans if scan.match_status != "matched"]

    metrics = st.columns(4)
    metrics[0].metric("First pass", f"{first_complete}/{len(lines)}")
    metrics[1].metric("Recounts waiting", len(recount_lines))
    metrics[2].metric("Scan exceptions", len(exceptions))
    metrics[3].metric(
        "Accuracy",
        "Blind" if audit.blind_count and pending else f"{((len(lines) - len(variances)) / max(1, len(lines))) * 100:.1f}%",
    )

    if audit.status not in {"completed", "cancelled"}:
        if pending:
            st.info(f"First pass in progress: {pending} item(s) remain. Scan every item before recount results are revealed.")
            _count_form(
                repository,
                organization_id,
                facility_id,
                audit,
                recount=False,
                lots_by_id=lots_by_id,
                products_by_id=products_by_id,
            )
            if not audit.blind_count:
                progress = pd.DataFrame(rows).drop(columns=["line_id", "Unit Cost", "Retail Price"])
                st.dataframe(progress, hide_index=True, width="stretch")
        elif recount_lines:
            st.warning(f"First pass complete. {len(recount_lines)} item(s) require a recount before approval.")
            _count_form(
                repository,
                organization_id,
                facility_id,
                audit,
                recount=True,
                lots_by_id=lots_by_id,
                products_by_id=products_by_id,
            )
            recount_ids = {line.id for line in recount_lines}
            recount_frame = pd.DataFrame([row for row in rows if row["line_id"] in recount_ids])
            st.dataframe(
                recount_frame.drop(columns=["line_id", "Unit Cost", "Retail Price"]),
                hide_index=True,
                width="stretch",
            )
        else:
            st.success("Counting and required recounts are complete. Review totals and approve the audit.")
    else:
        st.success("This audit is complete and locked.")

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

    ready = pending == 0 and not recount_lines
    if ready or audit.status == "completed":
        st.divider()
        st.markdown("### Final audit totals")
        totals = _final_totals(rows)
        st.caption("Different units of measure remain separate so totals are operationally meaningful.")
        if not totals.empty:
            st.dataframe(
                totals,
                hide_index=True,
                width="stretch",
                column_config={
                    "Cost Impact": st.column_config.NumberColumn(format="$%.2f"),
                    "Revenue Impact": st.column_config.NumberColumn(format="$%.2f"),
                },
            )
        detail = pd.DataFrame(rows).drop(columns=["line_id"])
        st.dataframe(detail, hide_index=True, width="stretch")
        st.download_button(
            "Export final audit CSV",
            data=detail.to_csv(index=False).encode("utf-8"),
            file_name=f"inventory_audit_{audit.audit_number}.csv",
            mime="text/csv",
        )
        if audit.status not in {"completed", "cancelled"}:
            st.markdown("### Manager approval")
            confirm = st.checkbox(
                "I reviewed the recounts and confirmed the final physical quantities",
                key=f"audit_confirm_{audit.id}",
            )
            post_adjustments = st.checkbox(
                "Post approved corrections to the append-only inventory ledger",
                value=True,
                key=f"audit_post_{audit.id}",
            )
            if st.button("Approve and complete audit", type="primary", disabled=not confirm, width="stretch"):
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
                    st.success("Audit approved and completed.")
                    st.rerun()

    st.divider()
    st.markdown("### Audit history")
    history = pd.DataFrame(
        [
            {
                "Audit": item.audit_number,
                "Type": item.operation_type.title(),
                "Status": item.status.replace("_", " ").title(),
                "Scope": item.scope_label,
                "Started": item.started_at,
                "Started By": item.created_by,
                "Completed": item.completed_at,
                "Completed By": item.completed_by,
            }
            for item in audits
        ]
    )
    st.dataframe(history, hide_index=True, width="stretch")


def render_inventory_audit_workspace(operation_type: str = "retail") -> None:
    """Standalone entry point used by Retail Ops."""

    organization_id = st.session_state.get("active_organization_id")
    facility_id = st.session_state.get("active_facility_id")
    if not organization_id or not facility_id:
        st.warning("Select an organization and facility before opening Inventory Counts.")
        return
    try:
        audits, coman = _standalone_repositories("inventory-audits-scan-v1")
        if operation_type == "retail":
            _render_retail_snapshot_intake(audits, organization_id, facility_id)
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
        if "inventory_audits" in message or "inventory_audit_scans" in message:
            st.error("Inventory Counts needs database migration 0012 before it can load.")
            st.code("migrations/versions/0012_inventory_audits.sql")
        else:
            st.error(f"Inventory Counts could not load: {exc}")
