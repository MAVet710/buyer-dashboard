"""Durable, organization-scoped nomenclature catalog and mapping persistence."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from sqlalchemy import Engine, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import sessionmaker

from modules.coman.db import ComanDatabaseConfigurationError, create_coman_engine
from modules.coman.models import CatalogNomenclatureItem, CatalogNomenclatureMapping, utc_now
from services.nomenclature_mapper import normalize_item_name


@dataclass(frozen=True)
class CatalogItemRecord:
    id: str
    canonical_name: str
    normalized_name: str
    sku: str
    category: str
    brand: str


class NomenclatureStore:
    def __init__(self, database_url: str | None = None, engine: Engine | None = None):
        self._engine = engine
        if self._engine is None:
            try:
                self._engine = create_coman_engine(database_url)
            except ComanDatabaseConfigurationError:
                self._engine = None
        self._session_factory = (
            sessionmaker(bind=self._engine, expire_on_commit=False, future=True)
            if self._engine is not None
            else None
        )

    @property
    def configured(self) -> bool:
        return self._session_factory is not None

    def replace_catalog(self, organization_id: str, rows: Iterable[dict], actor: str) -> int:
        if not self._session_factory:
            raise ComanDatabaseConfigurationError("Nomenclature storage is not configured.")
        clean_rows = []
        for row in rows:
            canonical_name = str(row.get("canonical_name") or "").strip()
            normalized_name = normalize_item_name(canonical_name)
            if canonical_name and normalized_name:
                clean_rows.append(
                    {
                        "organization_id": organization_id,
                        "source_system": "dutchie",
                        "canonical_name": canonical_name,
                        "normalized_name": normalized_name,
                        "sku": str(row.get("sku") or "").strip(),
                        "category": str(row.get("category") or "").strip(),
                        "brand": str(row.get("brand") or "").strip(),
                        "active": True,
                        "imported_by": actor,
                        "updated_at": utc_now(),
                    }
                )
        with self._session_factory.begin() as session:
            session.query(CatalogNomenclatureItem).filter(
                CatalogNomenclatureItem.organization_id == organization_id,
                CatalogNomenclatureItem.source_system == "dutchie",
            ).update({"active": False, "updated_at": utc_now()}, synchronize_session=False)
            for row in clean_rows:
                if session.bind.dialect.name == "postgresql":
                    statement = pg_insert(CatalogNomenclatureItem).values(**row)
                    statement = statement.on_conflict_do_update(
                        constraint="uq_catalog_nomenclature_org_source_name",
                        set_={
                            "canonical_name": statement.excluded.canonical_name,
                            "sku": statement.excluded.sku,
                            "category": statement.excluded.category,
                            "brand": statement.excluded.brand,
                            "active": True,
                            "imported_by": actor,
                            "updated_at": utc_now(),
                        },
                    )
                    session.execute(statement)
                else:
                    existing = session.scalar(
                        select(CatalogNomenclatureItem).where(
                            CatalogNomenclatureItem.organization_id == organization_id,
                            CatalogNomenclatureItem.source_system == "dutchie",
                            CatalogNomenclatureItem.normalized_name == row["normalized_name"],
                        )
                    )
                    if existing:
                        for key in ("canonical_name", "sku", "category", "brand", "active", "imported_by", "updated_at"):
                            setattr(existing, key, row[key])
                    else:
                        session.add(CatalogNomenclatureItem(**row))
        return len(clean_rows)

    def list_catalog(self, organization_id: str) -> list[CatalogItemRecord]:
        if not self._session_factory:
            return []
        with self._session_factory() as session:
            rows = session.scalars(
                select(CatalogNomenclatureItem)
                .where(
                    CatalogNomenclatureItem.organization_id == organization_id,
                    CatalogNomenclatureItem.source_system == "dutchie",
                    CatalogNomenclatureItem.active.is_(True),
                )
                .order_by(CatalogNomenclatureItem.canonical_name)
            ).all()
            return [
                CatalogItemRecord(row.id, row.canonical_name, row.normalized_name, row.sku, row.category, row.brand)
                for row in rows
            ]

    def learned_mappings(self, organization_id: str) -> dict[str, tuple[str, str | None]]:
        if not self._session_factory:
            return {}
        with self._session_factory() as session:
            rows = session.execute(
                select(CatalogNomenclatureMapping, CatalogNomenclatureItem)
                .join(
                    CatalogNomenclatureItem,
                    CatalogNomenclatureItem.id == CatalogNomenclatureMapping.catalog_item_id,
                )
                .where(
                    CatalogNomenclatureMapping.organization_id == organization_id,
                    CatalogNomenclatureMapping.status == "confirmed",
                    CatalogNomenclatureItem.active.is_(True),
                )
            ).all()
            return {
                mapping.source_normalized_name: (catalog_item.canonical_name, catalog_item.id)
                for mapping, catalog_item in rows
            }

    def confirm_mappings(self, organization_id: str, rows: Iterable[dict], actor: str) -> int:
        if not self._session_factory:
            raise ComanDatabaseConfigurationError("Nomenclature storage is not configured.")
        saved = 0
        with self._session_factory.begin() as session:
            for row in rows:
                source_name = str(row.get("Original METRC Item") or "").strip()
                correct_name = str(row.get("Correct Item Name") or "").strip()
                if not source_name or not correct_name:
                    continue
                source_normalized = normalize_item_name(source_name)
                catalog_item = session.scalar(
                    select(CatalogNomenclatureItem).where(
                        CatalogNomenclatureItem.organization_id == organization_id,
                        CatalogNomenclatureItem.source_system == "dutchie",
                        CatalogNomenclatureItem.canonical_name == correct_name,
                        CatalogNomenclatureItem.active.is_(True),
                    )
                )
                if not catalog_item:
                    raise ValueError(
                        f"The selected name is not in this organization's active Dutchie catalog: {correct_name}"
                    )
                catalog_item_id = catalog_item.id
                existing = session.scalar(
                    select(CatalogNomenclatureMapping).where(
                        CatalogNomenclatureMapping.organization_id == organization_id,
                        CatalogNomenclatureMapping.source_system == "metrc",
                        CatalogNomenclatureMapping.source_normalized_name == source_normalized,
                    )
                )
                if existing:
                    existing.source_item_name = source_name
                    existing.correct_name = correct_name
                    existing.catalog_item_id = catalog_item_id
                    existing.status = "confirmed"
                    existing.confirmed_by = actor
                    existing.confirmed_at = utc_now()
                    existing.updated_at = utc_now()
                else:
                    session.add(
                        CatalogNomenclatureMapping(
                            organization_id=organization_id,
                            source_system="metrc",
                            source_item_name=source_name,
                            source_normalized_name=source_normalized,
                            correct_name=correct_name,
                            catalog_item_id=catalog_item_id,
                            status="confirmed",
                            confirmed_by=actor,
                            confirmed_at=utc_now(),
                        )
                    )
                saved += 1
        return saved
