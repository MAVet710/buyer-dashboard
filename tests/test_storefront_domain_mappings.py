from __future__ import annotations

from pathlib import Path

import pytest

from scripts.validate_storefront_domains import load_domains


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "deploy" / "storefront-domains.txt"
WORKFLOW = (ROOT / ".github" / "workflows" / "storefront-domain-mappings.yml").read_text(encoding="utf-8")


def test_cowboy_kush_is_an_explicit_approved_storefront_domain():
    assert load_domains(CONFIG) == ["cowboykush.doobielogic.io"]


@pytest.mark.parametrize(
    "value",
    [
        "*.doobielogic.io",
        "ops.doobielogic.io",
        "api.doobielogic.io",
        "www.doobielogic.io",
        "nested.store.doobielogic.io",
        "cowboykush.example.com",
        "https://cowboykush.doobielogic.io",
    ],
)
def test_storefront_domain_validator_rejects_wildcards_reserved_and_noncanonical_hosts(tmp_path: Path, value: str):
    path = tmp_path / "domains.txt"
    path.write_text(value + "\n", encoding="utf-8")
    with pytest.raises(ValueError):
        load_domains(path)


def test_storefront_domain_workflow_validates_for_pc_hosted_tunnel_routing():
    assert 'python scripts/validate_storefront_domains.py "$DOMAIN_CONFIG"' in WORKFLOW
    assert "Cloudflare Tunnel -> PC-hosted Caddy" in WORKFLOW
    assert "never creates DNS or cloud resources" in WORKFLOW
    assert "gcloud " not in WORKFLOW


def test_storefront_domain_workflow_is_validation_only_and_main_scoped():
    assert "branches: [main]" in WORKFLOW
    assert "workflow_dispatch:" in WORKFLOW
    assert "pull_request:" not in WORKFLOW
    assert "cancel-in-progress: true" in WORKFLOW
    assert "domain-mappings create" not in WORKFLOW
    assert "--force" not in WORKFLOW
    assert "--to-latest" not in WORKFLOW


def test_retired_cloudflare_worker_files_stay_absent():
    for path in (
        ROOT / "deploy" / "cloudflare" / "worker.mjs",
        ROOT / "deploy" / "cloudflare" / "worker.test.mjs",
        ROOT / "deploy" / "cloudflare" / "wrangler.jsonc",
    ):
        assert not path.exists(), path
