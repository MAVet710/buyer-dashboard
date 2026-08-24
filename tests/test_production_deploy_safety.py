from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = (ROOT / ".github" / "workflows" / "deploy.yml").read_text(encoding="utf-8")
DOCKERFILE = (ROOT / "frontend" / "Dockerfile").read_text(encoding="utf-8")
NGINX = (ROOT / "frontend" / "nginx.conf").read_text(encoding="utf-8")


def test_production_deploy_is_serialized_and_never_promotes_latest():
    assert "group: doobielogic-production" in WORKFLOW
    assert "cancel-in-progress: false" in WORKFLOW
    assert "--to-latest" not in WORKFLOW
    assert '${{ github.sha }}-${{ github.run_id }}-${{ github.run_attempt }}' in WORKFLOW


def test_api_candidate_is_verified_directly_before_exact_revision_cutover():
    assert "Capture and preflight currently healthy production API revision" in WORKFLOW
    assert "--no-traffic" in WORKFLOW
    assert '--tag "$API_CANDIDATE_TAG"' in WORKFLOW
    assert 'REV_RELEASE" = "${{ github.sha }}"' in WORKFLOW
    assert 'REV_SCHEMA" = "$IMAGE_SCHEMA_HEAD"' in WORKFLOW
    assert '"$CANDIDATE_URL/health"' in WORKFLOW
    assert '"$CANDIDATE_URL/health/ready"' in WORKFLOW
    assert '--to-revisions "$CREATED_API_REVISION=100"' in WORKFLOW
    assert '--to-revisions "$PREVIOUS_API_REVISION=100"' in WORKFLOW
    assert "Alembic migrations were intentionally NOT reversed" in WORKFLOW


def test_web_release_identity_is_built_served_and_verified_on_both_domains():
    assert "ARG VITE_RELEASE_SHA=unknown" in DOCKERFILE
    assert 'release.json' in DOCKERFILE
    assert '"release_sha":"%s"' in DOCKERFILE
    assert "location = /release.json" in NGINX
    assert 'Cache-Control "no-store, no-cache, must-revalidate"' in NGINX
    assert "--build-arg VITE_RELEASE_SHA=${{ github.sha }}" in WORKFLOW
    assert '"$CANDIDATE_URL/release.json?run=${{ github.run_id }}-${{ github.run_attempt }}"' in WORKFLOW
    assert 'https://doobielogic.io/release.json?run=${{ github.run_id }}-${{ github.run_attempt }}' in WORKFLOW
    assert 'https://ops.doobielogic.io/release.json?run=${{ github.run_id }}-${{ github.run_attempt }}' in WORKFLOW
    assert '--to-revisions "$CREATED_WEB_REVISION=100"' in WORKFLOW
    assert '--to-revisions "$PREVIOUS_WEB_REVISION=100"' in WORKFLOW


def test_cloud_run_mutations_and_describes_are_project_scoped():
    run_lines = [line.strip() for line in WORKFLOW.splitlines() if line.strip().startswith("gcloud run ")]
    assert run_lines
    # Multi-line commands place --project on the following line. Require at least
    # one project flag for every Cloud Run command block by comparing counts.
    assert WORKFLOW.count('--project "${{ secrets.GCP_PROJECT_ID }}"') >= len(run_lines)
    assert 'gcloud logging read' in WORKFLOW
    assert WORKFLOW.count('gcloud logging read') <= WORKFLOW.count('--project "${{ secrets.GCP_PROJECT_ID }}"')
