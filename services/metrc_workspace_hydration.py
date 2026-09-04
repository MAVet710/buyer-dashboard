from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Mapping

from sqlalchemy import Engine, select
from sqlalchemy.orm import sessionmaker

from modules.coman.models import AuditEvent, Product, utc_now
from modules.product_master.models import ProductMasterProfile
from modules.traceability.object_links import TraceabilityObjectLink
from services.metrc_facility_materialization import MetrcCanonicalInventorySeeder


def _text(value: Any) -> str:
    return str(value or "").strip()


def _source(record: Mapping[str, Any]) -> Mapping[str, Any]:
    nested = record.get("source")
    return nested if isinstance(nested, Mapping) else record


def _first(source: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        value = source.get(key)
        if value is not None and _text(value):
            return value
    return None


def _item_identity(record: Mapping[str, Any]) -> tuple[str, str, str, str, str]:
    source = _source(record)
    item_id = _text(record.get("provider_id") or record.get("id") or _first(source, "Id", "ID", "id", "ItemId"))
    name = _text(record.get("name") or _first(source, "Name", "ItemName", "ProductName", "name"))
    category = _text(record.get("category") or _first(source, "ProductCategoryName", "ItemCategoryName", "CategoryName", "category"))
    brand = _text(record.get("brand") or _first(source, "BrandName", "ItemBrandName", "brand"))
    unit = _text(record.get("unit") or _first(source, "UnitOfMeasureName", "UnitOfMeasureAbbreviation", "UnitOfMeasure", "unit") or "unit")
    return item_id, name, category, brand, unit


def _product_sku(state: str, item_id: str) -> str:
    token = re.sub(r"[^A-Z0-9]+", "-", item_id.upper()).strip("-")
    base = f"METRC-{state.upper()}-{token}"[:120]
    return base or f"METRC-{state.upper()}-ITEM"


def _provider_link(
    session,
    *,
    organization_id: str,
    facility_id: str,
    environment: str,
    provider_id: str,
) -> TraceabilityObjectLink | None:
    return session.scalar(
        select(TraceabilityObjectLink).where(
            TraceabilityObjectLink.organization_id == organization_id,
            TraceabilityObjectLink.facility_id == facility_id,
            TraceabilityObjectLink.provider == "metrc",
            TraceabilityObjectLink.environment == environment,
            TraceabilityObjectLink.provider_resource == "items",
            TraceabilityObjectLink.provider_id == provider_id,
        )
    )


def _scope_matches(link: TraceabilityObjectLink | None, *, state: str, license_number: str) -> bool:
    if link is None:
        return True
    return link.jurisdiction == state.upper() and link.license_number == license_number


class MetrcItemMasterSeeder:
    """Materialize provider-owned Metrc Items into the DoobieLogic Product Master.

    Provider identity is always carried by TraceabilityObjectLink. Existing linked
    Product identity is preserved; this service fills missing provider-neutral master
    data but never silently rewrites a local Product whose name or unit differs.
    """

    def __init__(self, engine: Engine):
        self.sessions = sessionmaker(bind=engine, expire_on_commit=False, future=True)

    def seed(
        self,
        *,
        organization_id: str,
        facility_id: str,
        state: str,
        environment: str,
        license_number: str,
        actor: str,
        items: list[dict[str, Any]],
    ) -> dict[str, Any]:
        state = _text(state).upper() or "MA"
        environment = _text(environment).casefold() or "sandbox"
        license_number = _text(license_number)
        actor = _text(actor) or "system"
        created_products = 0
        created_profiles = 0
        created_links = 0
        existing_products = 0
        skipped = 0
        conflicts: list[dict[str, str]] = []
        warnings: list[dict[str, str]] = []

        with self.sessions.begin() as session:
            products = list(session.scalars(select(Product).where(Product.organization_id == organization_id)))
            by_id = {row.id: row for row in products}
            by_sku = {_text(row.sku).casefold(): row for row in products}

            for record in items:
                if not isinstance(record, dict):
                    skipped += 1
                    continue
                item_id, name, category, brand, unit = _item_identity(record)
                if not item_id or not name:
                    skipped += 1
                    conflicts.append({
                        "code": "missing_item_identity",
                        "item_id": item_id,
                        "message": "Metrc Item has no exact provider id + name pair, so Product Master identity was not guessed.",
                    })
                    continue

                link = _provider_link(
                    session,
                    organization_id=organization_id,
                    facility_id=facility_id,
                    environment=environment,
                    provider_id=item_id,
                )
                if not _scope_matches(link, state=state, license_number=license_number):
                    skipped += 1
                    conflicts.append({
                        "code": "item_link_license_mismatch",
                        "item_id": item_id,
                        "message": "The exact Metrc Item is already linked under a different facility license scope.",
                    })
                    continue

                product: Product | None = None
                if link is not None:
                    if link.entity_type != "product":
                        skipped += 1
                        conflicts.append({
                            "code": "item_link_collision",
                            "item_id": item_id,
                            "message": "The Metrc Item is already linked to a non-Product DoobieLogic object.",
                        })
                        continue
                    product = by_id.get(link.entity_id)
                    if product is None:
                        skipped += 1
                        conflicts.append({
                            "code": "orphan_item_link",
                            "item_id": item_id,
                            "message": "The exact Metrc Item link points to a Product that is not present in this organization.",
                        })
                        continue
                    existing_products += 1
                    if _text(product.name) != name or (_text(product.base_unit) and _text(product.base_unit).casefold() != unit.casefold()):
                        warnings.append({
                            "code": "existing_product_metadata_differs",
                            "item_id": item_id,
                            "message": "Metrc Item identity is linked, but local Product name/unit differs; local Product identity was preserved.",
                        })
                    link.provider_label = name or link.provider_label
                    link.status = "verified"
                    link.mismatch_reason = ""
                    link.verified_at = utc_now()
                    link.last_seen_at = utc_now()
                else:
                    sku = _product_sku(state, item_id)
                    owner = by_sku.get(sku.casefold())
                    if owner is not None:
                        digest = hashlib.sha256(f"{state}:{item_id}".encode("utf-8")).hexdigest()[:8].upper()
                        sku = f"{sku[:110]}-{digest}"[:120]
                        owner = by_sku.get(sku.casefold())
                    if owner is not None:
                        skipped += 1
                        conflicts.append({
                            "code": "product_sku_collision",
                            "item_id": item_id,
                            "message": "A local Product Master SKU collides with the deterministic Metrc Item SKU.",
                        })
                        continue
                    product = Product(
                        organization_id=organization_id,
                        sku=sku,
                        name=name,
                        item_type="cannabis",
                        base_unit=unit or "unit",
                        unit_cost=0.0,
                        retail_price=0.0,
                        upc="",
                        external_product_id="",
                        active=True,
                    )
                    session.add(product)
                    session.flush()
                    by_id[product.id] = product
                    by_sku[sku.casefold()] = product
                    created_products += 1
                    link = TraceabilityObjectLink(
                        organization_id=organization_id,
                        facility_id=facility_id,
                        provider="metrc",
                        jurisdiction=state,
                        environment=environment,
                        license_number=license_number,
                        entity_type="product",
                        entity_id=product.id,
                        provider_resource="items",
                        provider_id=item_id,
                        provider_label=name,
                        status="verified",
                        mismatch_reason="",
                        verified_at=utc_now(),
                        last_seen_at=utc_now(),
                    )
                    session.add(link)
                    created_links += 1
                    session.add(AuditEvent(
                        organization_id=organization_id,
                        facility_id=facility_id,
                        entity_type="product",
                        entity_id=product.id,
                        action="metrc_product_master_seeded",
                        actor=actor,
                        changes_json=json.dumps({
                            "metrc_item_id": item_id,
                            "name": name,
                            "category": category,
                            "brand": brand,
                            "unit": unit,
                            "environment": environment,
                            "license_number": license_number,
                        }, sort_keys=True),
                    ))

                profile = session.get(ProductMasterProfile, product.id)
                if profile is None:
                    profile = ProductMasterProfile(
                        organization_id=organization_id,
                        product_id=product.id,
                        brand=brand,
                        category=category,
                        subcategory="",
                        strain="",
                        manufacturer="",
                        product_format="",
                        image_url="",
                        description="",
                        retail_enabled=True,
                        production_enabled=True,
                    )
                    session.add(profile)
                    created_profiles += 1
                else:
                    # Blank-field enrichment is safe; populated local master data is never overwritten.
                    if not _text(profile.brand) and brand:
                        profile.brand = brand
                    if not _text(profile.category) and category:
                        profile.category = category

            summary = {
                "workspace": "product_master",
                "mode": "materialized",
                "source_item_count": len(items),
                "created_products": created_products,
                "created_profiles": created_profiles,
                "created_links": created_links,
                "existing_product_count": existing_products,
                "skipped_count": skipped,
                "conflict_count": len(conflicts),
                "warning_count": len(warnings),
                "conflicts": conflicts[:100],
                "warnings": warnings[:100],
                "overwrite_existing": False,
            }
            session.add(AuditEvent(
                organization_id=organization_id,
                facility_id=facility_id,
                entity_type="metrc_workspace_hydration",
                entity_id=facility_id,
                action="metrc_product_master_hydration_completed",
                actor=actor,
                changes_json=json.dumps({key: value for key, value in summary.items() if key not in {"conflicts", "warnings"}}, sort_keys=True),
            ))
            return summary


class MetrcWorkspaceHydrationService:
    """Route a successful Metrc snapshot into the natural DoobieLogic workspaces.

    Materializable regulatory objects become provider-linked canonical records.
    Provider-owned workflow history is left as provider shadow state for the
    appropriate read model instead of fabricating local business actions.
    """

    def __init__(self, engine: Engine):
        self.engine = engine

    def hydrate(
        self,
        *,
        organization_id: str,
        facility_id: str,
        state: str,
        environment: str,
        license_number: str,
        actor: str,
        resource_snapshots: Mapping[str, list[dict[str, Any]]],
    ) -> dict[str, Any]:
        workspaces: dict[str, dict[str, Any]] = {}

        items = [dict(row) for row in resource_snapshots.get("items", []) if isinstance(row, dict)]
        if items:
            workspaces["product_master"] = MetrcItemMasterSeeder(self.engine).seed(
                organization_id=organization_id,
                facility_id=facility_id,
                state=state,
                environment=environment,
                license_number=license_number,
                actor=actor,
                items=items,
            )

        packages = [dict(row) for row in resource_snapshots.get("packages", []) if isinstance(row, dict)]
        if packages:
            inventory = MetrcCanonicalInventorySeeder(self.engine).seed(
                organization_id=organization_id,
                facility_id=facility_id,
                state=state,
                environment=environment,
                license_number=license_number,
                actor=actor,
                packages=packages,
            )
            inventory["workspace"] = "inventory"
            inventory["mode"] = "materialized"
            workspaces["inventory"] = inventory

        transfers = [dict(row) for row in resource_snapshots.get("transfers", []) if isinstance(row, dict)]
        if transfers:
            workspaces["transfer_control"] = {
                "workspace": "transfer_control",
                "mode": "provider_shadow",
                "source_transfer_count": len(transfers),
                "message": "Synced Metrc transfers remain provider-owned and are surfaced in Transfer Control without fabricating local manifest or receiving history.",
            }

        return {
            "provider": "metrc",
            "environment": environment,
            "automatic": True,
            "workspaces": workspaces,
            "materialized_workspaces": sorted(name for name, row in workspaces.items() if row.get("mode") == "materialized"),
            "provider_shadow_workspaces": sorted(name for name, row in workspaces.items() if row.get("mode") == "provider_shadow"),
        }
