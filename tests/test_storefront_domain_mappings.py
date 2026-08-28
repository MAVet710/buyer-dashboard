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


def test_storefront_mapping_workflow_installs_beta_noninteractively_before_mapping():
    install = WORKFLOW.index("gcloud components install beta --quiet")
    describe = WORKFLOW.index("gcloud beta run domain-mappings describe")
    assert install < describe


def test_storefront_mapping_workflow_is_idempotent_and_service_scoped():
    assert "gcloud beta run domain-mappings describe" in WORKFLOW
    assert "gcloud beta run domain-mappings create" in WORKFLOW
    assert '--service "${{ env.WEB_SERVICE }}"' in WORKFLOW
    assert 'ROUTE_NAME" != "${{ env.WEB_SERVICE }}"' in WORKFLOW
    assert '--project "${{ secrets.GCP_PROJECT_ID }}"' in WORKFLOW
    assert '--region "${{ env.REGION }}"' in WORKFLOW
    assert "--force" not in WORKFLOW
    assert "--to-latest" not in WORKFLOW


def test_storefront_mapping_workflow_reports_dns_without_blocking_on_certificate_readiness():
    assert ".status.resourceRecords[]?" in WORKFLOW
    assert 'select(.type == "Ready")' in WORKFLOW
    assert "Mapping readiness:" in WORKFLOW
    assert '[ "$READY" = "True" ]' not in WORKFLOW


def test_storefront_domain_workflow_only_mutates_after_main_merge_or_manual_dispatch():
    assert "branches: [main]" in WORKFLOW
    assert "workflow_dispatch:" in WORKFLOW
    assert "pull_request:" not in WORKFLOW
    assert "cancel-in-progress: false" in WORKFLOW
