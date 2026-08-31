from __future__ import annotations

from collections import defaultdict, deque
from hashlib import sha256
import json
from typing import Any

from sqlalchemy import Engine, func, or_, select
from sqlalchemy.orm import Session, sessionmaker

from modules.coman.models import (
    AuditEvent,
    CommercialOrder,
    CommercialOrderLine,
    Facility,
    InventoryLot,
    InventoryTransaction,
    OrderLotAllocation,
    Product,
    TradePartner,
)
from modules.cultivation.models import CultivationPlant
from modules.inventory_transfers.lineage import CrossFacilityLineageService
from modules.material_lineage.models import (
    MaterialTransformation,
    MaterialTransformationInput,
    MaterialTransformationOutput,
)
from modules.operational_moats.models import CultivationHarvest


ROOT_TYPES = {"package", "lot", "plant", "harvest"}
CONTAINABLE_STATUSES = {"available", "released"}
ALREADY_CONTAINED_STATUSES = {"hold", "quarantine", "failed", "test_failed", "rejected"}


class Recall360Service:
    """Deterministic recall/blast-radius analysis over durable genealogy and ledger truth.

    The report may federate across facilities the caller is authorized to inspect.
    Containment deliberately mutates only the active facility so a recall action cannot
    become an implicit cross-license write.
    """

    def __init__(self, engine: Engine):
        self.engine = engine
        self.sessions = sessionmaker(bind=engine, expire_on_commit=False, future=True)
        self.lineage = CrossFacilityLineageService(engine)

    def impact(
        self,
        *,
        organization_id: str,
        facility_id: str,
        root_type: str,
        reference: str,
        allowed_facility_ids: set[str],
        max_depth: int = 12,
    ) -> dict[str, Any]:
        normalized_type = str(root_type or "").strip().casefold()
        if normalized_type not in ROOT_TYPES:
            raise ValueError("Recall root type must be package, lot, plant, or harvest.")
        clean_reference = str(reference or "").strip()
        if not clean_reference:
            raise ValueError("Choose a package, lot, plant, or harvest reference to trace.")

        allowed = set(allowed_facility_ids or {facility_id})
        allowed.add(facility_id)
        with self.sessions() as session:
            root, starting_lots = self._resolve_root(
                session,
                organization_id=organization_id,
                facility_id=facility_id,
                root_type=normalized_type,
                reference=clean_reference,
            )

        nodes: dict[str, dict[str, Any]] = {}
        edges: dict[tuple, dict[str, Any]] = {}
        redacted_facility_count = 0
        transfer_ids: set[str] = set()
        for lot_id in starting_lots:
            graph = self.lineage.lot_graph(
                organization_id=organization_id,
                facility_id=facility_id,
                lot_id=lot_id,
                allowed_facility_ids=allowed,
                max_depth=max_depth,
            )
            redacted_facility_count = max(redacted_facility_count, int(graph.get("redacted_facility_count") or 0))
            for node in graph.get("nodes") or []:
                nodes.setdefault(str(node["key"]), dict(node))
                if node.get("type") == "transfer" and node.get("id"):
                    transfer_ids.add(str(node["id"]))
            for edge in graph.get("edges") or []:
                edges[self._edge_key(edge)] = dict(edge)

        root_key = self._root_key(root)
        nodes.setdefault(root_key, dict(root) | {"key": root_key})
        impacted_keys = self._descendant_keys(root_key, list(edges.values())) if starting_lots else {root_key}
        impacted_lot_ids = {
            str(nodes[key]["id"])
            for key in impacted_keys
            if key in nodes and nodes[key].get("type") == "lot" and nodes[key].get("id")
        }
        # A package/lot root is itself part of the blast radius even if it has no children.
        if root.get("type") == "lot" and root.get("id"):
            impacted_lot_ids.add(str(root["id"]))

        with self.sessions() as session:
            lot_rows = self._lot_impacts(session, organization_id, impacted_lot_ids, allowed)
            commercial = self._commercial_exposure(session, organization_id, impacted_lot_ids, allowed)
            facility_names = {
                row.id: {"id": row.id, "name": row.name, "code": row.code, "license_number": row.license_number}
                for row in session.scalars(
                    select(Facility).where(
                        Facility.organization_id == organization_id,
                        Facility.id.in_(allowed or {facility_id}),
                    )
                )
            }

        local_candidates = [
            row for row in lot_rows
            if row["facility_id"] == facility_id
            and row["on_hand"] > 1e-9
            and row["status"].casefold() in CONTAINABLE_STATUSES
        ]
        remote_candidates = [
            row for row in lot_rows
            if row["facility_id"] != facility_id
            and row["on_hand"] > 1e-9
            and row["status"].casefold() in CONTAINABLE_STATUSES
        ]
        already_contained = [
            row for row in lot_rows
            if row["on_hand"] > 1e-9 and row["status"].casefold() in ALREADY_CONTAINED_STATUSES
        ]
        finished = [row for row in lot_rows if row["item_type"] == "finished_good"]
        in_transit = [
            node for node in nodes.values()
            if node.get("type") == "transfer_reference" and node.get("direction") == "in_transit"
        ]
        shipped = [row for row in commercial if row["shipped_quantity"] > 1e-9]
        committed = [row for row in commercial if row["reserved_quantity"] > 1e-9]
        customers = sorted({str(row["customer"]) for row in shipped if row.get("customer")})

        return {
            "root": root,
            "summary": {
                "affected_lots": len(lot_rows),
                "finished_goods": len(finished),
                "on_hand_lots": sum(1 for row in lot_rows if row["on_hand"] > 1e-9),
                "local_containment_candidates": len(local_candidates),
                "remote_containment_candidates": len(remote_candidates),
                "already_contained": len(already_contained),
                "commercial_orders": len({row["order_id"] for row in commercial}),
                "shipped_orders": len({row["order_id"] for row in shipped}),
                "customers_exposed": len(customers),
                "in_transit_packages": len(in_transit),
                "transfer_count": len(transfer_ids),
                "redacted_facility_count": redacted_facility_count,
            },
            "affected_lots": lot_rows,
            "commercial_exposure": commercial,
            "customers_exposed": customers,
            "in_transit": in_transit,
            "local_containment_candidates": local_candidates,
            "remote_containment_candidates": remote_candidates,
            "already_contained": already_contained,
            "facilities": list(facility_names.values()),
            "graph": {
                "nodes": list(nodes.values()),
                "edges": list(edges.values()),
                "node_count": len(nodes),
                "edge_count": len(edges),
                "root_key": root_key,
            },
            "limitations": [
                "Retail consumer sales are not attributed to a specific package unless the source POS sale carries lot/package identity; DoobieLogic does not infer consumer exposure from product-level sales alone.",
                "A DoobieLogic operational hold is local containment and is not represented as a completed Metrc/state-system quarantine action.",
            ],
        }

    def preview_local_hold(
        self,
        *,
        organization_id: str,
        facility_id: str,
        root_type: str,
        reference: str,
        allowed_facility_ids: set[str],
        reason: str,
    ) -> dict[str, Any]:
        report = self.impact(
            organization_id=organization_id,
            facility_id=facility_id,
            root_type=root_type,
            reference=reference,
            allowed_facility_ids=allowed_facility_ids,
        )
        candidates = report["local_containment_candidates"]
        state = [
            {"lot_id": row["lot_id"], "status": row["status"], "on_hand": row["on_hand"]}
            for row in candidates
        ]
        payload = {
            "organization_id": organization_id,
            "facility_id": facility_id,
            "root_type": str(root_type).strip().casefold(),
            "reference": str(reference).strip(),
            "reason": str(reason or "Recall containment").strip(),
            "state": state,
        }
        preview_key = sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        return {
            "preview_key": preview_key,
            "candidate_count": len(candidates),
            "candidates": candidates,
            "remote_candidate_count": len(report["remote_containment_candidates"]),
            "already_contained_count": len(report["already_contained"]),
            "reason": payload["reason"],
            "state_system_sync": False,
            "warning": "This applies DoobieLogic operational holds only in the active facility. Switch facilities to contain remote affected inventory and complete any required state-system action separately.",
        }

    def commit_local_hold(
        self,
        *,
        organization_id: str,
        facility_id: str,
        root_type: str,
        reference: str,
        allowed_facility_ids: set[str],
        reason: str,
        preview_key: str,
        actor: str,
    ) -> dict[str, Any]:
        current = self.preview_local_hold(
            organization_id=organization_id,
            facility_id=facility_id,
            root_type=root_type,
            reference=reference,
            allowed_facility_ids=allowed_facility_ids,
            reason=reason,
        )
        if str(preview_key or "") != current["preview_key"]:
            raise ValueError("Recall containment changed after preview. Refresh the impact report and preview again before applying holds.")
        candidate_ids = [str(row["lot_id"]) for row in current["candidates"]]
        if not candidate_ids:
            return {"changed": 0, "lot_ids": [], "state_system_sync": False}
        with self.sessions.begin() as session:
            lots = list(
                session.scalars(
                    select(InventoryLot).where(
                        InventoryLot.organization_id == organization_id,
                        InventoryLot.facility_id == facility_id,
                        InventoryLot.id.in_(candidate_ids),
                    ).with_for_update()
                )
            )
            by_id = {row.id: row for row in lots}
            if set(by_id) != set(candidate_ids):
                raise ValueError("One or more recall candidates moved outside the active facility. Refresh before applying holds.")
            for expected in current["candidates"]:
                lot = by_id[str(expected["lot_id"])]
                balance = self._balance(session, lot.id)
                if str(lot.status or "").casefold() not in CONTAINABLE_STATUSES or abs(balance - float(expected["on_hand"])) > 1e-9:
                    raise ValueError("Recall candidate state changed after preview. Refresh before applying holds.")
            changed_ids: list[str] = []
            for lot in lots:
                previous = str(lot.status or "available")
                lot.status = "hold"
                session.add(
                    AuditEvent(
                        organization_id=organization_id,
                        facility_id=facility_id,
                        entity_type="inventory_lot",
                        entity_id=lot.id,
                        action="recall_operational_hold_applied",
                        actor=actor,
                        changes_json=json.dumps(
                            {
                                "previous_status": previous,
                                "status": "hold",
                                "reason": str(reason or "Recall containment").strip(),
                                "root_type": str(root_type).strip().casefold(),
                                "root_reference": str(reference).strip(),
                                "state_system_sync": False,
                            },
                            sort_keys=True,
                        ),
                    )
                )
                changed_ids.append(lot.id)
            session.flush()
        return {"changed": len(changed_ids), "lot_ids": changed_ids, "state_system_sync": False}

    def _resolve_root(
        self,
        session: Session,
        *,
        organization_id: str,
        facility_id: str,
        root_type: str,
        reference: str,
    ) -> tuple[dict[str, Any], list[str]]:
        if root_type in {"package", "lot"}:
            lot = session.scalar(
                select(InventoryLot).where(
                    InventoryLot.organization_id == organization_id,
                    InventoryLot.facility_id == facility_id,
                    or_(
                        InventoryLot.id == reference,
                        InventoryLot.lot_code == reference,
                        InventoryLot.compliance_package_id == reference,
                        InventoryLot.external_inventory_id == reference,
                        InventoryLot.barcode_value == reference,
                    ),
                )
            )
            if lot is None:
                raise ValueError("Package or lot was not found in the active facility.")
            product = session.get(Product, lot.product_id)
            return (
                {
                    "type": "lot",
                    "id": lot.id,
                    "reference": lot.compliance_package_id or lot.lot_code,
                    "lot_code": lot.lot_code,
                    "package_id": lot.compliance_package_id,
                    "product_name": product.name if product else "",
                    "facility_id": lot.facility_id,
                },
                [lot.id],
            )
        if root_type == "plant":
            plant = session.scalar(
                select(CultivationPlant).where(
                    CultivationPlant.organization_id == organization_id,
                    CultivationPlant.facility_id == facility_id,
                    or_(CultivationPlant.id == reference, CultivationPlant.plant_tag == reference),
                )
            )
            if plant is None:
                raise ValueError("Plant was not found in the active cultivation facility.")
            transformation_ids = list(
                session.scalars(
                    select(MaterialTransformationInput.transformation_id).where(
                        MaterialTransformationInput.organization_id == organization_id,
                        MaterialTransformationInput.facility_id == facility_id,
                        MaterialTransformationInput.entity_type == "plant",
                        MaterialTransformationInput.entity_id == plant.id,
                    )
                )
            )
            lot_ids = list(
                session.scalars(
                    select(MaterialTransformationOutput.lot_id).where(
                        MaterialTransformationOutput.transformation_id.in_(transformation_ids or ["__none__"])
                    )
                )
            )
            return (
                {
                    "type": "plant",
                    "id": plant.id,
                    "reference": plant.plant_tag,
                    "plant_tag": plant.plant_tag,
                    "strain_name": plant.strain_name,
                    "facility_id": plant.facility_id,
                },
                list(dict.fromkeys(str(row) for row in lot_ids if row)),
            )
        harvest = session.scalar(
            select(CultivationHarvest).where(
                CultivationHarvest.organization_id == organization_id,
                CultivationHarvest.facility_id == facility_id,
                or_(CultivationHarvest.id == reference, CultivationHarvest.harvest_code == reference),
            )
        )
        if harvest is None:
            raise ValueError("Harvest was not found in the active cultivation facility.")
        transformation_ids = list(
            session.scalars(
                select(MaterialTransformation.id).where(
                    MaterialTransformation.organization_id == organization_id,
                    MaterialTransformation.facility_id == facility_id,
                    MaterialTransformation.source_entity_type == "harvest",
                    MaterialTransformation.source_entity_id == harvest.id,
                )
            )
        )
        lot_ids = list(
            session.scalars(
                select(MaterialTransformationOutput.lot_id).where(
                    MaterialTransformationOutput.transformation_id.in_(transformation_ids or ["__none__"])
                )
            )
        )
        return (
            {
                "type": "harvest",
                "id": harvest.id,
                "reference": harvest.harvest_code,
                "harvest_code": harvest.harvest_code,
                "strain": harvest.strain,
                "facility_id": harvest.facility_id,
            },
            list(dict.fromkeys(str(row) for row in lot_ids if row)),
        )

    @staticmethod
    def _root_key(root: dict[str, Any]) -> str:
        return f"{root['type']}:{root['id']}"

    @staticmethod
    def _descendant_keys(root_key: str, edges: list[dict[str, Any]]) -> set[str]:
        outgoing: dict[str, list[str]] = defaultdict(list)
        for edge in edges:
            source = str(edge.get("from") or "")
            target = str(edge.get("to") or "")
            if source and target:
                outgoing[source].append(target)
        visited = {root_key}
        queue = deque([root_key])
        while queue:
            key = queue.popleft()
            for child in outgoing.get(key, []):
                if child not in visited:
                    visited.add(child)
                    queue.append(child)
        return visited

    def _lot_impacts(
        self,
        session: Session,
        organization_id: str,
        lot_ids: set[str],
        allowed_facility_ids: set[str],
    ) -> list[dict[str, Any]]:
        if not lot_ids:
            return []
        lots = list(
            session.scalars(
                select(InventoryLot).where(
                    InventoryLot.organization_id == organization_id,
                    InventoryLot.id.in_(lot_ids),
                    InventoryLot.facility_id.in_(allowed_facility_ids or ["__none__"]),
                )
            )
        )
        product_ids = {row.product_id for row in lots}
        products = {
            row.id: row
            for row in session.scalars(
                select(Product).where(Product.organization_id == organization_id, Product.id.in_(product_ids or ["__none__"]))
            )
        }
        facilities = {
            row.id: row
            for row in session.scalars(
                select(Facility).where(Facility.organization_id == organization_id, Facility.id.in_({row.facility_id for row in lots} or ["__none__"]))
            )
        }
        result = []
        for lot in lots:
            product = products.get(lot.product_id)
            facility = facilities.get(lot.facility_id)
            result.append(
                {
                    "lot_id": lot.id,
                    "lot_code": lot.lot_code,
                    "package_id": lot.compliance_package_id,
                    "product_id": lot.product_id,
                    "product_name": product.name if product else "",
                    "sku": product.sku if product else "",
                    "item_type": product.item_type if product else "",
                    "facility_id": lot.facility_id,
                    "facility_name": facility.name if facility else "",
                    "license_number": facility.license_number if facility else "",
                    "location": lot.location_code,
                    "status": str(lot.status or ""),
                    "on_hand": self._balance(session, lot.id),
                    "unit": product.base_unit if product else "",
                }
            )
        result.sort(key=lambda row: (row["facility_name"], row["product_name"], row["package_id"] or row["lot_code"]))
        return result

    def _commercial_exposure(
        self,
        session: Session,
        organization_id: str,
        lot_ids: set[str],
        allowed_facility_ids: set[str],
    ) -> list[dict[str, Any]]:
        if not lot_ids:
            return []
        allocations = list(
            session.scalars(
                select(OrderLotAllocation).where(
                    OrderLotAllocation.organization_id == organization_id,
                    OrderLotAllocation.lot_id.in_(lot_ids),
                    OrderLotAllocation.facility_id.in_(allowed_facility_ids or ["__none__"]),
                )
            )
        )
        shipments = list(
            session.scalars(
                select(InventoryTransaction).where(
                    InventoryTransaction.organization_id == organization_id,
                    InventoryTransaction.lot_id.in_(lot_ids),
                    InventoryTransaction.facility_id.in_(allowed_facility_ids or ["__none__"]),
                    InventoryTransaction.transaction_type == "shipment",
                    InventoryTransaction.commercial_order_id.is_not(None),
                )
            )
        )
        order_ids = {str(row.commercial_order_id) for row in allocations if row.commercial_order_id} | {
            str(row.commercial_order_id) for row in shipments if row.commercial_order_id
        }
        orders = {
            row.id: row
            for row in session.scalars(
                select(CommercialOrder).where(
                    CommercialOrder.organization_id == organization_id,
                    CommercialOrder.id.in_(order_ids or ["__none__"]),
                )
            )
        }
        partner_ids = {row.partner_id for row in orders.values()}
        partners = {
            row.id: row
            for row in session.scalars(
                select(TradePartner).where(
                    TradePartner.organization_id == organization_id,
                    TradePartner.id.in_(partner_ids or ["__none__"]),
                )
            )
        }
        line_ids = {str(row.commercial_order_line_id) for row in allocations if row.commercial_order_line_id} | {
            str(row.commercial_order_line_id) for row in shipments if row.commercial_order_line_id
        }
        lines = {
            row.id: row
            for row in session.scalars(
                select(CommercialOrderLine).where(
                    CommercialOrderLine.organization_id == organization_id,
                    CommercialOrderLine.id.in_(line_ids or ["__none__"]),
                )
            )
        }
        grouped: dict[tuple[str, str, str], dict[str, Any]] = {}
        for allocation in allocations:
            order = orders.get(allocation.commercial_order_id)
            if not order or order.order_type != "sales":
                continue
            line = lines.get(allocation.commercial_order_line_id)
            partner = partners.get(order.partner_id)
            key = (order.id, allocation.commercial_order_line_id, allocation.lot_id)
            row = grouped.setdefault(
                key,
                {
                    "order_id": order.id,
                    "order_number": order.order_number,
                    "order_status": order.status,
                    "customer": partner.name if partner else "",
                    "customer_license": partner.license_or_registration if partner else "",
                    "lot_id": allocation.lot_id,
                    "line_id": allocation.commercial_order_line_id,
                    "description": line.description if line else "",
                    "reserved_quantity": 0.0,
                    "shipped_quantity": 0.0,
                    "unit": line.unit if line else "",
                    "shipment_references": [],
                },
            )
            row["reserved_quantity"] += max(0.0, float(allocation.quantity or 0) - float(allocation.fulfilled_quantity or 0))
        for shipment in shipments:
            order = orders.get(str(shipment.commercial_order_id))
            if not order or order.order_type != "sales":
                continue
            line = lines.get(str(shipment.commercial_order_line_id))
            partner = partners.get(order.partner_id)
            key = (order.id, str(shipment.commercial_order_line_id or ""), shipment.lot_id)
            row = grouped.setdefault(
                key,
                {
                    "order_id": order.id,
                    "order_number": order.order_number,
                    "order_status": order.status,
                    "customer": partner.name if partner else "",
                    "customer_license": partner.license_or_registration if partner else "",
                    "lot_id": shipment.lot_id,
                    "line_id": str(shipment.commercial_order_line_id or ""),
                    "description": line.description if line else "",
                    "reserved_quantity": 0.0,
                    "shipped_quantity": 0.0,
                    "unit": shipment.unit,
                    "shipment_references": [],
                },
            )
            row["shipped_quantity"] += abs(float(shipment.quantity_delta or 0))
            if shipment.reference and shipment.reference not in row["shipment_references"]:
                row["shipment_references"].append(shipment.reference)
        result = list(grouped.values())
        result.sort(key=lambda row: (row["customer"], row["order_number"], row["description"]))
        return result

    @staticmethod
    def _balance(session: Session, lot_id: str) -> float:
        return float(
            session.scalar(
                select(func.coalesce(func.sum(InventoryTransaction.quantity_delta), 0.0)).where(
                    InventoryTransaction.lot_id == lot_id
                )
            )
            or 0.0
        )

    @staticmethod
    def _edge_key(row: dict[str, Any]) -> tuple:
        return (
            row.get("from"),
            row.get("to"),
            row.get("relationship"),
            row.get("quantity"),
            row.get("unit"),
            row.get("purpose"),
        )
