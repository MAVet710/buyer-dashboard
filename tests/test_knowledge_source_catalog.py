from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.build_knowledge_bundle import validate_manifest


MANIFEST = Path(__file__).resolve().parents[1] / "knowledge_sources" / "approved_sources.json"


def load_manifest() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def test_approved_source_catalog_is_valid_and_unique():
    payload = load_manifest()
    allowed_domains, sources = validate_manifest(payload)
    assert {"masscannabiscontrol.com", "www.metrc.com", "support.dutchie.com"} <= allowed_domains
    keys = [source["key"] for source in sources]
    assert len(keys) == len(set(keys))
    assert len(keys) >= 18


def test_massachusetts_regulatory_sources_are_facility_scoped_and_current_baseline_is_present():
    sources = {source["key"]: source for source in load_manifest()["sources"] if source.get("active", True)}
    adult = sources["ma_935_cmr_500_current"]
    medical = sources["ma_935_cmr_501_current"]
    for source in (adult, medical):
        assert source["authority_level"] == 1
        assert source["source_type"] == "regulation"
        assert source["jurisdiction"] == "MA"
        assert source["effective_date"] == "2026-06-18"
        assert source["facility_scope"] is True
        assert source["global_scope"] is False
    assert "2026-06-18" in adult["version"]
    assert "2026-06-18" in medical["version"]


def test_active_catalog_does_not_label_draft_or_archived_material_as_current():
    for source in load_manifest()["sources"]:
        if not source.get("active", True):
            continue
        identity = " ".join(str(source.get(key) or "") for key in ("key", "title", "version", "url")).casefold()
        assert "draft" not in identity
        assert "archived" not in identity


def test_vendor_material_cannot_be_misclassified_as_regulatory_authority():
    for source in load_manifest()["sources"]:
        if source["source"] in {"Metrc", "Dutchie Help Center"}:
            assert source["authority_level"] == 3
            assert source["source_type"] in {"metrc", "dutchie"}


def test_catalog_rejects_host_prefix_and_plain_http_attacks():
    payload = load_manifest()
    hostile = json.loads(json.dumps(payload))
    hostile["sources"][0]["url"] = "https://masscannabiscontrol.com.evil.example/fake.pdf"
    with pytest.raises(ValueError, match="not allowlisted"):
        validate_manifest(hostile)

    insecure = json.loads(json.dumps(payload))
    insecure["sources"][0]["url"] = "http://masscannabiscontrol.com/fake.pdf"
    with pytest.raises(ValueError, match="not allowlisted"):
        validate_manifest(insecure)


def test_catalog_rejects_bad_authority_and_format():
    payload = load_manifest()
    bad_authority = json.loads(json.dumps(payload))
    bad_authority["sources"][0]["authority_level"] = 99
    with pytest.raises(ValueError, match="authority"):
        validate_manifest(bad_authority)

    bad_format = json.loads(json.dumps(payload))
    bad_format["sources"][0]["format"] = "exe"
    with pytest.raises(ValueError, match="format"):
        validate_manifest(bad_format)
