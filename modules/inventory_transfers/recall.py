from __future__ import annotations

from collections import defaultdict, deque
from typing import Any

from sqlalchemy import Engine, func, select
from sqlalchemy.orm import sessionmaker

from modules.coman.models import Facility, InventoryLot, InventoryTransaction, Product

from .lineage import CrossFacilityLineageService


class RecallBlastRadiusService:
    """Compute a deterministic downstream recall scope from durable genealogy.

    The lineage graph is the source of truth for relationships. Recall 360 only walks
    forward from the selected lot, so upstream ingredients/parents remain visible in
    Package 360 genealogy without being incorrectly classified as recalled descendants.
    """

    def __init__(self, engine: Engine):
        self.engine = engine
        self.sessions = sessionmaker(bind=engine, expire_on_commit=False, future=True)
        self.lineage = CrossFacilityLineageService(engine)

    def blast_radius(
        self,
        *,
        organization_id: str,
        facility_id: str,
        lot_id: str,
        allowed_facility_ids: set[str],
        max_depth: int = 12,
    ) -> dict[str, Any]:
        allowed = set(allowed_facility_ids or {facility_id})
        allowed.add(facility_id)
        graph = self.lineage.lot_graph(
            organization_id=organization_id,
            facility_id=facility_id,
            lot_id=lot_id,
            allowed_facility_ids=allowed,
            max_depth=max_depth,
        )
        nodes = {str(row["key"]): dict(row) for row in graph.get("nodes") or []}
        root_key = f"lot:{graph['root_lot_id']}"
        if root_key not in nodes:
            raise ValueError("Recall source package could not be resolved in the lineage graph.")

        adjacency: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for raw in graph.get("edges") or []:
            edge = dict(raw)
            source = str(edge.get("from") or "")
            target = str(edge.get("to") or "")
            if source and target:
                adjacency[source].append(edge)

        depth: dict[str, int] = {root_key: 0}
        predecessor: dict[str, dict[str, Any]] = {}
        queue: deque[str] = deque([root_key])
        while queue:
            current = queue.popleft()
            current_depth = depth[current]
            for edge in adjacency.get(current, []):
                target = str(edge["to"])
                target_node = nodes.get(target) or {}
                if target_node.get("type") == "transfer" and str(target_node.get("status") or "").casefold() == "cancelled":
                    continue
                if target in depth:
                    continue
                depth[target] = current_depth + 1
                predecessor[target] = edge
                queue.append(target)

        reachable_keys = set(depth)
        affected_lot_ids = {
            str(nodes[key]["id"])
            for key in reachable_keys
            if key in nodes and nodes[key].get("type") == "lot" and nodes[key].get("id")
        }
        affected_lot_ids.add(str(graph["root_lot_id"]))

        lot_rows: dict[str, tuple[InventoryLot, Product, Facility]] = {}
        balances: dict[str, float] = {}
        with self.sessions() as session:
            if affected_lot_ids:
                for lot, product, facility in session.execute(
                    select(InventoryLot, Product, Facility)
                    .join(Product, Product.id == InventoryLot.product_id)
                    .join(Facility, Facility.id == InventoryLot.facility_id)
                    .where(
                        InventoryLot.id.in_(affected_lot_ids),
                        InventoryLot.organization_id == organization_id,
                        InventoryLot.facility_id.in_(allowed),
                        Product.organization_id == organization_id,
                        Facility.organization_id == organization_id,
                    )
                ):
                    lot_rows[str(lot.id)] = (lot, product, facility)
                for found_lot_id, balance in session.execute(
                    select(
                        InventoryTransaction.lot_id,
                        func.coalesce(func.sum(InventoryTransaction.quantity_delta), 0.0),
                    )
                    .where(InventoryTransaction.lot_id.in_(affected_lot_ids))
                    .group_by(InventoryTransaction.lot_id)
                ):
                    balances[str(found_lot_id)] = float(balance or 0.0)

        affected: list[dict[str, Any]] = []
        for found_lot_id, (lot, product, facility) in lot_rows.items():
            key = f"lot:{found_lot_id}"
            node_depth = int(depth.get(key, 0 if found_lot_id == graph["root_lot_id"] else max_depth + 1))
            path = self._path(root_key, key, predecessor)
            affected.append(
                {
                    "lot_id": found_lot_id,
                    "lot_code": lot.lot_code,
                    "package_id": lot.compliance_package_id,
                    "product_id": lot.product_id,
                    "product_name": product.name,
                    "facility_id": lot.facility_id,
                    "facility_name": facility.name,
                    "license_number": facility.license_number,
                    "status": lot.status,
                    "balance": balances.get(found_lot_id, 0.0),
                    "unit": product.base_unit,
                    "depth": node_depth,
                    "is_source": found_lot_id == graph["root_lot_id"],
                    "path": path,
                }
            )
        affected.sort(key=lambda row: (row["depth"], row["facility_name"], row["product_name"], row["package_id"] or row["lot_code"]))

        protected_exposures: list[dict[str, Any]] = []
        for key in sorted(reachable_keys, key=lambda item: (depth[item], item)):
            node = nodes.get(key) or {}
            if node.get("type") != "transfer_reference":
                continue
            protected_exposures.append(
                {
                    "key": key,
                    "package_id": node.get("package_id") or "",
                    "lot_code": node.get("lot_code") or "",
                    "facility_name": node.get("facility_name") or "",
                    "license_number": node.get("license_number") or "",
                    "direction": node.get("direction") or "",
                    "status": node.get("status") or "",
                    "redacted": bool(node.get("redacted")),
                    "depth": depth[key],
                    "path": self._path(root_key, key, predecessor),
                }
            )

        on_hand_by_unit: dict[str, float] = defaultdict(float)
        status_counts: dict[str, int] = defaultdict(int)
        facility_ids: set[str] = set()
        license_numbers: set[str] = set()
        for row in affected:
            status_counts[str(row["status"] or "unknown")] += 1
            facility_ids.add(str(row["facility_id"]))
            if row["license_number"]:
                license_numbers.add(str(row["license_number"]))
            if float(row["balance"] or 0) > 0:
                on_hand_by_unit[str(row["unit"] or "unit")] += float(row["balance"])

        reachable_transfers = {
            str(nodes[key]["id"])
            for key in reachable_keys
            if key in nodes and nodes[key].get("type") == "transfer" and nodes[key].get("id")
        }
        return {
            "source_lot_id": str(graph["root_lot_id"]),
            "affected_lots": affected,
            "affected_lot_count": len(affected),
            "downstream_lot_count": sum(not row["is_source"] for row in affected),
            "active_inventory_lot_count": sum(float(row["balance"] or 0) > 0 for row in affected),
            "facility_count": len(facility_ids),
            "license_count": len(license_numbers),
            "transfer_count": len(reachable_transfers),
            "protected_exposure_count": len(protected_exposures),
            "protected_exposures": protected_exposures,
            "on_hand_by_unit": dict(sorted(on_hand_by_unit.items())),
            "status_counts": dict(sorted(status_counts.items())),
            "cross_facility": bool(graph.get("cross_facility")),
            "redacted_facility_count": int(graph.get("redacted_facility_count") or 0),
            "max_depth": max_depth,
        }

    @staticmethod
    def _path(
        root_key: str,
        target_key: str,
        predecessor: dict[str, dict[str, Any]],
    ) -> list[dict[str, Any]]:
        if target_key == root_key:
            return []
        reversed_path: list[dict[str, Any]] = []
        current = target_key
        seen: set[str] = set()
        while current != root_key and current not in seen:
            seen.add(current)
            edge = predecessor.get(current)
            if not edge:
                return []
            reversed_path.append(
                {
                    "from": edge.get("from"),
                    "to": edge.get("to"),
                    "relationship": edge.get("relationship"),
                    "quantity": edge.get("quantity"),
                    "unit": edge.get("unit"),
                    "purpose": edge.get("purpose"),
                }
            )
            current = str(edge.get("from") or "")
        if current != root_key:
            return []
        return list(reversed(reversed_path))
