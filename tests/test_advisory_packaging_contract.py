from pathlib import Path


def test_shared_score_definition_is_shipped_to_both_runtime_contexts():
    frontend = Path("frontend/Dockerfile").read_text(encoding="utf-8")
    api = Path("Dockerfile.api").read_text(encoding="utf-8")
    ci = Path(".github/workflows/web-ci.yml").read_text(encoding="utf-8")
    assert Path("shared/advisory_score.json").is_file()
    assert "WORKDIR /web/frontend" in frontend
    assert "COPY shared/ /web/shared/" in frontend
    assert "COPY shared shared" in api
    assert "--build-arg VITE_SUPABASE_PUBLISHABLE_KEY=test ." in ci
    assert "from backend.app.services.advisory import score_definition" in ci
    assert "pnpm@10.34.5" in frontend


def test_root_build_context_excludes_workstation_secrets_and_runtime_files():
    patterns = set(Path(".dockerignore").read_text(encoding="utf-8").splitlines())
    assert {"**/.env*", "**/.pilot-*", "**/node_modules", "artifacts"} <= patterns
