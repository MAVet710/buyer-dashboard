"""Real React -> loopback HTTP -> FastAPI acceptance. No production configuration.

Run with the owner-approved Python executable. Evidence defaults to a fresh temp
directory; --evidence-root can select an authorized external evidence directory.
Only this runner's Popen children/descendants are stopped. No application overrides
except Settings(_env_file=None); auth and database dependencies remain real.
"""
from __future__ import annotations

import argparse
import ipaddress
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import traceback
import ctypes
from ctypes import wintypes
from datetime import datetime, timedelta, timezone
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]
PREFIX = "/api/v1/cultivation-intelligence"
PYTHON = Path(r"C:\Users\ndasi\.codex\worktrees\ceec\repo-next-20260912-174618\.pilot-venv\Scripts\python.exe")


class OwnedJob:
    """Windows kernel job contains only processes launched by this runner."""
    def __init__(self):
        self.api = ctypes.WinDLL("kernel32", use_last_error=True)
        self.api.CreateJobObjectW.restype = wintypes.HANDLE
        self.api.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        self.api.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
        self.api.CloseHandle.argtypes = [wintypes.HANDLE]
        self.handle = self.api.CreateJobObjectW(None, None)
        if not self.handle: raise ctypes.WinError(ctypes.get_last_error())
    def add(self, child):
        if not self.api.AssignProcessToJobObject(self.handle, int(child._handle)):
            child.terminate()
            raise ctypes.WinError(ctypes.get_last_error())
    def stop(self):
        if not self.api.TerminateJobObject(self.handle, 0):
            raise ctypes.WinError(ctypes.get_last_error())
        self.api.CloseHandle(self.handle)


def network_guard():
    original = socket.socket.connect
    def connect(sock, address):
        if isinstance(address, tuple) and not ipaddress.ip_address(address[0]).is_loopback:
            raise RuntimeError("Acceptance blocked non-loopback network")
        return original(sock, address)
    socket.socket.connect = connect


def configure():
    sys.path.insert(0, str(ROOT))
    network_guard()
    from backend.app.config import Settings, get_settings
    # Cache an explicitly env-file-free configuration before any router imports.
    get_settings.cache_clear()
    Settings.model_config["env_file"] = None
    get_settings()


def seed(directory):
    from sqlalchemy.orm import Session
    from backend.app.database import get_engine
    from modules.coman.models import Organization, Facility, AppUser
    from modules.cultivation.models import CultivationRoom, CultivationPlant
    with Session(get_engine()) as s, s.begin():
        org = Organization(name="Synthetic browser acceptance", slug="real-browser")
        s.add(org); s.flush()
        facility = Facility(organization_id=org.id, name="Synthetic cultivation", code="BROWSER", cultivation_enabled=True)
        s.add(facility); s.flush()
        scope = dict(organization_id=org.id, facility_id=facility.id)
        s.add_all([AppUser(id=identity, organization_id=org.id, username=identity, normalized_username=identity,
                          password_hash="unusable-synthetic-only", role=role, active=True)
                   for identity, role in [("web-local-developer", "admin"), ("browser-readonly", "read_only")]])
        room = CultivationRoom(**scope, room_code="SYNTHETIC-A", display_name="Synthetic room A", phase="flowering")
        plants = [CultivationPlant(**scope, plant_tag=f"SYNTHETIC-{i}", strain_name="Synthetic", phase="flowering", room_code="SYNTHETIC-A") for i in (1, 2)]
        s.add_all([room, *plants]); s.flush()
        manifest = {**scope, "room": room.id, "plants": [p.id for p in plants]}
    (directory / "scope.json").write_text(json.dumps(manifest), encoding="utf-8")


def serve():
    from fastapi import FastAPI
    from backend.app.routers.cultivation_intelligence_workspace import router
    import uvicorn
    app = FastAPI(title="Isolated real cultivation acceptance")
    app.include_router(router, prefix="/api/v1")
    uvicorn.run(app, host="127.0.0.1", port=8016, access_log=False)


