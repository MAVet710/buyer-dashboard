from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = (ROOT / ".github" / "workflows" / "deploy.yml").read_text(encoding="utf-8")


def test_production_release_is_serialized_and_exactly_identified():
    assert "group: doobielogic-production-release-gate" in WORKFLOW
    assert "cancel-in-progress: false" in WORKFLOW
    assert '${{ github.sha }}-${{ github.run_id }}-${{ github.run_attempt }}' in WORKFLOW
    assert "--to-latest" not in WORKFLOW
    assert "gcloud " not in WORKFLOW


def test_api_release_is_verified_before_pc_hosted_handoff():
    assert "parity-release-gate:" in WORKFLOW
    assert "local-runtime-release-gate:\n    needs: parity-release-gate" in WORKFLOW
    assert "Build API release image locally" in WORKFLOW
    assert "Verify API image has exactly one Alembic head" in WORKFLOW
    assert "Verify PC-hosted API startup contract" in WORKFLOW
    assert "No external application deployment is performed by this workflow" in WORKFLOW


def test_public_runtime_contract_is_cloudflare_tunnel_to_local_pc_with_hosted_supabase():
    assert "https://ops.doobielogic.io" in WORKFLOW
    assert "Cloudflare Tunnel" in WORKFLOW
    assert "Caddy on 127.0.0.1:8080" in WORKFLOW
    assert "FastAPI on 127.0.0.1:8010" in WORKFLOW
    assert "existing hosted DoobieLogic Supabase project" in WORKFLOW
    assert "https://fovxtygwcxubjzjgovva.supabase.co" in WORKFLOW
    assert "127.0.0.1:54321" not in WORKFLOW


def test_retired_hosting_artifacts_are_absent():
    retired = (
        ROOT / ("ren" + "der.yaml"),
        ROOT / "deploy" / "cloudflare" / "worker.mjs",
        ROOT / "deploy" / "cloudflare" / "worker.test.mjs",
        ROOT / "deploy" / "cloudflare" / "wrangler.jsonc",
    )
    for path in retired:
        assert not path.exists(), path


def test_production_release_has_no_billable_google_control_plane_dependency():
    forbidden = (
        "google-github-actions/",
        "gcloud ",
        "GCP_PROJECT_ID",
        "GCP_SERVICE_ACCOUNT",
        "GCP_WORKLOAD_IDENTITY_PROVIDER",
        "docker.pkg.dev",
    )
    for path in sorted((ROOT / ".github" / "workflows").glob("*.yml")):
        source = path.read_text(encoding="utf-8")
        for token in forbidden:
            assert token.casefold() not in source.casefold(), (path.name, token)
