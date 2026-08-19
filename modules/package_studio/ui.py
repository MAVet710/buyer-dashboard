"""Option-B-style Package Studio work window."""

from __future__ import annotations

from typing import Any, MutableMapping

import pandas as pd
import streamlit as st
from sqlalchemy.exc import SQLAlchemyError

from modules.coman.db import ComanDatabaseConfigurationError, create_coman_engine
from .service import (
    AvailableLot,
    PackageStudioInputPlan,
    PackageStudioOutputPlan,
    PackageStudioPlan,
    PackageStudioService,
    StudioProduct,
)


ACTION_LABELS = {
    "Breakdown": "breakdown",
    "Pack Down": "pack_down",
    "Build Run": "build_run",
    "Multi-Build": "multi_build",
    "Sample Pull": "sample_pull",
    "Rework": "rework",
    "Source Correction": "correction",
}

PURPOSE_LABELS = {
    "Standard output": "standard",
    "Lab sample": "lab_sample",
    "Trade sample": "trade_sample",
    "Retail sample": "retail_sample",
    "Rework output": "rework",
    "Corrected output": "corrected",
}


def _service() -> PackageStudioService | None:
    try:
        return PackageStudioService(create_coman_engine())
    except ComanDatabaseConfigurationError:
        return None


def _actor(state: MutableMapping[str, Any]) -> str:
    return str(
        state.get("admin_user")
        or state.get("user_user")
        or state.get("auth_user_id")
        or state.get("auth_user_role")
        or "system"
    )


