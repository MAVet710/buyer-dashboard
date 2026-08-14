"""Fast repository checks that complement the full pytest suite."""

from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIRS = [ROOT / "modules", ROOT / "services", ROOT / "reports", ROOT / "views"]


def python_sources() -> list[Path]:
    files = [ROOT / "app.py", ROOT / "delivery_impact.py"]
    for directory in SOURCE_DIRS:
        files.extend(directory.rglob("*.py"))
    return sorted({path for path in files if path.exists()})


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

    if problems:
        print("Quality gate failed:")
        for problem in problems:
            print(f"- {problem}")
        return 1
    print(f"Quality gate passed across {len(python_sources())} source files; app.py is {app_lines:,} lines.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
