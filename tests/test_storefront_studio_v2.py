from __future__ import annotations

import base64
from pathlib import Path

import pytest
from sqlalchemy import create_engine

from modules.coman.models import Base
from modules.coman.repository import ComanRepository
from modules.commerce_storefronts.studio import CommerceStorefrontStudioService
from modules.commerce_storefronts.wholesale_service import WholesaleCommerceStorefrontService

ROOT = Path(__file__).resolve().parents[1]


def _setup():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    repo = ComanRepository(engine)
    organization = repo.create_organization("Storefront Studio QA")
    facility = repo.create_facility(organization.id, "Wholesale", "WHOLESALE")
    wholesale = WholesaleCommerceStorefrontService(engine)
    wholesale.upsert_storefront(
        organization_id=organization.id,
        facility_id=facility.id,
        actor="admin",
        display_name="Studio Brand",
        subdomain="studio-brand",
        accent_color="#8abf55",
        published=True,
    )
    return engine, repo, organization, facility, wholesale, CommerceStorefrontStudioService(engine)


def test_studio_draft_is_private_until_explicit_publish_and_core_lab_stats_cannot_be_removed():
    _, _, organization, facility, _, studio = _setup()
    initial = studio.snapshot(organization.id, facility.id)
    assert initial["draft_dirty"] is False
    assert initial["published"]["theme_preset"] == "clean"

    draft = dict(initial["draft"])
    draft.update(
        {
            "theme_preset": "dark",
            "card_style": "premium",
            "announcement_enabled": True,
            "announcement_text": "Fresh wholesale drop",
            "show_about": True,
            "about_heading": "Built by the grow team",
            "visible_stats": ["batch", "coa"],
        }
    )
    saved = studio.save_draft(
        organization_id=organization.id,
        facility_id=facility.id,
        actor="admin",
        design=draft,
    )
    assert saved["draft_dirty"] is True
    assert saved["draft"]["theme_preset"] == "dark"
    assert saved["draft"]["visible_stats"][:3] == ["thca", "tac", "terpenes"]

    # The customer-facing storefront remains on the last published design.
    assert studio.public_design("studio-brand")["theme_preset"] == "clean"

    published = studio.publish_draft(organization_id=organization.id, facility_id=facility.id, actor="admin")
    assert published["draft_dirty"] is False
    assert published["published"]["theme_preset"] == "dark"
    assert studio.public_design("studio-brand")["card_style"] == "premium"


def test_studio_assets_are_tenant_scoped_signature_checked_and_public_only_when_published():
    _, repo, organization, facility, wholesale, studio = _setup()
    png = b"\x89PNG\r\n\x1a\n" + b"safe-image-bytes"
    asset = studio.upload_asset(
        organization_id=organization.id,
        facility_id=facility.id,
        actor="admin",
        kind="logo",
        file_name="logo.png",
        content_type="image/png",
        content_base64=base64.b64encode(png).decode("ascii"),
    )
    assert asset["kind"] == "logo"
    assert asset["byte_size"] == len(png)

    draft = studio.snapshot(organization.id, facility.id)["draft"]
    draft["logo_asset_id"] = asset["id"]
    studio.save_draft(organization_id=organization.id, facility_id=facility.id, actor="admin", design=draft)
    with pytest.raises(ValueError, match="not part of the published design"):
        studio.get_public_asset(slug="studio-brand", asset_id=asset["id"])

    studio.publish_draft(organization_id=organization.id, facility_id=facility.id, actor="admin")
    public_asset = studio.get_public_asset(slug="studio-brand", asset_id=asset["id"])
    assert public_asset["content"] == png

    other_facility = repo.create_facility(organization.id, "Other Wholesale", "WHOLESALE-2")
    wholesale.upsert_storefront(
        organization_id=organization.id,
        facility_id=other_facility.id,
        actor="admin",
        display_name="Other Brand",
        subdomain="other-studio-brand",
        published=True,
    )
    with pytest.raises(ValueError, match="not found"):
        studio.get_admin_asset(organization_id=organization.id, facility_id=other_facility.id, asset_id=asset["id"])

    with pytest.raises(ValueError, match="contents do not match"):
        studio.upload_asset(
            organization_id=organization.id,
            facility_id=facility.id,
            actor="admin",
            kind="hero",
            file_name="fake.png",
            content_type="image/png",
            content_base64=base64.b64encode(b"not-a-png").decode("ascii"),
        )


def test_studio_rejects_arbitrary_layout_and_asset_references():
    engine, _, organization, facility, _, studio = _setup()
    draft = studio.snapshot(organization.id, facility.id)["draft"]
    draft["section_order"] = ["hero", "arbitrary-html", "catalog"]
    with pytest.raises(ValueError, match="unsupported section"):
        studio.save_draft(organization_id=organization.id, facility_id=facility.id, actor="admin", design=draft)

    clean = studio.snapshot(organization.id, facility.id)["draft"]
    clean["logo_asset_id"] = "00000000-0000-0000-0000-000000000000"
    with pytest.raises(ValueError, match="does not belong"):
        studio.save_draft(organization_id=organization.id, facility_id=facility.id, actor="admin", design=clean)
    engine.dispose()


def test_storefront_studio_frontend_and_router_contracts_are_present():
    manager = (ROOT / "frontend/src/components/CommerceStorefrontManager.tsx").read_text(encoding="utf-8")
    page = (ROOT / "frontend/src/pages/StorefrontPage.tsx").read_text(encoding="utf-8")
    css = (ROOT / "frontend/src/storefront-studio-v2.css").read_text(encoding="utf-8")
    router = (ROOT / "backend/app/routers/storefronts.py").read_text(encoding="utf-8")

    for token in (
        "DOOBIECOMMERCE · STOREFRONT STUDIO",
        "Save design draft",
        "Publish design",
        "Desktop",
        "Tablet",
        "Mobile",
        "THCA, TAC and Terps",
        "Theme preset",
        "Card style",
        "Brand assets",
        "Page sections",
        "Product card fields",
    ):
        assert token in manager
    for token in ("studio.section_order", "studio.theme_preset", "studio.card_style", "studio.visible_stats", "studio.announcement_enabled", "favicon_asset_path"):
        assert token in page
    for route in ('@router.get("/studio")', '@router.post("/studio")', '@router.post("/studio/publish")', '@router.post("/studio/assets")', '@public_router.get("/{slug}/assets/{asset_id}")'):
        assert route in router
    assert ".storefront-studio-preview.desktop" in css
    assert ".storefront-studio-preview.tablet" in css
    assert ".storefront-studio-preview.mobile" in css


def test_storefront_studio_migration_extends_0051_without_modifying_it():
    migration = (ROOT / "migrations/versions/0052_storefront_studio.py").read_text(encoding="utf-8")
    assert 'revision = "0052_storefront_studio"' in migration
    assert 'down_revision = "0051_storefront_order_terms"' in migration
    assert "commerce_storefront_studio" in migration
    assert "commerce_storefront_assets" in migration
