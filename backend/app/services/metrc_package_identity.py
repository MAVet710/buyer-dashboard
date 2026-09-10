from __future__ import annotations

from typing import Any

from sqlalchemy import Engine, func, select
from sqlalchemy.orm import sessionmaker

from modules.coman.models import InventoryLot, InventoryTransaction, Product
from modules.traceability.object_links import TraceabilityObjectLinkRepository
from services.metrc_client import fetch_metrc_resource
from .metrc_package_readback import canonical_unit, package_snapshot


class MetrcPackageIdentityError(ValueError):
    pass


def _source(record: dict[str, Any]) -> dict[str, Any]:
    value = record.get("source")
    return dict(value) if isinstance(value, dict) else {}


def _provider_id(record: dict[str, Any]) -> str:
    source = _source(record)
    return str(record.get("provider_id") or source.get("Id") or source.get("id") or "").strip()


def _provider_name(record: dict[str, Any]) -> str:
    source = _source(record)
    value = record.get("name") or source.get("Name") or source.get("ItemName")
    return str(value or "").strip()


class MetrcPackageIdentityService:
    """Bind local Product/InventoryLot identities to exact fresh Metrc objects."""

    def __init__(self, engine: Engine):
        self.engine = engine
        self.sessions = sessionmaker(bind=engine, expire_on_commit=False, future=True)
        self.links = TraceabilityObjectLinkRepository(engine)

    @staticmethod
    def _scope(state: str, environment: str, license_number: str) -> tuple[str, str, str]:
        state_code = str(state or "").strip().upper()
        env = str(environment or "").strip().casefold()
        license_value = str(license_number or "").strip()
        if state_code != "MA" or env != "sandbox":
            raise MetrcPackageIdentityError(
                "Package identity promotion is currently restricted to the verified Massachusetts Metrc sandbox."
            )
        if not license_value:
            raise MetrcPackageIdentityError("An exact Massachusetts sandbox facility license is required.")
        return state_code, env, license_value

    def _read_one(
        self,
        *,
        resource: str,
        provider_id: str,
        state: str,
        environment: str,
        license_number: str,
        integrator_api_key: str,
        user_api_key: str,
    ) -> dict[str, Any]:
        readback = fetch_metrc_resource(
            state=state,
            user_api_key=user_api_key,
            integrator_api_key=integrator_api_key,
            resource=resource,
            environment=environment,
            license_number=license_number,
            path_parameters={"id": provider_id},
        )
        records = [dict(row) for row in readback.get("records") or [] if isinstance(row, dict)] if isinstance(readback, dict) else []
        if not isinstance(readback, dict) or not readback.get("ok") or len(records) != 1:
            raise MetrcPackageIdentityError(
                str((readback or {}).get("message") if isinstance(readback, dict) else "")
                or "Fresh exact Metrc identity readback failed."
            )
        if _provider_id(records[0]) != str(provider_id).strip():
            raise MetrcPackageIdentityError("Metrc returned a different provider identity than the one selected.")
        return readback

    def link_product(
        self,
        *,
        organization_id: str,
        facility_id: str,
        product_id: str,
        provider_item_id: str,
        state: str,
        environment: str,
        license_number: str,
        integrator_api_key: str,
        user_api_key: str,
    ) -> dict[str, Any]:
        state_code, env, license_value = self._scope(state, environment, license_number)
        selected = str(provider_item_id or "").strip()
        if not selected:
            raise MetrcPackageIdentityError("Choose an exact Metrc Item to link to this DoobieLogic Product.")
        with self.sessions() as session:
            product = session.get(Product, product_id)
            if not product or product.organization_id != organization_id:
                raise MetrcPackageIdentityError("Product was not found in the active organization.")
            local = {"id": product.id, "sku": product.sku, "name": product.name, "active": bool(product.active)}
        if not local["active"]:
            raise MetrcPackageIdentityError("Inactive Products cannot be newly linked to Metrc Items.")

        readback = self._read_one(
            resource="items_by_id",
            provider_id=selected,
            state=state_code,
            environment=env,
            license_number=license_value,
            integrator_api_key=integrator_api_key,
            user_api_key=user_api_key,
        )
        record = readback["records"][0]
        source = _source(record)
        if source.get("IsArchived") is True or source.get("IsActive") is False:
            raise MetrcPackageIdentityError("The selected Metrc Item is inactive and cannot back an active Product.")
        provider_name = _provider_name(record)
        if not provider_name:
            raise MetrcPackageIdentityError("The selected Metrc Item did not return a stable operator label.")
        link = self.links.upsert_verified(
            organization_id=organization_id,
            facility_id=facility_id,
            provider="metrc",
            jurisdiction=state_code,
            environment=env,
            license_number=license_value,
            entity_type="product",
            entity_id=product_id,
            provider_resource="items",
            provider_id=selected,
            provider_label=provider_name,
        )
        return {
            "product": local,
            "link": self.links.payload(link),
            "readback": {"provider_id": selected, "name": provider_name, "last_modified": str(record.get("last_modified") or "")},
            "message": "Product is linked to the exact freshly verified Metrc Item identity.",
        }

    def link_lot(
        self,
        *,
        organization_id: str,
        facility_id: str,
        lot_id: str,
        provider_package_id: str,
        state: str,
        environment: str,
        license_number: str,
        integrator_api_key: str,
        user_api_key: str,
    ) -> dict[str, Any]:
        state_code, env, license_value = self._scope(state, environment, license_number)
        selected = str(provider_package_id or "").strip()
        if not selected:
            raise MetrcPackageIdentityError("Choose an exact Metrc Package to link to this inventory lot.")
        with self.sessions() as session:
            lot = session.get(InventoryLot, lot_id)
            if not lot or lot.organization_id != organization_id or lot.facility_id != facility_id:
                raise MetrcPackageIdentityError("Inventory package was not found in the active facility.")
            product = session.get(Product, lot.product_id)
            if not product or product.organization_id != organization_id:
                raise MetrcPackageIdentityError("Inventory package has no valid Product Master identity.")
            balance = float(session.scalar(select(func.coalesce(func.sum(InventoryTransaction.quantity_delta), 0.0)).where(InventoryTransaction.lot_id == lot.id)) or 0.0)
            unit = session.scalar(select(InventoryTransaction.unit).where(InventoryTransaction.lot_id == lot.id).order_by(InventoryTransaction.occurred_at.desc()).limit(1)) or product.base_unit
            local = {
                "id": lot.id,
                "lot_code": lot.lot_code,
                "compliance_package_id": lot.compliance_package_id,
                "product_id": product.id,
                "product_name": product.name,
                "balance": balance,
                "unit": str(unit),
            }
        product_link = self.links.get_local(
            organization_id=organization_id,
            facility_id=facility_id,
            provider="metrc",
            environment=env,
            entity_type="product",
            entity_id=local["product_id"],
        )
        if not product_link or product_link.status != "verified" or product_link.provider_resource != "items" or product_link.license_number != license_value:
            raise MetrcPackageIdentityError("Link this lot's Product to the exact Metrc Item before linking the package identity.")

        readback = self._read_one(
            resource="packages_by_id",
            provider_id=selected,
            state=state_code,
            environment=env,
            license_number=license_value,
            integrator_api_key=integrator_api_key,
            user_api_key=user_api_key,
        )
        snapshot = package_snapshot(readback)
        if not snapshot.get("ok") or not snapshot.get("label"):
            raise MetrcPackageIdentityError("The selected Metrc Package did not return a stable package label.")
        if str(snapshot.get("item") or "").strip().casefold() != str(product_link.provider_label or "").strip().casefold():
            raise MetrcPackageIdentityError("The selected Metrc Package belongs to a different Metrc Item than this Product link.")
        provider_quantity = snapshot.get("quantity")
        if provider_quantity is None or abs(float(provider_quantity) - float(local["balance"])) > 1e-6:
            raise MetrcPackageIdentityError("Local inventory balance does not match the selected Metrc Package quantity; reconcile before linking.")
        if canonical_unit(snapshot.get("unit_of_measure")) != canonical_unit(local["unit"]):
            raise MetrcPackageIdentityError("Local inventory unit does not match the selected Metrc Package unit; reconcile before linking.")
        existing_label = str(local["compliance_package_id"] or "").strip()
        provider_label = str(snapshot["label"]).strip()
        if existing_label and existing_label.casefold() != provider_label.casefold():
            raise MetrcPackageIdentityError("This inventory lot already stores a different compliance package label; reconcile it instead of overwriting.")

        link = self.links.upsert_verified(
            organization_id=organization_id,
            facility_id=facility_id,
            provider="metrc",
            jurisdiction=state_code,
            environment=env,
            license_number=license_value,
            entity_type="inventory_lot",
            entity_id=lot_id,
            provider_resource="packages",
            provider_id=selected,
            provider_label=provider_label,
        )
        if not existing_label:
            with self.sessions.begin() as session:
                row = session.get(InventoryLot, lot_id)
                if not row or row.organization_id != organization_id or row.facility_id != facility_id:
                    raise MetrcPackageIdentityError("Inventory package disappeared before its verified label could be persisted.")
                row.compliance_package_id = provider_label
        return {
            "lot": local | {"compliance_package_id": provider_label},
            "link": self.links.payload(link),
            "readback": {key: snapshot.get(key) for key in ("provider_id", "label", "item", "quantity", "unit_of_measure", "finished", "last_modified")},
            "message": "Inventory lot is linked to the exact freshly verified Metrc Package identity.",
        }

    def list_links(self, *, organization_id: str, facility_id: str, environment: str) -> dict[str, list[dict[str, Any]]]:
        rows = self.links.list_facility(
            organization_id=organization_id,
            facility_id=facility_id,
            provider="metrc",
            environment=str(environment or "").strip().casefold(),
            limit=5000,
        )
        result = {"products": [], "packages": []}
        for row in rows:
            if row.entity_type == "product" and row.provider_resource == "items":
                result["products"].append(self.links.payload(row))
            elif row.entity_type == "inventory_lot" and row.provider_resource == "packages":
                result["packages"].append(self.links.payload(row))
        return result
