from __future__ import annotations

from collections import Counter
from typing import Any

from sqlalchemy import Engine, func, or_, select
from sqlalchemy.orm import Session

from modules.coman.models import AppUser, AppUserFacilityRole, Facility, InventoryLot, Product
from modules.inventory_transfers.lineage import CrossFacilityLineageService
from modules.inventory_transfers.recall import RecallBlastRadiusService

from .datasets import DatasetAccessContext


TRACEABILITY_CAPABILITIES = frozenset({"retail", "production", "cultivation"})


class AgentTraceabilityService:
    """Read-only traceability queries bound to trusted server-side AI access context."""

    def __init__(self, access: DatasetAccessContext):
        if access.engine is None:
            raise ValueError("Traceability tools require a trusted database engine.")
        self.access = access
        self.engine: Engine = access.engine
        self.allowed_facility_ids = self._allowed_facility_ids()
        self.lineage = CrossFacilityLineageService(self.engine)
        self.recall = RecallBlastRadiusService(self.engine)

    @classmethod
    def available_for(cls, access: DatasetAccessContext | None) -> bool:
        return bool(
            access
            and access.engine is not None
            and TRACEABILITY_CAPABILITIES.intersection(set(access.capabilities or ()))
            and access.organization_id
            and access.facility_id
        )

    def package_lineage(self, args: dict[str, Any]) -> dict[str, Any]:
        identifier = self._identifier(args)
        resolution = self._resolve_lot(identifier)
        if not resolution.get("resolved"):
            return resolution
        root = resolution["lot"]
        max_depth = max(1, min(int(args.get("max_depth") or 24), 64))
        limit = max(5, min(int(args.get("limit") or 50), 100))
        graph = self.lineage.lot_graph(
            organization_id=self.access.organization_id,
            facility_id=str(root["facility_id"]),
            lot_id=str(root["lot_id"]),
            allowed_facility_ids=self.allowed_facility_ids,
            max_depth=max_depth,
        )
        nodes = [dict(row) for row in graph.get("nodes") or []]
        edges = [dict(row) for row in graph.get("edges") or []]
        node_types = Counter(str(row.get("type") or "unknown") for row in nodes)
        relationships = Counter(str(row.get("relationship") or "unknown") for row in edges)
        bounded_nodes = nodes[:limit]
        bounded_edges = edges[: max(limit, min(limit * 2, 160))]
        summary = (
            f"Package lineage for {root['package_id'] or root['lot_code']}: "
            f"{len(nodes)} node(s), {len(edges)} relationship edge(s), "
            f"{int(graph.get('transfer_count') or 0)} durable transfer(s), "
            f"{int(graph.get('redacted_facility_count') or 0)} protected facility scope(s)."
        )
        return {
            "tool": "package_lineage",
            "read_only": True,
            "resolved": True,
            "identifier": identifier,
            "root_lot": root,
            "node_count": len(nodes),
            "edge_count": len(edges),
            "node_type_counts": dict(sorted(node_types.items())),
            "relationship_counts": dict(sorted(relationships.items())),
            "transfer_count": int(graph.get("transfer_count") or 0),
            "cross_facility": bool(graph.get("cross_facility")),
            "redacted_facility_count": int(graph.get("redacted_facility_count") or 0),
            "max_depth": max_depth,
            "nodes": bounded_nodes,
            "edges": bounded_edges,
            "rows_truncated": len(bounded_nodes) < len(nodes) or len(bounded_edges) < len(edges),
            "_agent_summary": summary,
        }

    def recall_blast_radius(self, args: dict[str, Any]) -> dict[str, Any]:
        identifier = self._identifier(args)
        resolution = self._resolve_lot(identifier)
        if not resolution.get("resolved"):
            return resolution
        root = resolution["lot"]
        limit = max(5, min(int(args.get("limit") or 50), 100))
        result = self.recall.blast_radius(
            organization_id=self.access.organization_id,
            facility_id=str(root["facility_id"]),
            lot_id=str(root["lot_id"]),
            allowed_facility_ids=self.allowed_facility_ids,
        )
        affected = [dict(row) for row in result.get("affected_lots") or []]
        protected = [dict(row) for row in result.get("protected_exposures") or []]
        scope_state = "complete" if result.get("scope_complete") else "INCOMPLETE"
        summary = (
            f"Recall 360 for {root['package_id'] or root['lot_code']}: "
            f"{int(result.get('affected_lot_count') or 0)} affected package(s), "
            f"{int(result.get('active_inventory_lot_count') or 0)} with positive on-hand inventory, "
            f"{int(result.get('license_count') or 0)} accessible license(s), "
            f"{int(result.get('protected_exposure_count') or 0)} protected/unresolved transfer exposure(s). "
            f"Scope is {scope_state}."
        )
        if not result.get("scope_complete"):
            summary += " Do not treat this as the complete recall blast radius; traceability review is required."
        return {
            "tool": "recall_blast_radius",
            "read_only": True,
            "resolved": True,
            "identifier": identifier,
            "root_lot": root,
            **{key: value for key, value in result.items() if key not in {"affected_lots", "protected_exposures"}},
            "affected_lots": affected[:limit],
            "protected_exposures": protected[: min(limit, 50)],
            "returned_affected_lot_count": min(len(affected), limit),
            "rows_truncated": len(affected) > limit or len(protected) > min(limit, 50),
            "_agent_summary": summary,
        }

    def _allowed_facility_ids(self) -> set[str]:
        with Session(self.engine) as session:
            if str(self.access.role or "").casefold() in {"dev", "admin"}:
                return set(
                    session.scalars(
                        select(Facility.id).where(
                            Facility.organization_id == self.access.organization_id,
                            Facility.active.is_(True),
                        )
                    )
                )
            user = session.get(AppUser, self.access.user_id)
            if not user or not user.active or user.organization_id != self.access.organization_id:
                return {self.access.facility_id}
            assigned = set(
                session.scalars(
                    select(AppUserFacilityRole.facility_id)
                    .join(Facility, Facility.id == AppUserFacilityRole.facility_id)
                    .where(
                        AppUserFacilityRole.user_id == user.id,
                        AppUserFacilityRole.organization_id == self.access.organization_id,
                        Facility.organization_id == self.access.organization_id,
                        Facility.active.is_(True),
                    )
                )
            )
            assigned.add(self.access.facility_id)
            return assigned

    def _resolve_lot(self, identifier: str) -> dict[str, Any]:
        normalized = identifier.casefold()
        with Session(self.engine) as session:
            rows = list(
                session.execute(
                    select(InventoryLot, Product, Facility)
                    .join(Product, Product.id == InventoryLot.product_id)
                    .join(Facility, Facility.id == InventoryLot.facility_id)
                    .where(
                        InventoryLot.organization_id == self.access.organization_id,
                        InventoryLot.facility_id.in_(self.allowed_facility_ids),
                        Product.organization_id == self.access.organization_id,
                        Facility.organization_id == self.access.organization_id,
                        or_(
                            func.lower(InventoryLot.id) == normalized,
                            func.lower(InventoryLot.lot_code) == normalized,
                            func.lower(InventoryLot.compliance_package_id) == normalized,
                            func.lower(InventoryLot.external_inventory_id) == normalized,
                            func.lower(InventoryLot.barcode_value) == normalized,
                        ),
                    )
                )
            )
        candidates = [self._lot_row(lot, product, facility) for lot, product, facility in rows]
        if not candidates:
            return {
                "tool": "traceability_resolution",
                "read_only": True,
                "resolved": False,
                "status": "not_found",
                "identifier": identifier,
                "candidates": [],
                "_agent_summary": f"No package or lot matching '{identifier}' was found in the authorized facility scope.",
            }
        exact_id = [row for row in candidates if str(row["lot_id"]).casefold() == normalized]
        if len(exact_id) == 1:
            return {"resolved": True, "lot": exact_id[0]}
        if len(candidates) > 1:
            candidates.sort(key=lambda row: (row["facility_id"] != self.access.facility_id, row["facility_name"], row["package_id"] or row["lot_code"]))
            return {
                "tool": "traceability_resolution",
                "read_only": True,
                "resolved": False,
                "status": "ambiguous",
                "identifier": identifier,
                "candidates": candidates[:10],
                "_agent_summary": (
                    f"'{identifier}' matches {len(candidates)} accessible lots. "
                    "Use a unique package ID, barcode, or internal lot ID before drawing a traceability conclusion."
                ),
            }
        return {"resolved": True, "lot": candidates[0]}

    @staticmethod
    def _identifier(args: dict[str, Any]) -> str:
        value = str(args.get("identifier") or "").strip().strip('"\'')
        if not value:
            raise ValueError("A package, tag, barcode, lot code, or lot ID is required.")
        if len(value) > 160:
            raise ValueError("Traceability identifier is too long.")
        return value

    @staticmethod
    def _lot_row(lot: InventoryLot, product: Product, facility: Facility) -> dict[str, Any]:
        return {
            "lot_id": str(lot.id),
            "lot_code": str(lot.lot_code or ""),
            "package_id": str(lot.compliance_package_id or ""),
            "external_inventory_id": str(lot.external_inventory_id or ""),
            "barcode_value": str(lot.barcode_value or ""),
            "product_id": str(lot.product_id),
            "product_name": str(product.name or ""),
            "status": str(lot.status or ""),
            "facility_id": str(lot.facility_id),
            "facility_name": str(facility.name or ""),
            "license_number": str(facility.license_number or ""),
        }


