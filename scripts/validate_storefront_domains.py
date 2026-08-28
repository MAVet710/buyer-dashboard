from __future__ import annotations

import argparse
import re
from pathlib import Path


DOMAIN_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.doobielogic\.io$")
RESERVED_LABELS = {"api", "ops", "www"}


def load_domains(path: Path) -> list[str]:
    domains: list[str] = []
    seen: set[str] = set()
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        value = raw.strip().lower()
        if not value or value.startswith("#"):
            continue
        if "*" in value:
            raise ValueError(f"line {line_number}: wildcard storefront domains are not allowed")
        if not DOMAIN_RE.fullmatch(value):
            raise ValueError(
                f"line {line_number}: {value!r} must be one exact first-level *.doobielogic.io hostname"
            )
        label = value.removesuffix(".doobielogic.io")
        if label in RESERVED_LABELS:
            raise ValueError(f"line {line_number}: {value!r} is a reserved DoobieLogic platform host")
        if value in seen:
            raise ValueError(f"line {line_number}: duplicate storefront domain {value!r}")
        seen.add(value)
        domains.append(value)
    if not domains:
        raise ValueError("at least one approved storefront domain is required")
    return domains


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate approved hosted storefront domains.")
    parser.add_argument("path", type=Path)
    parser.add_argument("--print", action="store_true", dest="print_domains")
    args = parser.parse_args()
    domains = load_domains(args.path)
    if args.print_domains:
        print("\n".join(domains))
    else:
        print(f"Validated {len(domains)} storefront domain(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
