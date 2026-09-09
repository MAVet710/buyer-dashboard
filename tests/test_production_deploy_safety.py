from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = (ROOT / ".github" / "workflows" / "deploy.yml").read_text(encoding="utf-8")
BLUEPRINT = (ROOT / "render.yaml").read_text(encoding="utf-8")


def test_production_release_is_serialized_and_exactly_identified():
    assert "group: doobielogic-production-release-gate" in WORKFLOW
    assert "cancel-in-progress: false" in WORKFLOW
    assert '${{ github.sha }}-${{ github.run_id }}-${{ github.run_attempt }}' in WORKFLOW
    assert "--to-latest" not in WORKFLOW
    assert "gcloud " not in WORKFLOW


def test_api_release_is_verified_before_render_check_gated_handoff():
    assert "parity-release-gate:" in WORKFLOW
    assert "zero-cost-release-gate:\n    needs: parity-release-gate" in WORKFLOW
    assert "Build API release image locally" in WORKFLOW
    assert "Verify API image has exactly one Alembic head" in WORKFLOW
    assert "Verify production API startup contract" in WORKFLOW
    assert "Verify Render handoff is exact-source and check-gated" in WORKFLOW

    api = BLUEPRINT.split("name: doobielogic-api", 1)[1].split("name: doobielogic-ops", 1)[0]
    assert "autoDeployTrigger: checksPass" in api
    assert "healthCheckPath: /health/ready" in api
    assert "RENDER_GIT_COMMIT" in api
    assert "alembic upgrade head" in api


def test_web_release_identity_is_built_from_exact_render_commit_and_not_cached():
    static = BLUEPRINT.split("name: doobielogic-ops", 1)[1]
    assert "runtime: static" in static
    assert "autoDeployTrigger: checksPass" in static
    assert "RENDER_GIT_COMMIT" in static
    assert "release.json" in static
    assert "path: /release.json" in static
    assert "no-store, no-cache, must-revalidate" in static
    assert "doobielogic.io" in static
    assert "ops.doobielogic.io" in static


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

    assert "plan: free" in BLUEPRINT
    assert "name: doobielogic-api" in BLUEPRINT
    assert "name: doobielogic-ops" in BLUEPRINT
