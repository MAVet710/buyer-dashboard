"""Controlled Storefront Studio draft/publish and media-asset service."""

from __future__ import annotations

import base64
import hashlib
import json
import re
from typing import Any

from sqlalchemy import Engine, select
from sqlalchemy.orm import sessionmaker

from modules.coman.models import utc_now

from .models import CommerceStorefrontAsset, CommerceStorefrontStudio
from .service import CommerceStorefrontService

_THEME_PRESETS = {"clean", "premium", "dark", "western", "boutique"}
_FONT_PRESETS = {"modern", "editorial", "rounded", "classic"}
_CARD_STYLES = {"collectible", "premium", "compact", "clean"}
_CARD_IMAGE_STYLES = {"cover", "contain", "framed"}
_SECTIONS = {"hero", "featured", "catalog", "about", "contact"}
_OPTIONAL_STATS = {"batch", "coa", "harvest_date", "production_date", "expiration_date", "available", "sku", "case_quantity"}
_CORE_STATS = ["thca", "tac", "terpenes"]
_BADGES = {"featured", "new_drop", "limited", "staff_pick", "high_terps"}
_ASSET_KINDS = {"logo", "hero", "favicon"}
_ALLOWED_IMAGE_TYPES = {"image/png", "image/jpeg", "image/webp"}
_ASSET_MAX_BYTES = {"logo": 1 * 1024 * 1024, "hero": 4 * 1024 * 1024, "favicon": 256 * 1024}


def _json(value: Any) -> str:
    return json.dumps(value, default=str, sort_keys=True, separators=(",", ":"))


def _load(value: str, fallback: Any) -> Any:
    try:
        parsed = json.loads(value or "")
    except (TypeError, ValueError, json.JSONDecodeError):
        return fallback
    return parsed


def _hex(value: Any, fallback: str) -> str:
    text = str(value or fallback).strip()
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", text):
        raise ValueError("Storefront Studio colors must use six-digit hex values such as #8abf55.")
    return text.lower()


def _clean_text(value: Any, maximum: int) -> str:
    return str(value or "").strip()[:maximum]


def _signature_matches(content_type: str, content: bytes) -> bool:
    if content_type == "image/png":
        return content.startswith(b"\x89PNG\r\n\x1a\n")
    if content_type == "image/jpeg":
        return content.startswith(b"\xff\xd8\xff")
    if content_type == "image/webp":
        return len(content) >= 12 and content[:4] == b"RIFF" and content[8:12] == b"WEBP"
    return False


def default_studio_design(accent_color: str = "#8abf55") -> dict[str, Any]:
    return {
        "theme_preset": "clean",
        "font_preset": "modern",
        "card_style": "collectible",
        "card_image_style": "cover",
        "accent_color": str(accent_color or "#8abf55").lower(),
        "secondary_color": "#173127",
        "surface_color": "#f7f5ef",
        "announcement_enabled": False,
        "announcement_text": "",
        "show_hero": True,
        "show_featured": True,
        "show_about": False,
        "about_heading": "Brand story",
        "about_body": "",
        "show_contact": True,
        "show_footer": True,
        "section_order": ["hero", "featured", "catalog", "about", "contact"],
        "visible_stats": [*_CORE_STATS, "batch", "coa", "harvest_date", "available"],
        "badges": ["featured", "new_drop", "limited"],
        "logo_asset_id": "",
        "hero_asset_id": "",
        "favicon_asset_id": "",
    }


