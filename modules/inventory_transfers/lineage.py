from __future__ import annotations

from collections import deque
from typing import Any

from sqlalchemy import Engine, or_, select
from sqlalchemy.orm import Session, sessionmaker

from modules.coman.models import InventoryLot
from modules.material_lineage.service import MaterialLineageService

from .models import InventoryTransfer, InventoryTransferLine


class CrossFacilityLineageService:
    """Federate proven facility-scoped graphs through durable transfer edges.

    MaterialLineageService remains strictly facility scoped. This wrapper only opens
    another facility graph when the caller is authorized for that facility and a
    durable InventoryTransferLine proves the package movement.
    """

    def __init__(self, engine: Engine):
        self.engine = engine
        self.sessions = sessionmaker(bind=engine, expire_on_commit=False, future=True)
        self.material = MaterialLineageService(engine)

    def lot_graph(
        self,
        *,
        organization_id: str,
        facility_id: str,
        lot_id: str,
        allowed_facility_ids: set[str],
        max_depth: int = 8,
    ) -> dict[str, Any]:
        allowed = set(allowed_facility_ids or {facility_id})
        allowed.add(facility_id)
        root = self.material.lot_graph(
            organization_id=organization_id,
            facility_id=facility_id,
            lot_id=lot_id,
            max_depth=max_depth,
        )
        nodes: dict[str, dict[str, Any]] = {row["key"]: dict(row) for row in root.get("nodes") or []}
        edges: dict[tuple, dict[str, Any]] = {}
        for row in root.get("edges") or []:
            edges[self._edge_key(row)] = dict(row)

        queue: deque[tuple[str, str, int]] = deque()
        queued: set[tuple[str, str]] = set()
        for node in nodes.values():
            if node.get("type") == "lot" and node.get("id"):
                scoped = self._lot_scope(organization_id, str(node["id"]))
                if scoped:
                    marker = (str(node["id"]), scoped)
                    queue.append((marker[0], marker[1], 0))
                    queued.add(marker)

        processed: set[tuple[str, str]] = set()
        transfer_ids: set[str] = set()
        redacted_facilities: set[str] = set()
        while queue:
            current_lot_id, current_facility_id, depth = queue.popleft()
            marker = (current_lot_id, current_facility_id)
            if marker in processed or depth > max_depth:
                continue
            processed.add(marker)
            with self.sessions() as session:
                matches = list(
                    session.execute(
                        select(InventoryTransferLine, InventoryTransfer)
                        .join(InventoryTransfer, InventoryTransfer.id == InventoryTransferLine.transfer_id)
                        .where(
                            InventoryTransferLine.organization_id == organization_id,
                            InventoryTransfer.organization_id == organization_id,
                            or_(
                                InventoryTransferLine.source_lot_id == current_lot_id,
                                InventoryTransferLine.destination_lot_id == current_lot_id,
                            ),
                        )
                    )
                )
            for line, transfer in matches:
                transfer_ids.add(transfer.id)
                transfer_key = f"transfer:{transfer.id}"
                nodes.setdefault(
                    transfer_key,
                    {
                        "key": transfer_key,
                        "type": "transfer",
                        "id": transfer.id,
                        "manifest_reference": transfer.manifest_reference,
                        "status": transfer.status,
                        "source_facility_name": transfer.source_facility_name,
                        "destination_facility_name": transfer.destination_facility_name,
                        "source_license_number": transfer.source_license_number,
                        "destination_license_number": transfer.destination_license_number,
                        "shipped_at": transfer.shipped_at,
                        "received_at": transfer.received_at,
                    },
                )
                source_key = self._lot_or_reference_node(
                    nodes,
                    organization_id=organization_id,
                    lot_id=line.source_lot_id,
                    facility_id=transfer.source_facility_id,
                    allowed=allowed,
                    reference_key=f"transfer-source:{line.id}",
                    package_id=line.source_package_id,
                    lot_code=line.source_lot_code,
                    facility_name=transfer.source_facility_name,
                    license_number=transfer.source_license_number,
                    direction="source",
                )
                edges[self._edge_key({"from": source_key, "to": transfer_key, "relationship": "transferred_out", "quantity": line.quantity, "unit": line.unit, "purpose": transfer.manifest_reference})] = {
                    "from": source_key,
                    "to": transfer_key,
                    "relationship": "transferred_out",
                    "quantity": float(line.quantity),
                    "unit": line.unit,
                    "purpose": transfer.manifest_reference,
                }
                if line.destination_lot_id:
                    destination_key = self._lot_or_reference_node(
                        nodes,
                        organization_id=organization_id,
                        lot_id=line.destination_lot_id,
                        facility_id=transfer.destination_facility_id,
                        allowed=allowed,
                        reference_key=f"transfer-destination:{line.id}",
                        package_id=line.destination_package_id,
                        lot_code=line.destination_lot_code,
                        facility_name=transfer.destination_facility_name,
                        license_number=transfer.destination_license_number,
                        direction="destination",
                    )
                    edges[self._edge_key({"from": transfer_key, "to": destination_key, "relationship": "received_as_transfer", "quantity": line.received_quantity or line.quantity, "unit": line.unit, "purpose": transfer.manifest_reference})] = {
                        "from": transfer_key,
                        "to": destination_key,
                        "relationship": "received_as_transfer",
                        "quantity": float(line.received_quantity or line.quantity),
                        "unit": line.unit,
                        "purpose": transfer.manifest_reference,
                    }
                else:
                    destination_key = f"transfer-in-transit:{line.id}"
                    nodes.setdefault(
                        destination_key,
                        {
                            "key": destination_key,
                            "type": "transfer_reference",
                            "id": line.id,
                            "package_id": line.source_package_id,
                            "lot_code": "",
                            "facility_name": transfer.destination_facility_name,
                            "license_number": transfer.destination_license_number,
                            "direction": "in_transit",
                            "status": line.status,
                        },
                    )
                    edges[self._edge_key({"from": transfer_key, "to": destination_key, "relationship": "in_transit", "quantity": line.quantity, "unit": line.unit, "purpose": transfer.manifest_reference})] = {
                        "from": transfer_key,
                        "to": destination_key,
                        "relationship": "in_transit",
                        "quantity": float(line.quantity),
                        "unit": line.unit,
                        "purpose": transfer.manifest_reference,
                    }

                for related_lot_id, related_facility_id in (
                    (line.source_lot_id, transfer.source_facility_id),
                    (line.destination_lot_id, transfer.destination_facility_id),
                ):
                    if not related_lot_id:
                        continue
                    related_marker = (str(related_lot_id), str(related_facility_id))
                    if related_facility_id not in allowed:
                        redacted_facilities.add(str(related_facility_id))
                        continue
                    if related_marker not in queued:
                        related_graph = self.material.lot_graph(
                            organization_id=organization_id,
                            facility_id=str(related_facility_id),
                            lot_id=str(related_lot_id),
                            max_depth=max(0, max_depth - depth - 1),
                        )
                        for node in related_graph.get("nodes") or []:
                            nodes.setdefault(node["key"], dict(node))
                        for edge in related_graph.get("edges") or []:
                            edges[self._edge_key(edge)] = dict(edge)
                        for node in related_graph.get("nodes") or []:
                            if node.get("type") != "lot" or not node.get("id"):
                                continue
                            scope = self._lot_scope(organization_id, str(node["id"]))
                            if scope and scope in allowed:
                                next_marker = (str(node["id"]), scope)
                                if next_marker not in queued:
                                    queue.append((next_marker[0], next_marker[1], depth + 1))
                                    queued.add(next_marker)

        return {
            "root_lot_id": root["root_lot_id"],
            "nodes": list(nodes.values()),
            "edges": list(edges.values()),
            "node_count": len(nodes),
            "edge_count": len(edges),
            "max_depth": max_depth,
            "transfer_count": len(transfer_ids),
            "cross_facility": bool(transfer_ids),
            "redacted_facility_count": len(redacted_facilities),
        }

    def _lot_scope(self, organization_id: str, lot_id: str) -> str | None:
        with self.sessions() as session:
            row = session.scalar(
                select(InventoryLot.facility_id).where(
                    InventoryLot.id == lot_id,
                    InventoryLot.organization_id == organization_id,
                )
            )
        return str(row) if row else None

    def _lot_or_reference_node(
        self,
        nodes: dict[str, dict[str, Any]],
        *,
        organization_id: str,
        lot_id: str,
        facility_id: str,
        allowed: set[str],
        reference_key: str,
        package_id: str,
        lot_code: str,
        facility_name: str,
        license_number: str,
        direction: str,
    ) -> str:
        if facility_id in allowed:
            lot_key = f"lot:{lot_id}"
            if lot_key not in nodes:
                with self.sessions() as session:
                    lot = session.scalar(
                        select(InventoryLot).where(
                            InventoryLot.id == lot_id,
                            InventoryLot.organization_id == organization_id,
                            InventoryLot.facility_id == facility_id,
                        )
                    )
                if lot:
                    nodes[lot_key] = {
                        "key": lot_key,
                        "type": "lot",
                        "id": lot.id,
                        "lot_code": lot.lot_code,
                        "package_id": lot.compliance_package_id,
                        "product_id": lot.product_id,
                        "status": lot.status,
                        "facility_id": lot.facility_id,
                    }
                    return lot_key
            else:
                return lot_key
        nodes.setdefault(
            reference_key,
            {
                "key": reference_key,
                "type": "transfer_reference",
                "id": reference_key,
                "package_id": package_id,
                "lot_code": lot_code,
                "facility_name": facility_name,
                "license_number": license_number,
                "direction": direction,
                "redacted": True,
            },
        )
        return reference_key

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
