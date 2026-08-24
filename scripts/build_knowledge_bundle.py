from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from services.ai.retrieval.approved_sources import download_source, safe_key, validate_manifest


def build_bundle(manifest_path: Path, output_dir: Path, selected_keys: set[str] | None = None) -> dict:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    allowed_domains, sources = validate_manifest(manifest)
    output_dir.mkdir(parents=True, exist_ok=True)
    records = []
    for source in sources:
        if not bool(source.get("active", True)):
            continue
        if selected_keys and source["key"] not in selected_keys:
            continue
        payload, final_url, content_type = download_source(source, allowed_domains=allowed_domains)
        extension = ".pdf" if source["format"] == "pdf" else ".html"
        filename = f"{safe_key(source['key'])}{extension}"
        (output_dir / filename).write_bytes(payload)
        records.append({
            **source,
            "bundle_filename": filename,
            "final_url": final_url,
            "content_type": content_type,
            "sha256": hashlib.sha256(payload).hexdigest(),
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "bytes": len(payload),
        })
    bundle = {
        "schema_version": 1,
        "manifest": str(manifest_path),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "document_count": len(records),
        "documents": records,
    }
    (output_dir / "bundle.json").write_text(json.dumps(bundle, indent=2), encoding="utf-8")
    return bundle


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a local DoobieLogic knowledge bundle from the approved source catalog.")
    parser.add_argument("--manifest", default="knowledge_sources/approved_sources.json")
    parser.add_argument("--output", default="knowledge_bundle")
    parser.add_argument("--key", action="append", default=[], help="Download only a specific approved source key; repeat as needed.")
    args = parser.parse_args()
    bundle = build_bundle(Path(args.manifest), Path(args.output), set(args.key) or None)
    print(json.dumps({"document_count": bundle["document_count"], "output": args.output}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