def normalize_studio_design(raw: Any, *, accent_color: str = "#8abf55") -> dict[str, Any]:
    value = raw if isinstance(raw, dict) else {}
    base = default_studio_design(accent_color)

    theme = str(value.get("theme_preset") or base["theme_preset"]).strip().casefold()
    font = str(value.get("font_preset") or base["font_preset"]).strip().casefold()
    card = str(value.get("card_style") or base["card_style"]).strip().casefold()
    image_style = str(value.get("card_image_style") or base["card_image_style"]).strip().casefold()
    if theme not in _THEME_PRESETS:
        raise ValueError("Unknown Storefront Studio theme preset.")
    if font not in _FONT_PRESETS:
        raise ValueError("Unknown Storefront Studio font preset.")
    if card not in _CARD_STYLES:
        raise ValueError("Unknown Storefront Studio card style.")
    if image_style not in _CARD_IMAGE_STYLES:
        raise ValueError("Unknown Storefront Studio card image style.")

    raw_order = value.get("section_order", base["section_order"])
    if not isinstance(raw_order, list):
        raise ValueError("Storefront section order must be a list.")
    order: list[str] = []
    for item in raw_order:
        section = str(item or "").strip().casefold()
        if section not in _SECTIONS:
            raise ValueError("Storefront section order contains an unsupported section.")
        if section not in order:
            order.append(section)
    for section in base["section_order"]:
        if section not in order:
            order.append(section)
    if "catalog" not in order:
        raise ValueError("The storefront catalog section cannot be removed.")

    raw_stats = value.get("visible_stats", base["visible_stats"])
    if not isinstance(raw_stats, list):
        raise ValueError("Visible storefront card stats must be a list.")
    stats = [*_CORE_STATS]
    for item in raw_stats:
        stat = str(item or "").strip().casefold()
        if stat in _CORE_STATS or stat in _OPTIONAL_STATS:
            if stat not in stats:
                stats.append(stat)
        elif stat:
            raise ValueError("Storefront card stats contain an unsupported field.")

    raw_badges = value.get("badges", base["badges"])
    if not isinstance(raw_badges, list):
        raise ValueError("Storefront badge rules must be a list.")
    badges: list[str] = []
    for item in raw_badges:
        badge = str(item or "").strip().casefold()
        if badge not in _BADGES:
            raise ValueError("Storefront badge rules contain an unsupported badge.")
        if badge not in badges:
            badges.append(badge)

    return {
        "theme_preset": theme,
        "font_preset": font,
        "card_style": card,
        "card_image_style": image_style,
        "accent_color": _hex(value.get("accent_color"), base["accent_color"]),
        "secondary_color": _hex(value.get("secondary_color"), base["secondary_color"]),
        "surface_color": _hex(value.get("surface_color"), base["surface_color"]),
        "announcement_enabled": bool(value.get("announcement_enabled", base["announcement_enabled"])),
        "announcement_text": _clean_text(value.get("announcement_text", base["announcement_text"]), 240),
        "show_hero": bool(value.get("show_hero", base["show_hero"])),
        "show_featured": bool(value.get("show_featured", base["show_featured"])),
        "show_about": bool(value.get("show_about", base["show_about"])),
        "about_heading": _clean_text(value.get("about_heading", base["about_heading"]), 120),
        "about_body": _clean_text(value.get("about_body", base["about_body"]), 4000),
        "show_contact": bool(value.get("show_contact", base["show_contact"])),
        "show_footer": bool(value.get("show_footer", base["show_footer"])),
        "section_order": order,
        "visible_stats": stats,
        "badges": badges,
        "logo_asset_id": _clean_text(value.get("logo_asset_id", ""), 36),
        "hero_asset_id": _clean_text(value.get("hero_asset_id", ""), 36),
        "favicon_asset_id": _clean_text(value.get("favicon_asset_id", ""), 36),
    }


