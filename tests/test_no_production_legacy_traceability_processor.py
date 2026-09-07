from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PRODUCTION_ROOTS = (ROOT / "modules", ROOT / "backend", ROOT / "services")
LEGACY_PROCESSOR = (ROOT / "modules/traceability/processor.py").resolve()


def test_no_production_code_imports_legacy_traceability_processor():
    offenders: list[str] = []
    for root in PRODUCTION_ROOTS:
        for path in root.rglob("*.py"):
            if path.resolve() == LEGACY_PROCESSOR:
                continue
            source = path.read_text(encoding="utf-8")
            explicit = "modules.traceability.processor" in source
            relative = path.parent.name == "traceability" and "from .processor import" in source
            if explicit or relative:
                offenders.append(str(path.relative_to(ROOT)))

    assert offenders == [], (
        "Production code must use TraceabilityDispatcher/provider adapters; "
        f"legacy processor imports found in: {offenders}"
    )