def register_traceability_tools(registry: Any, access: DatasetAccessContext) -> bool:
    """Attach read-only lineage/recall functions without exposing tenant scope arguments."""
    if not AgentTraceabilityService.available_for(access):
        return False

    from .tools import ToolSpec

    service = AgentTraceabilityService(access)
    identifier = {
        "type": "string",
        "description": "Package tag/ID, barcode, lot code, or internal lot ID from the current authorized organization.",
        "minLength": 1,
        "maxLength": 160,
    }
    registry._register(
        ToolSpec(
            "package_lineage",
            "Trace an authorized cannabis package or lot through durable plant, harvest, production, packaging, extraction, and cross-license genealogy. Read-only; tenant/facility scope is fixed by the server.",
            {
                "type": "object",
                "properties": {
                    "identifier": identifier,
                    "max_depth": {"type": "integer", "minimum": 1, "maximum": 64},
                    "limit": {"type": "integer", "minimum": 5, "maximum": 100},
                },
                "required": ["identifier"],
            },
            service.package_lineage,
        )
    )
    registry._register(
        ToolSpec(
            "recall_blast_radius",
            "Calculate the deterministic downstream Recall 360 blast radius for an authorized package or lot, including accessible descendants, on-hand exposure, transfers, and protected/unresolved transfer references. Read-only; does not place holds, mutate Metrc, or notify regulators.",
            {
                "type": "object",
                "properties": {
                    "identifier": identifier,
                    "limit": {"type": "integer", "minimum": 5, "maximum": 100},
                },
                "required": ["identifier"],
            },
            service.recall_blast_radius,
        )
    )
    return True
