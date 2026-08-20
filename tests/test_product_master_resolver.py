from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from modules.coman.models import Base, Organization, Product, TradePartner
from modules.product_master import ProductMasterRepository
from modules.product_master.resolver import resolve_product_master, search_product_master


def _environment():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    with sessions.begin() as session:
        org = Organization(name="Buyer Dash", slug="buyer-dash-resolver")
        session.add(org)
        session.flush()
        product = Product(
            organization_id=org.id,
            sku="GMO-PR-1G",
            name="GMO Pre-Roll 1g",
            item_type="finished_good",
            base_unit="unit",
            unit_cost=3.5,
            retail_price=14.0,
            upc="012345678901",
        )
        vendor = TradePartner(
            organization_id=org.id,
            name="Acme Cannabis Supply",
            partner_type="vendor",
        )
        session.add_all([product, vendor])
        session.flush()
        ids = {"org": org.id, "product": product.id, "vendor": vendor.id}
    return engine, ids


def _mastered_product():
    engine, ids = _environment()
    repo = ProductMasterRepository(engine)
    repo.update_profile(
        ids["org"],
        ids["product"],
        actor="buyer",
        brand="House Brand",
        category="Pre-Rolls",
        subcategory="Singles",
        strain="GMO",
        manufacturer="Buyer Dash Manufacturing",
        product_format="1g pre-roll",
    )
    repo.link_vendor(
        ids["org"],
        ids["product"],
        ids["vendor"],
        actor="buyer",
        vendor_sku="ACME-GMO-001",
        is_primary=True,
        lead_time_days=5,
        minimum_order_quantity=24,
        case_pack=12,
    )
    repo.add_alias(
        ids["org"],
        ids["product"],
        "GMO PR 1 Gram",
        actor="buyer",
        source="dutchie_import",
    )
    repo.map_external(
        ids["org"],
        ids["product"],
        system_name="metrc",
        external_id="ITEM-123",
        external_name="GMO / Pre-Roll / 1g",
        actor="buyer",
    )
    repo.record_value(
        ids["org"],
        ids["product"],
        value_type="unit_cost",
        amount=3.75,
        actor="buyer",
        partner_id=ids["vendor"],
        source="purchase_order",
        source_reference="PO-1001",
    )
    return engine, ids


def test_resolver_finds_canonical_product_by_name_sku_alias_and_external_id():
    engine, ids = _mastered_product()

    by_name = resolve_product_master(engine, ids["org"], product_name="GMO Pre-Roll 1g")
    by_sku = resolve_product_master(engine, ids["org"], sku="gmo-pr-1g")
    by_alias = resolve_product_master(engine, ids["org"], product_name="gmo pr 1 gram")
    by_external = resolve_product_master(engine, ids["org"], product_name="ITEM-123")

    for row in (by_name, by_sku, by_alias, by_external):
        assert row["canonical_product_id"] == ids["product"]
        assert row["product_name"] == "GMO Pre-Roll 1g"
        assert row["primary_vendor"] == "Acme Cannabis Supply"
        assert row["vendor_lead_time_days"] == 5
        assert row["vendor_moq"] == 24
        assert row["vendor_case_pack"] == 12
        assert row["unit_cost"] == 3.75
        assert row["value_history"][0]["source_reference"] == "PO-1001"


def test_master_search_handles_punctuation_profile_vendor_and_external_terms():
    engine, ids = _mastered_product()

    queries = (
        "gmo pre roll",
        "house brand",
        "pre rolls",
        "acme cannabis",
        "ACME-GMO-001",
        "ITEM-123",
        "GMO / Pre-Roll",
        "012345678901",
    )
    for query in queries:
        results = search_product_master(engine, ids["org"], query, limit=5)
        assert results, query
        assert results[0]["canonical_product_id"] == ids["product"]


def test_master_search_is_organization_scoped():
    engine, ids = _mastered_product()
    sessions = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    with sessions.begin() as session:
        other = Organization(name="Other Tenant", slug="other-resolver-tenant")
        session.add(other)
        session.flush()
        other_id = other.id

    assert search_product_master(engine, other_id, "GMO", limit=5) == []
    assert resolve_product_master(engine, other_id, product_name="GMO Pre-Roll 1g") == {}