def historical(directory):
    """API-created connection/device/sensor; historical setup inserted before approval."""
    from sqlalchemy.orm import Session
    from backend.app.database import get_engine
    from modules.cultivation.intelligence_models import (CultivationRecipe, CultivationRecipeStage,
        CultivationRecipeTarget, CropCycle, CropCycleRoom, CropCyclePlant, DeviceMapping)
    manifest = json.loads((directory / "scope.json").read_text())
    headers = {"Content-Type": "application/json", "X-Organization-Id": manifest["organization_id"],
               "X-Facility-Id": manifest["facility_id"], "X-User-Id": "web-local-developer", "X-User-Role": "admin"}
    calls = []
    def post(path, body):
        with urlopen(Request("http://127.0.0.1:8016" + PREFIX + path, data=json.dumps(body).encode(), headers=headers), timeout=15) as response:
            calls.append({"method": "POST", "path": PREFIX + path, "status": response.status})
            return json.load(response)
    connection = post("/connections", {"provider": "json", "label": "Synthetic file evidence", "mode": "file"})
    device = post(f'/connections/{connection["id"]}/devices', {"version": connection["version"], "source_device_id": "synthetic-device", "display_name": "Synthetic sensor"})
    sensor = post(f'/devices/{device["id"]}/sensors', {"version": device["version"], "source_channel": "temp", "source_metric": "vendor_temp", "source_unit": "F", "metric": "temperature"})
    post(f'/devices/{device["id"]}/sensors', {"version": sensor["version"], "source_channel": "temp_bad", "source_metric": "vendor_temp_bad", "source_unit": "F", "metric": "temperature"})
    end = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    past = end - timedelta(days=2)
    scope = {key: manifest[key] for key in ("organization_id", "facility_id")}
    with Session(get_engine()) as s, s.begin():
        recipe = CultivationRecipe(**scope, name="Synthetic approved standard", version=1, status="draft", created_by="web-local-developer")
        s.add(recipe); s.flush()
        stage = CultivationRecipeStage(**scope, recipe_id=recipe.id, stage_key="synthetic-flower", display_name="Synthetic flower", sequence=1)
        s.add(stage); s.flush()
        s.add(CultivationRecipeTarget(**scope, stage_id=stage.id, metric="temperature", minimum=20, maximum=24, unit="C", threshold_seconds=120)); s.flush()
        recipe.status = "approved"; recipe.approved_by = "web-local-developer"; recipe.approved_at = past
        s.flush()
        cycle = CropCycle(**scope, cycle_code="SYNTHETIC-CYCLE", display_name="Synthetic exact cycle", recipe_id=recipe.id, status="active", created_by="web-local-developer")
        s.add(cycle); s.flush()
        s.add(DeviceMapping(**scope, device_id=device["id"], room_id=manifest["room"], effective_at=past, created_by="web-local-developer"))
        s.add(CropCycleRoom(**scope, cycle_id=cycle.id, room_id=manifest["room"], stage_id=stage.id, entered_at=past, assigned_by="web-local-developer"))
        for plant in manifest["plants"]:
            s.add(CropCyclePlant(**scope, cycle_id=cycle.id, plant_id=plant, added_at=past, added_by="web-local-developer"))
        manifest.update(cycle=cycle.id, connection=connection["id"], device=device["id"],
                        start=(end-timedelta(hours=1)).isoformat().replace("+00:00", "Z"), end=end.isoformat().replace("+00:00", "Z"))
    (directory / "scope.json").write_text(json.dumps(manifest), encoding="utf-8")
    (directory / "setup-http.json").write_text(json.dumps(calls, indent=2), encoding="utf-8")


