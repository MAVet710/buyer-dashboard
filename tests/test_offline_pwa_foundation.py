from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_pwa_manifest_and_service_worker_are_wired_without_api_caching():
    index = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    manifest = (ROOT / "frontend" / "public" / "manifest.webmanifest").read_text(encoding="utf-8")
    worker = (ROOT / "frontend" / "public" / "service-worker.js").read_text(encoding="utf-8")
    main = (ROOT / "frontend" / "src" / "main.tsx").read_text(encoding="utf-8")

    assert 'rel="manifest" href="/manifest.webmanifest"' in index
    assert '"id": "/"' in manifest
    assert '"start_url": "/"' in manifest
    assert '"scope": "/"' in manifest
    assert '"display": "standalone"' in manifest
    assert 'url.pathname.startsWith("/api/")' in worker
    assert 'if (url.origin !== self.location.origin || isApiRequest(url)) return;' in worker
    assert 'registerDoobieLogicServiceWorker' in main
    assert '<OfflineStatusBar />' in main


def test_offline_queue_is_tenant_scoped_and_regulatory_writes_fail_closed():
    queue = (ROOT / "frontend" / "src" / "lib" / "offlineQueue.ts").read_text(encoding="utf-8")
    status = (ROOT / "frontend" / "src" / "components" / "OfflineStatusBar.tsx").read_text(encoding="utf-8")

    for blocked in ("/metrc", "/regulatory", "/traceability", "/dispatch", "/provider", "/integrations", "/manifest", "/transfer"):
        assert f'"{blocked}"' in queue
    assert "Offline capture requires an explicit organization and facility scope." in queue
    assert 'status === 409 || status === 412' in queue
    assert 'status: "conflict"' not in queue  # conflict is derived, never predeclared as a successful state
    assert "waiting for verified replay" in status
    assert "Regulatory, provider, manifest, and transfer writes remain blocked while offline." in status
