"""Durable receiving for manufacturing/cultivation inventory.

Production receiving is intentionally separate from retail receiving. Incoming
material is posted into the active organization/facility ledger as a new lot and
append-only inventory transaction. This keeps each METRC/license location isolated
while reusing the canonical Co-Man product master and inventory ledger.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import streamlit as st
from sqlalchemy import Engine, select
from sqlalchemy.orm import sessionmaker

from modules.coman.models import AuditEvent, InventoryLot, InventoryTransaction, Product, utc_now


@dataclass(frozen=True)
class ProductionReceipt:
    product_id: str
    lot_code: str
    compliance_package_id: str
    quantity: float
    unit: str
    location_code: str = "RECEIVING"
    source_name: str = ""
    manifest_reference: str = ""
    notes: str = ""


class ProductionInventoryReceivingService:
    """Post inbound cannabis material to one facility-scoped durable ledger."""

    def __init__(self, engine: Engine):
        self._sessions = sessionmaker(bind=engine, expire_on_commit=False, future=True)

    def list_products(self, organization_id: str) -> list[Product]:
        with self._sessions() as session:
            return list(
                session.scalars(
                    select(Product)
                    .where(Product.organization_id == organization_id, Product.active.is_(True))
                    .order_by(Product.name)
                )
            )

    def receive(
        self,
        *,
        organization_id: str,
        facility_id: str,
        receipt: ProductionReceipt,
        actor: str,
    ) -> str:
        if not organization_id or not facility_id:
            raise ValueError("Select an active production/cultivation facility before receiving inventory.")
        if float(receipt.quantity) <= 0:
            raise ValueError("Received quantity must be greater than zero.")
        lot_code = str(receipt.lot_code or receipt.compliance_package_id or "").strip()
        if not lot_code:
            raise ValueError("A lot/package identifier is required.")
        unit = str(receipt.unit or "").strip()
        if not unit:
            raise ValueError("A unit of measure is required.")

        with self._sessions.begin() as session:
            product = session.get(Product, receipt.product_id)
            if not product or product.organization_id != organization_id or not product.active:
                raise ValueError("Select an active Product Master item for this organization.")

            duplicate = session.scalar(
                select(InventoryLot.id).where(
                    InventoryLot.facility_id == facility_id,
                    InventoryLot.lot_code == lot_code,
                )
            )
            if duplicate:
                raise ValueError("That lot/package already exists in the active facility.")

            lot = InventoryLot(
                organization_id=organization_id,
                facility_id=facility_id,
                product_id=product.id,
                lot_code=lot_code,
                compliance_package_id=str(receipt.compliance_package_id or "").strip(),
                external_inventory_id=str(receipt.compliance_package_id or "").strip(),
                barcode_value=str(receipt.compliance_package_id or lot_code).strip(),
                location_code=str(receipt.location_code or "RECEIVING").strip() or "RECEIVING",
                status="available",
                received_at=utc_now(),
                notes=(
                    f"Source: {str(receipt.source_name or '').strip()}\n"
                    f"Manifest/transfer: {str(receipt.manifest_reference or '').strip()}\n"
                    f"{str(receipt.notes or '').strip()}"
                ).strip(),
            )
            session.add(lot)
            session.flush()

            session.add(
                InventoryTransaction(
                    organization_id=organization_id,
                    facility_id=facility_id,
                    lot_id=lot.id,
                    transaction_type="receive",
                    quantity_delta=float(receipt.quantity),
                    unit=unit,
                    production_order_id=None,
                    commercial_order_id=None,
                    commercial_order_line_id=None,
                    reason="Inbound production/cultivation material received",
                    reference=str(receipt.manifest_reference or receipt.compliance_package_id or lot_code).strip(),
                    actor=str(actor or "system").strip() or "system",
                )
            )
            session.add(
                AuditEvent(
                    organization_id=organization_id,
                    facility_id=facility_id,
                    entity_type="inventory_lot",
                    entity_id=lot.id,
                    action="production_inventory_received",
                    actor=str(actor or "system").strip() or "system",
                    changes_json=(
                        "{"
                        f'"lot_code":"{lot_code}",'
                        f'"package_id":"{str(receipt.compliance_package_id or "").strip()}",'
                        f'"quantity":{float(receipt.quantity)},'
                        f'"unit":"{unit}"'
                        "}"
                    ),
                )
            )
            return lot.id


def render_production_receive_inventory_dialog(state: dict[str, Any], engine: Engine) -> None:
    """Render production/cultivation receiving against the active facility only."""

    organization_id = str(state.get("active_organization_id") or "")
    facility_id = str(state.get("active_facility_id") or "")
    service = ProductionInventoryReceivingService(engine)

    def body() -> None:
        if st.button("Close", key="prod_receive_close"):
            state["inventory_receive_open"] = False
            st.rerun()

        st.caption("PRODUCTION / CULTIVATION RECEIVING")
        st.markdown("## Receive material")
        st.caption("Posts only to the active facility/license inventory. Retail inventory is never modified.")

        if not organization_id or not facility_id:
            st.warning("Select an active production or cultivation facility first.")
            return

        products = service.list_products(organization_id)
        if not products:
            st.warning("Create the material in Product Master before receiving it.")
            return

        labels = {f"{item.name} · {item.sku}": item for item in products}
        selected_label = st.selectbox("Material / product", list(labels), key="prod_receive_product")
        selected = labels[selected_label]

        cols = st.columns(2)
        package_id = cols[0].text_input("METRC package ID", key="prod_receive_package_id")
        lot_code = cols[1].text_input(
            "Internal lot / batch",
            value=package_id,
            key="prod_receive_lot_code",
            help="Defaults to the METRC package ID when the internal lot is not different.",
        )
        qty_cols = st.columns(3)
        quantity = qty_cols[0].number_input("Quantity", min_value=0.0, step=1.0, key="prod_receive_qty")
        unit = qty_cols[1].selectbox("Unit", [selected.base_unit, "g", "kg", "oz", "lb", "unit"], key="prod_receive_unit")
        location = qty_cols[2].text_input("Room / location", value="RECEIVING", key="prod_receive_room")

        source_cols = st.columns(2)
        source_name = source_cols[0].text_input("Source facility / supplier", key="prod_receive_source")
        manifest = source_cols[1].text_input("Manifest / transfer #", key="prod_receive_manifest")
        notes = st.text_area("Notes", key="prod_receive_notes")

        if st.button("Receive material", type="primary", width="stretch", key="prod_receive_commit"):
            try:
                lot_id = service.receive(
                    organization_id=organization_id,
                    facility_id=facility_id,
                    receipt=ProductionReceipt(
                        product_id=selected.id,
                        lot_code=lot_code or package_id,
                        compliance_package_id=package_id,
                        quantity=float(quantity),
                        unit=unit,
                        location_code=location,
                        source_name=source_name,
                        manifest_reference=manifest,
                        notes=notes,
                    ),
                    actor=str(state.get("auth_user_email") or state.get("auth_user_name") or "system"),
                )
            except Exception as exc:
                st.error(str(exc))
                return
            state["inventory_receive_open"] = False
            state["inventory_adjustment_flash"] = f"Received material into production inventory · lot {lot_id}"
            st.rerun()

    if hasattr(st, "dialog"):
        @st.dialog("Receive production inventory", width="large")
        def dialog() -> None:
            body()
        dialog()
    else:
        with st.container(border=True):
            body()