def _studio_css() -> None:
    st.markdown(
        """
        <style>
        .ps-kicker {color:#ff9a3c;font-size:.68rem;font-weight:820;letter-spacing:.14em;text-transform:uppercase}
        .ps-subtitle {color:#aaa49e;font-size:.82rem;margin-top:-.25rem;margin-bottom:.75rem}
        .ps-balance {
            padding:.7rem .78rem;border:1px solid rgba(255,255,255,.08);border-radius:12px;
            background:linear-gradient(145deg,#171512,#101010);margin:.35rem 0 .7rem;
        }
        .ps-balance strong {color:#f6f5f2}
        .ps-balance span {color:#aaa49e}
        .ps-sync-note {
            padding:.58rem .66rem;border:1px solid rgba(255,154,60,.18);border-radius:10px;
            background:rgba(255,154,60,.06);color:#c8c0b8;font-size:.75rem
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _lot_label(lot: AvailableLot) -> str:
    package = f" · {lot.compliance_package_id}" if lot.compliance_package_id else ""
    return f"{lot.product_name} · {lot.lot_code}{package} · {lot.balance:,.2f} {lot.unit}"


def _product_label(product: StudioProduct) -> str:
    suffix = f" · {product.sku}" if product.sku else ""
    return f"{product.name}{suffix}"


def _render_new_run(
    state: MutableMapping[str, Any],
    service: PackageStudioService,
    organization_id: str,
    facility_id: str,
    *,
    can_commit: bool,
) -> None:
    try:
        lots = service.list_available_lots(organization_id, facility_id)
        products = service.list_products(organization_id)
    except SQLAlchemyError as exc:
        st.error("Package Studio needs database migration 0017_package_studio before it can load.")
        st.caption(str(exc))
        return

    if not lots:
        st.info("No durable available packages were found for this facility.")
        st.caption("Package Studio works from Supabase-backed inventory lots so Source Trail remains auditable.")
        return
    if not products:
        st.info("No active products are available for Package Studio outputs.")
        return

    lot_by_label = {_lot_label(item): item for item in lots}
    product_by_label = {_product_label(item): item for item in products}

    action_label = st.selectbox("Package action", list(ACTION_LABELS), key="ps_action")
    action_type = ACTION_LABELS[action_label]
    source_label = st.selectbox("Source package", list(lot_by_label), key="ps_source_lot")
    source = lot_by_label[source_label]

    top = st.columns(4)
    top[0].metric("Available", f"{source.balance:,.2f} {source.unit}")
    top[1].metric("Source", source.lot_code)
    top[2].metric("Product", source.product_name[:24])
    top[3].metric("Location", source.location_code or "—")

    default_output_count = 2 if action_type in {"breakdown", "multi_build"} else 1
    output_count = int(
        st.number_input(
            "Number of outputs",
            min_value=1,
            max_value=8,
            value=default_output_count,
            step=1,
            key=f"ps_output_count_{action_type}",
            disabled=action_type == "sample_pull",
        )
    )
    if action_type == "sample_pull":
        output_count = 1

    loss_quantity = st.number_input(
        f"Recorded loss / waste ({source.unit})",
        min_value=0.0,
        value=0.0,
        step=0.01,
        key="ps_loss_qty",
    )
    reason = st.text_input("Reason / work note", key="ps_reason", placeholder="Optional operational reason")

    outputs: list[PackageStudioOutputPlan] = []
    source_total = 0.0
    st.markdown("#### Outputs")
    for index in range(output_count):
        with st.container(border=True):
            st.caption(f"OUTPUT {index + 1}")
            columns = st.columns([1.4, 1, 1])

            if action_type in {"breakdown", "sample_pull"}:
                same_product = next((p for p in products if p.product_id == source.product_id), None)
                if same_product is None:
                    st.error("The source product is not present in the active product master.")
                    return
                output_product = same_product
                columns[0].text_input(
                    "Output product",
                    value=output_product.name,
                    disabled=True,
                    key=f"ps_output_product_locked_{index}",
                )
            else:
                product_label = columns[0].selectbox(
                    "Output product",
                    list(product_by_label),
                    key=f"ps_output_product_{index}_{action_type}",
                )
                output_product = product_by_label[product_label]

            lot_code = columns[1].text_input(
                "Lot / package code",
                key=f"ps_output_lot_code_{index}_{action_type}",
                placeholder=f"PS-{index + 1:02d}",
            )
            compliance_id = columns[2].text_input(
                "METRC package tag",
                key=f"ps_output_metrc_{index}_{action_type}",
                placeholder="Optional in Phase 1",
            )

            quantity_cols = st.columns(3)
            inventory_quantity = quantity_cols[0].number_input(
                "Finished quantity",
                min_value=0.0,
                value=0.0,
                step=1.0,
                key=f"ps_output_inventory_qty_{index}_{action_type}",
            )
            inventory_unit = quantity_cols[1].text_input(
                "Finished unit",
                value=output_product.base_unit or "unit",
                key=f"ps_output_inventory_unit_{index}_{action_type}",
            )
            source_equivalent = quantity_cols[2].number_input(
                f"Source used ({source.unit})",
                min_value=0.0,
                value=0.0,
                step=0.01,
                key=f"ps_output_source_eq_{index}_{action_type}",
            )
            source_total += float(source_equivalent or 0.0)

            if action_type == "sample_pull":
                purpose_label = st.selectbox(
                    "Sample type",
                    ["Lab sample", "Trade sample", "Retail sample"],
                    key=f"ps_output_purpose_{index}_{action_type}",
                )
            elif action_type == "rework":
                purpose_label = "Rework output"
            elif action_type == "correction":
                purpose_label = "Corrected output"
            else:
                purpose_label = st.selectbox(
                    "Output purpose",
                    ["Standard output", "Trade sample", "Retail sample"],
                    key=f"ps_output_purpose_{index}_{action_type}",
                )

            outputs.append(
                PackageStudioOutputPlan(
                    product_id=output_product.product_id,
                    lot_code=lot_code,
                    inventory_quantity=float(inventory_quantity or 0.0),
                    inventory_unit=str(inventory_unit or output_product.base_unit or "unit"),
                    source_equivalent_quantity=float(source_equivalent or 0.0),
                    source_equivalent_unit=source.unit,
                    compliance_package_id=compliance_id,
                    purpose=PURPOSE_LABELS[purpose_label],
                )
            )

    source_to_use = source_total + float(loss_quantity or 0.0)
    difference = source.balance - source_to_use
    balance_text = (
        f"Source selected: {source_to_use:,.2f} {source.unit} · "
        f"Outputs: {source_total:,.2f} {source.unit} · "
        f"Loss: {float(loss_quantity or 0.0):,.2f} {source.unit} · "
        f"Remaining source: {difference:,.2f} {source.unit}"
    )
    st.markdown(
        f"""
        <div class="ps-balance">
          <strong>Mass balance preview</strong><br/>
          <span>{balance_text}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if source_to_use <= 0:
        st.info("Enter the source material used by at least one output to preview the run.")
        return
    if source_to_use > source.balance + 1e-9:
        st.error("This run consumes more material than the source package currently contains.")
        return

    plan = PackageStudioPlan(
        action_type=action_type,
        inputs=(PackageStudioInputPlan(source.lot_id, source_to_use, source.unit),),
        outputs=tuple(outputs),
        loss_quantity=float(loss_quantity or 0.0),
        source_unit=source.unit,
        reason=reason,
    )
    try:
        preview = service.preview(plan)
    except ValueError as exc:
        st.warning(str(exc))
        return

    st.success(
        f"Balanced · {preview.total_input:,.2f} {preview.source_unit} in · "
        f"{preview.total_output_source_equivalent:,.2f} out · {preview.loss_quantity:,.2f} loss"
    )
    st.markdown(
        '<div class="ps-sync-note">Phase 1 records the package operation and METRC references in Buyer Dash, '
        'but it does not silently create or adjust packages in METRC. External sync remains explicitly Not requested.</div>',
        unsafe_allow_html=True,
    )

    confirm = st.checkbox("I reviewed the source, outputs, and mass balance.", key="ps_commit_confirm")
    if not can_commit:
        st.info("Your current role can review Package Studio but cannot commit inventory transformations.")
        return
    if st.button(
        f"Commit {action_label}",
        type="primary",
        width="stretch",
        disabled=not confirm,
        key="ps_commit_run",
    ):
        try:
            result = service.commit(
                plan,
                organization_id=organization_id,
                facility_id=facility_id,
                actor=_actor(state),
            )
        except (ValueError, SQLAlchemyError) as exc:
            st.error(str(exc))
            return
        st.success(f"{result.run_number} committed with {len(result.output_lot_ids)} output package(s).")
        state["package_studio_last_run"] = result.run_number


def _render_source_trail(
    service: PackageStudioService,
    organization_id: str,
    facility_id: str,
) -> None:
    try:
        lots = service.list_available_lots(organization_id, facility_id)
    except SQLAlchemyError as exc:
        st.error("Package Studio needs database migration 0017_package_studio before Source Trail can load.")
        st.caption(str(exc))
        return
    if not lots:
        st.info("No available durable packages are present in this facility.")
        return
    lot_by_label = {_lot_label(item): item for item in lots}
    selected_label = st.selectbox("Package", list(lot_by_label), key="ps_trail_lot")
    selected = lot_by_label[selected_label]
    try:
        trail = service.source_trail(
            selected.lot_id,
            organization_id=organization_id,
            facility_id=facility_id,
        )
    except (ValueError, SQLAlchemyError) as exc:
        st.error(str(exc))
        return

    lot = trail["lot"]
    metrics = st.columns(3)
    metrics[0].metric("Current balance", f"{lot['balance']:,.2f} {lot['unit']}")
    metrics[1].metric("Package", lot["lot_code"])
    metrics[2].metric("Product", lot["product_name"][:24])

    created = trail.get("created_by")
    st.markdown("#### Parent source")
    if not created:
        st.caption("This package does not have a Package Studio parent event yet.")
    else:
        st.write(f"**{created['run_number']} · {created['action_type'].replace('_', ' ').title()}**")
        st.dataframe(pd.DataFrame(created["parents"]), hide_index=True, width="stretch")

    st.markdown("#### Downstream use")
    downstream = trail.get("used_by") or []
    if not downstream:
        st.caption("No downstream Package Studio transformations are recorded from this package.")
    else:
        for run in downstream:
            with st.expander(f"{run['run_number']} · {run['action_type'].replace('_', ' ').title()}"):
                st.caption(f"Consumed {run['quantity_consumed']:,.2f} {run['unit']}")
                st.dataframe(pd.DataFrame(run["outputs"]), hide_index=True, width="stretch")


def _render_recent_runs(
    service: PackageStudioService,
    organization_id: str,
    facility_id: str,
) -> None:
    try:
        runs = service.recent_runs(organization_id, facility_id)
    except SQLAlchemyError as exc:
        st.error("Package Studio needs database migration 0017_package_studio before run history can load.")
        st.caption(str(exc))
        return
    if not runs:
        st.info("No Package Studio runs have been committed in this facility yet.")
        return
    frame = pd.DataFrame(runs)
    frame["action_type"] = frame["action_type"].astype(str).str.replace("_", " ", regex=False).str.title()
    frame["external_sync_status"] = frame["external_sync_status"].astype(str).str.replace("_", " ", regex=False).str.title()
    st.dataframe(frame, hide_index=True, width="stretch")


def render_package_studio(state: MutableMapping[str, Any]) -> None:
    """Render the Package Studio work window body."""
    _studio_css()
    organization_id = str(state.get("active_organization_id") or "")
    facility_id = str(state.get("active_facility_id") or "")
    if not organization_id or not facility_id:
        st.warning("Choose an organization and facility before opening Package Studio.")
        return

    service = _service()
    if service is None:
        st.error("Package Studio requires the configured Supabase / Co-Man database connection.")
        return

    role = str(state.get("auth_user_role") or "trial").strip().casefold()
    can_commit = role in {"dev", "admin", "buyer", "planner", "supervisor", "operator", "qa"}

    st.markdown('<div class="ps-kicker">PACKAGE STUDIO</div>', unsafe_allow_html=True)
    st.markdown("## Package transformation")
    st.markdown(
        '<div class="ps-subtitle">Break down, pack down, build, sample, correct, and trace packages from one auditable work window.</div>',
        unsafe_allow_html=True,
    )
    tabs = st.tabs(["New Run", "Source Trail", "Recent Runs"])
    with tabs[0]:
        _render_new_run(state, service, organization_id, facility_id, can_commit=can_commit)
    with tabs[1]:
        _render_source_trail(service, organization_id, facility_id)
    with tabs[2]:
        _render_recent_runs(service, organization_id, facility_id)


def render_package_studio_dialog(state: MutableMapping[str, Any]) -> None:
    """Render Package Studio as the same raised work-window pattern as Product 360."""
    if hasattr(st, "dialog"):
        @st.dialog("Package Studio", width="large")
        def _dialog() -> None:
            if st.button("Close", key="package_studio_close"):
                state["package_studio_open"] = False
                st.rerun()
            render_package_studio(state)

        _dialog()
    else:
        with st.container(border=True):
            render_package_studio(state)