class CommerceStorefrontStudioService:
    def __init__(self, engine: Engine):
        self.engine = engine
        self._sessions = sessionmaker(bind=engine, expire_on_commit=False, future=True)
        self._storefronts = CommerceStorefrontService(engine)

    def _storefront(self, organization_id: str, facility_id: str):
        row = self._storefronts.get_storefront(organization_id, facility_id)
        if not row:
            raise ValueError("Create the storefront before opening Storefront Studio.")
        return row

    def _row(self, storefront_id: str) -> CommerceStorefrontStudio | None:
        with self._sessions() as session:
            return session.scalar(select(CommerceStorefrontStudio).where(CommerceStorefrontStudio.storefront_id == storefront_id))

    def snapshot(self, organization_id: str, facility_id: str) -> dict[str, Any]:
        storefront = self._storefront(organization_id, facility_id)
        studio = self._row(storefront.id)
        fallback = default_studio_design(storefront.accent_color)
        draft = normalize_studio_design(_load(studio.draft_json, fallback) if studio else fallback, accent_color=storefront.accent_color)
        published = normalize_studio_design(_load(studio.published_json, fallback) if studio and studio.published_json not in ("", "{}") else fallback, accent_color=storefront.accent_color)
        return {
            "draft": self._with_asset_paths(storefront.slug, draft),
            "published": self._with_asset_paths(storefront.slug, published),
            "draft_dirty": _json(draft) != _json(published),
            "published_at": studio.published_at if studio else None,
            "theme_presets": sorted(_THEME_PRESETS),
            "font_presets": sorted(_FONT_PRESETS),
            "card_styles": sorted(_CARD_STYLES),
            "card_image_styles": sorted(_CARD_IMAGE_STYLES),
            "optional_stats": sorted(_OPTIONAL_STATS),
            "badge_rules": sorted(_BADGES),
        }

    def save_draft(self, *, organization_id: str, facility_id: str, actor: str, design: dict[str, Any]) -> dict[str, Any]:
        storefront = self._storefront(organization_id, facility_id)
        normalized = normalize_studio_design(design, accent_color=storefront.accent_color)
        self._validate_asset_refs(storefront.id, organization_id, facility_id, normalized)
        with self._sessions.begin() as session:
            row = session.scalar(select(CommerceStorefrontStudio).where(CommerceStorefrontStudio.storefront_id == storefront.id))
            if row is None:
                row = CommerceStorefrontStudio(
                    organization_id=organization_id,
                    facility_id=facility_id,
                    storefront_id=storefront.id,
                    draft_json=_json(normalized),
                    published_json="{}",
                    updated_by=actor,
                )
                session.add(row)
            else:
                row.draft_json = _json(normalized)
                row.updated_by = actor
            session.flush()
        return self.snapshot(organization_id, facility_id)

    def publish_draft(self, *, organization_id: str, facility_id: str, actor: str) -> dict[str, Any]:
        storefront = self._storefront(organization_id, facility_id)
        with self._sessions.begin() as session:
            row = session.scalar(select(CommerceStorefrontStudio).where(CommerceStorefrontStudio.storefront_id == storefront.id))
            if row is None:
                design = default_studio_design(storefront.accent_color)
                row = CommerceStorefrontStudio(
                    organization_id=organization_id,
                    facility_id=facility_id,
                    storefront_id=storefront.id,
                    draft_json=_json(design),
                    published_json=_json(design),
                    published_at=utc_now(),
                    updated_by=actor,
                )
                session.add(row)
            else:
                draft = normalize_studio_design(_load(row.draft_json, {}), accent_color=storefront.accent_color)
                self._validate_asset_refs(storefront.id, organization_id, facility_id, draft, session=session)
                row.published_json = _json(draft)
                row.published_at = utc_now()
                row.updated_by = actor
            session.flush()
        return self.snapshot(organization_id, facility_id)

    def public_design(self, slug: str) -> dict[str, Any]:
        storefront = self._storefronts.resolve_public(slug)
        studio = self._row(storefront.id)
        fallback = default_studio_design(storefront.accent_color)
        raw = _load(studio.published_json, fallback) if studio and studio.published_json not in ("", "{}") else fallback
        design = normalize_studio_design(raw, accent_color=storefront.accent_color)
        return self._with_asset_paths(storefront.slug, design)

    def upload_asset(
        self,
        *,
        organization_id: str,
        facility_id: str,
        actor: str,
        kind: str,
        file_name: str,
        content_type: str,
        content_base64: str,
    ) -> dict[str, Any]:
        storefront = self._storefront(organization_id, facility_id)
        clean_kind = str(kind or "").strip().casefold()
        if clean_kind not in _ASSET_KINDS:
            raise ValueError("Storefront asset kind must be logo, hero, or favicon.")
        clean_type = str(content_type or "").strip().casefold()
        if clean_type not in _ALLOWED_IMAGE_TYPES:
            raise ValueError("Storefront assets must be PNG, JPEG, or WebP images.")
        raw = str(content_base64 or "").strip()
        if raw.casefold().startswith("data:") and "," in raw:
            raw = raw.split(",", 1)[1]
        try:
            content = base64.b64decode(raw, validate=True)
        except Exception as exc:
            raise ValueError("Storefront asset is not valid base64 image data.") from exc
        if not content:
            raise ValueError("Storefront asset is empty.")
        if len(content) > _ASSET_MAX_BYTES[clean_kind]:
            limits = {"logo": "1 MB", "hero": "4 MB", "favicon": "256 KB"}
            raise ValueError(f"Storefront {clean_kind} image must be {limits[clean_kind]} or smaller.")
        if not _signature_matches(clean_type, content):
            raise ValueError("Storefront asset contents do not match the declared image type.")
        clean_name = re.sub(r"[^A-Za-z0-9._ -]+", "_", str(file_name or f"{clean_kind}-image").strip())[:255] or f"{clean_kind}-image"
        with self._sessions.begin() as session:
            row = CommerceStorefrontAsset(
                organization_id=organization_id,
                facility_id=facility_id,
                storefront_id=storefront.id,
                kind=clean_kind,
                file_name=clean_name,
                content_type=clean_type,
                content_bytes=content,
                byte_size=len(content),
                sha256=hashlib.sha256(content).hexdigest(),
                created_by=actor,
            )
            session.add(row)
            session.flush()
            return self._asset_meta(storefront.slug, row)

    def get_admin_asset(self, *, organization_id: str, facility_id: str, asset_id: str) -> dict[str, Any]:
        storefront = self._storefront(organization_id, facility_id)
        with self._sessions() as session:
            row = session.get(CommerceStorefrontAsset, asset_id)
            if not row or row.organization_id != organization_id or row.facility_id != facility_id or row.storefront_id != storefront.id:
                raise ValueError("Storefront asset was not found in this facility.")
            return {**self._asset_meta(storefront.slug, row), "content": bytes(row.content_bytes)}

    def get_public_asset(self, *, slug: str, asset_id: str) -> dict[str, Any]:
        storefront = self._storefronts.resolve_public(slug)
        design = self.public_design(slug)
        published_ids = {design.get("logo_asset_id", ""), design.get("hero_asset_id", ""), design.get("favicon_asset_id", "")}
        if asset_id not in published_ids:
            raise ValueError("Storefront asset is not part of the published design.")
        with self._sessions() as session:
            row = session.get(CommerceStorefrontAsset, asset_id)
            if not row or row.storefront_id != storefront.id:
                raise ValueError("Storefront asset was not found.")
            return {**self._asset_meta(storefront.slug, row), "content": bytes(row.content_bytes)}

    def _validate_asset_refs(
        self,
        storefront_id: str,
        organization_id: str,
        facility_id: str,
        design: dict[str, Any],
        *,
        session=None,
    ) -> None:
        owns_session = session is None
        db = session or self._sessions()
        try:
            for field, expected_kind in (("logo_asset_id", "logo"), ("hero_asset_id", "hero"), ("favicon_asset_id", "favicon")):
                asset_id = str(design.get(field) or "")
                if not asset_id:
                    continue
                asset = db.get(CommerceStorefrontAsset, asset_id)
                if not asset or asset.organization_id != organization_id or asset.facility_id != facility_id or asset.storefront_id != storefront_id or asset.kind != expected_kind:
                    raise ValueError(f"{expected_kind.title()} asset does not belong to this storefront.")
        finally:
            if owns_session:
                db.close()

    @staticmethod
    def _asset_meta(slug: str, row: CommerceStorefrontAsset) -> dict[str, Any]:
        return {
            "id": row.id,
            "kind": row.kind,
            "file_name": row.file_name,
            "content_type": row.content_type,
            "byte_size": row.byte_size,
            "sha256": row.sha256,
            "public_path": f"/api/v1/commerce-storefronts/{slug}/assets/{row.id}",
            "admin_path": f"/api/v1/storefronts/studio/assets/{row.id}",
        }

    @staticmethod
    def _with_asset_paths(slug: str, design: dict[str, Any]) -> dict[str, Any]:
        result = dict(design)
        for prefix in ("logo", "hero", "favicon"):
            asset_id = str(result.get(f"{prefix}_asset_id") or "")
            result[f"{prefix}_asset_path"] = f"/api/v1/commerce-storefronts/{slug}/assets/{asset_id}" if asset_id else ""
        return result
