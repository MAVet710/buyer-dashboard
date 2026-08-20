"""Fast repository checks that complement the full pytest suite."""

from __future__ import annotations

from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIRS = [ROOT / "modules", ROOT / "services", ROOT / "reports", ROOT / "views"]

# Version-backup files (app_v7.py, ui_theme_v2.py, extraction_perfect_view_v5.py, ...)
# only ever accumulate at the repo root and in views/ — that's where this pattern has
# actually occurred, so candidate scanning is scoped there rather than repo-wide.
VERSION_SUFFIX_PATTERN = re.compile(r".+_(v\d+|BU)$")
VERSION_SUFFIX_SCAN_DIRS = [ROOT, ROOT / "views"]
CORPUS_EXCLUDE_DIR_NAMES = {".venv", "__pycache__", ".git"}


def python_sources() -> list[Path]:
    files = [ROOT / "app.py", ROOT / "delivery_impact.py"]
    for directory in SOURCE_DIRS:
        files.extend(directory.rglob("*.py"))
    return sorted({path for path in files if path.exists()})


def orphaned_version_suffixed_files() -> list[str]:
    """Flag *_vN.py / *_BU.py files with zero references anywhere in the repo.

    The reference search covers the WHOLE tree (including tests/ and scripts/),
    not just the usual SOURCE_DIRS — a file can be legitimately alive purely by
    being exercised from tests/, and excluding that corpus would false-positive
    on it (this happened with views/extraction_perfect_view_v2.py, which is only
    referenced from tests/test_extraction_perfect_view_v2.py).
    """

    corpus: dict[Path, str] = {}
    for path in ROOT.rglob("*.py"):
        if any(part in CORPUS_EXCLUDE_DIR_NAMES for part in path.relative_to(ROOT).parts):
            continue
        corpus[path] = path.read_text(encoding="utf-8", errors="ignore")

    orphaned: list[str] = []
    for directory in VERSION_SUFFIX_SCAN_DIRS:
        if not directory.exists():
            continue
        for path in sorted(directory.glob("*.py")):
            stem = path.stem
            if not VERSION_SUFFIX_PATTERN.match(stem):
                continue
            referenced = any(
                re.search(rf"\b{re.escape(stem)}\b", source)
                for other_path, source in corpus.items()
                if other_path != path
            )
            if not referenced:
                orphaned.append(str(path.relative_to(ROOT)))
    return sorted(orphaned)


def main() -> int:
    problems: list[str] = []
    app_lines = len((ROOT / "app.py").read_text(encoding="utf-8").splitlines())
    if app_lines > 12_000:
        problems.append(f"app.py exceeded the 12,000-line safety ceiling ({app_lines:,}).")

    required = [
        ROOT / "docs" / "USER_GUIDE.md",
        ROOT / "modules" / "authentication" / "login_page.py",
        ROOT / "modules" / "navigation" / "role_home.py",
        ROOT / "services" / "tenant_guard.py",
    ]
    for path in required:
        if not path.exists():
            problems.append(f"Required commercial-readiness boundary is missing: {path.relative_to(ROOT)}")

    for path in python_sources():
        source = path.read_text(encoding="utf-8")
        relative = path.relative_to(ROOT)
        if "datetime.utcnow(" in source:
            problems.append(f"Timezone-naive UTC timestamp remains in {relative}")
        if "from PyPDF2" in source or "import PyPDF2" in source:
            problems.append(f"Deprecated PyPDF2 import remains in {relative}")

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    for phrase in ("Operations Home", "Data Import Center", "docs/USER_GUIDE.md"):
        if phrase not in readme:
            problems.append(f"README is missing current product language: {phrase}")

    for relative in orphaned_version_suffixed_files():
        problems.append(
            f"{relative} matches the dead version-backup naming pattern (_vN/_BU) and has "
            "zero references anywhere in the repo — delete it or wire it in."
        )

    if problems:
        print("Quality gate failed:")
        for problem in problems:
            print(f"- {problem}")
        return 1
    print(f"Quality gate passed across {len(python_sources())} source files; app.py is {app_lines:,} lines.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