def run(args):
    if Path(sys.executable).resolve() != PYTHON.resolve():
        raise RuntimeError("Use the explicitly approved Python executable")
    for port in (8016, 4198):
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", port))
    directory = Path(tempfile.mkdtemp(prefix="cultivation-real-browser-", dir=args.evidence_root))
    print(f"EVIDENCE={directory}", flush=True)
    # An allowlist prevents inherited vendor credentials/configuration reaching children.
    env = {k: v for k, v in os.environ.items() if k.upper() in {
        "SYSTEMROOT", "WINDIR", "PATH", "TEMP", "TMP", "USERPROFILE", "LOCALAPPDATA", "APPDATA", "PROGRAMFILES", "PROGRAMFILES(X86)", "COMSPEC", "PATHEXT"}}
    url = "sqlite:///" + (directory / "central.sqlite").as_posix()
    env.update(APP_ENV="test", DATABASE_URL=url, COMAN_DATABASE_URL=url,
               CULTIVATION_EDGE_PATH=str(directory / "edge.sqlite"), AI_ALLOW_CLOUD_FALLBACK="false",
               SANDBOX_STARTUP_SEED_ENABLED="false", PYTHONPATH=str(ROOT), PYTHON_DOTENV_DISABLED="1",
               PYTHONDONTWRITEBYTECODE="1", CI_REAL_EVIDENCE=str(directory))
    children = []; logs = []; job = OwnedJob()
    receipt = {"scope": "synthetic loopback real React/FastAPI; development headers, no Supabase login",
               "ports": [8016, 4198], "cases": [], "status": "FAILED", "evidence": str(directory)}
    def git(*arguments):
        return subprocess.check_output(["git", *arguments], cwd=ROOT, text=True).strip()
    receipt.update(base_sha=git("rev-parse", "HEAD"), uncommitted_state=git("status", "--porcelain"))
    def command(argv, log, cwd=ROOT):
        with (directory / log).open("w", encoding="utf-8") as output:
            subprocess.run(argv, cwd=cwd, env=env, stdout=output, stderr=subprocess.STDOUT, check=True, timeout=180)
    def start(argv, name, cwd):
        output = (directory / name).open("w", encoding="utf-8"); logs.append(output)
        child = subprocess.Popen(argv, cwd=cwd, env=env, stdout=output, stderr=subprocess.STDOUT)
        children.append(child)
        job.add(child)
        return child
    def wait(url, child):
        deadline = time.monotonic()+50
        while time.monotonic() < deadline:
            if child.poll() is not None: raise RuntimeError(f"Own listener exited: {child.returncode}")
            try:
                with urlopen(url, timeout=1): return
            except Exception: time.sleep(.25)
        raise RuntimeError("Own listener startup timed out")
    try:
        command([sys.executable, "-m", "alembic", "upgrade", "head"], "migration.log")
        receipt["migration"] = "full Alembic upgrade head passed"
        script = str(Path(__file__).resolve())
        command([sys.executable, script, "--mode", "seed", "--directory", str(directory)], "seed.log")
        api = start([sys.executable, script, "--mode", "serve"], "api.log", directory)
        wait("http://127.0.0.1:8016/openapi.json", api)
        command([sys.executable, script, "--mode", "historical", "--directory", str(directory)], "historical.log")
        node = shutil.which("node")
        if not node: raise RuntimeError("Installed node unavailable")
        vite = start([node, str(ROOT / "frontend/node_modules/vite/bin/vite.js"), "--config", "e2e/fixtures/cultivation-intelligence-real.config.ts", "--configLoader", "native", "--strictPort"], "vite.log", ROOT / "frontend")
        wait("http://127.0.0.1:4198/e2e/fixtures/cultivation-intelligence.html", vite)
        # Generated runner config lives only in evidence; shared package/config untouched.
        config = directory / "playwright.config.cjs"
        config.write_text("module.exports=" + json.dumps({"testDir": str(ROOT / "frontend/e2e"),
            "testMatch": "cultivation-intelligence-real.spec.ts", "timeout": 45000,
            "expect": {"timeout": 10000}, "workers": 1, "retries": 0,
            "reporter": [["json", {"outputFile": str(directory / "playwright.json")}]],
            "outputDir": str(directory / "artifacts"), "use": {"channel": "chrome", "headless": True,
            "trace": "off", "screenshot": "only-on-failure", "serviceWorkers": "block"}}), encoding="utf-8")
        browser = start([node, str(ROOT / "frontend/node_modules/@playwright/test/cli.js"), "test", "--config", str(config)], "browser.log", ROOT / "frontend")
        deadline = time.monotonic() + 600
        while browser.poll() is None:
            if (directory / "stop-requested").exists():
                raise RuntimeError("Run explicitly stopped; unfinished cases are not accepted")
            if time.monotonic() > deadline: raise TimeoutError("Browser acceptance exceeded 600 seconds")
            time.sleep(.25)
        receipt["browser_exit_code"] = browser.returncode
        receipt["status"] = "PASSED" if browser.returncode == 0 else "FAILED"
    except Exception:
        receipt["failure"] = traceback.format_exc()
    finally:
        job.stop()
        for child in reversed(children):
            child.wait(timeout=10)
        for output in logs: output.close()
        receipt["listeners_free_after_cleanup"] = {}
        for port in (8016, 4198):
            with socket.socket() as probe:
                receipt["listeners_free_after_cleanup"][str(port)] = probe.connect_ex(("127.0.0.1", port)) != 0
        receipt["cases"] = [json.loads(p.read_text(encoding="utf-8")) for p in directory.glob("case-*.json")]
        receipt["uncommitted_state_after"] = git("status", "--porcelain")
        (directory / "receipt.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
        print(json.dumps({"status": receipt["status"], "evidence": str(directory), "cleanup": receipt["listeners_free_after_cleanup"]}), flush=True)
    return 0 if receipt["status"] == "PASSED" else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["run", "seed", "serve", "historical"], default="run")
    parser.add_argument("--directory", type=Path)
    parser.add_argument("--evidence-root", type=Path)
    args = parser.parse_args()
    if args.mode == "run": sys.exit(run(args))
    configure()
    if args.mode == "seed": seed(args.directory)
    elif args.mode == "historical": historical(args.directory)
    else: serve()
