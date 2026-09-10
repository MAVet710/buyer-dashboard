from __future__ import annotations

import hashlib
from types import SimpleNamespace

from sqlalchemy import create_engine

from backend.app.services.buyer_model_cache import install_buyer_model_cache
from modules.coman.models import Base, Facility, Organization
from modules.data_hub_repository import DataHubRepository


def _publish(repository: DataHubRepository, dataset_key: str, payload: bytes) -> None:
    repository.publish_source(
        organization_id="org-a",
        facility_id="facility-a",
        dataset_key=dataset_key,
        dataset_label=dataset_key.replace("_", " ").title(),
        cache_key=f"cache-{dataset_key}",
        filename=f"{dataset_key}.csv",
        fingerprint=hashlib.sha256(payload).hexdigest(),
        payload=payload,
    )


def test_buyer_model_cache_reuses_same_source_fingerprints_and_invalidates_on_publish(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'buyer-cache.db'}", future=True)
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(
            Organization.__table__.insert(),
            [{"id": "org-a", "name": "A", "slug": "a", "active": True}],
        )
        connection.execute(
            Facility.__table__.insert(),
            [{
                "id": "facility-a",
                "organization_id": "org-a",
                "name": "A Retail",
                "code": "AR",
                "timezone_name": "America/New_York",
                "active": True,
            }],
        )

    repository = DataHubRepository(engine)
    _publish(repository, "inventory", b"Product,Category,On Hand\nBlue Dream,Flower,12\n")
    _publish(repository, "product_sales", b"Product,Category,Units Sold\nBlue Dream,Flower,4\n")

    calls: list[int] = []

    def original(context, model_engine, target_doh, velocity_adjustment, sales_days):
        del context, model_engine, target_doh, velocity_adjustment, sales_days
        calls.append(1)
        return ("result", len(calls))

    module = SimpleNamespace(_model=original)
    cached = install_buyer_model_cache(module)
    context = SimpleNamespace(
        organization_id="org-a",
        facility_id="facility-a",
        data_mode="Uploads",
    )

    first = cached(context, engine, 21, 0.5, 60)
    second = cached(context, engine, 21, 0.5, 60)
    assert first == second
    assert len(calls) == 1

    _publish(repository, "product_sales", b"Product,Category,Units Sold\nBlue Dream,Flower,8\n")
    third = cached(context, engine, 21, 0.5, 60)
    assert third != first
    assert len(calls) == 2
