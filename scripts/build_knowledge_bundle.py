from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

MAX_BYTES = 25 * 1024 * 1024
USER_AGENT = "DoobieLogic-Knowledge-Bundle/1.0"


class SafeRedirectHandler(HTTPRedirectHandler):
    def __init__(self, allowed_domains: set[str]) -> None:
        super().__init__()
        self.allowed_domains = allowed_domains

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        _validate_url(newurl, self.allowed_domains)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _validate_url(url: str, allowed_domains: set[str]) -> str:
    parsed = urlparse(str(url or ""))
    host = (parsed.hostname or "").casefold()
    if parsed.scheme != "https" or not host or host not in allowed_domains:
        raise ValueError(f"Knowledge source URL is not allowlisted: {url}")
    if parsed.username or parsed.password or parsed.port not in {None, 443}:
        raise ValueError(f"Knowledge source URL contains unsupported authority components: {url}")
    return host


def _safe_name(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9._-]+", "-", str(value or "").strip()).strip("-._")
    if not cleaned:
        raise ValueError("Knowledge source key is required.")
    return cleaned[:160]


def validate_manifest(payload: dict) -> tuple[set[str], list[dict]]:
    allowed = {str(value).casefold().strip() for value in payload.get("allowed_domains") or [] if str(value).strip()}
    if not allowed:
        raise ValueError("Knowledge manifest requires at least one allowed domain.")
    sources = payload.get("sources")
    if not isinstance(sources, list) or not sources:
        raise ValueError("Knowledge manifest requires sources.")
    keys: set[str] = set()
    validated: list[dict] = []
    for source in sources:
        if not isinstance(source, dict):
            raise ValueError("Each knowledge source must be an object.")
        key = _safe_name(source.get("key", ""))
        if key in keys:
            raise ValueError(f"Duplicate knowledge source key: {key}")
        keys.add(key)
        _validate_url(str(source.get("url") or ""), allowed)
        source_format = str(source.get("format") or "").casefold()
        if source_format not in {"pdf", "html"}:
            raise ValueError(f"Unsupported bundle source format for {key}: {source_format}")
        if int(source.get("authority_level") or 0) not in range(1, 7):
            raise ValueError(f"Invalid authority level for {key}")
        validated.append(dict(source))
    return allowed, validated


def download_source(source: dict, *, allowed_domains: set[str]) -> tuple[bytes, str, str]:
    url = str(source["url"])
    _validate_url(url, allowed_domains)
    opener = build_opener(SafeRedirectHandler(allowed_domains))
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/pdf,text/html;q=0.9,*/*;q=0.1"})
    with opener.open(request, timeout=30) as response:
        final_url = str(response.geturl())
        _validate_url(final_url, allowed_domains)
        content_type = str(response.headers.get("Content-Type") or "").split(";", 1)[0].casefold()
        payload = response.read(MAX_BYTES + 1)
    if len(payload) > MAX_BYTES:
        raise ValueError(f"Knowledge source exceeds {MAX_BYTES} bytes: {source['key']}")
    expected = str(source.get("format") or "").casefold()
    if expected == "pdf" and content_type != "application/pdf":
        raise ValueError(f"Expected PDF for {source['key']}, received {content_type or 'unknown'}")
    if expected == "html" and content_type not in {"text/html", "application/xhtml+xml"}:
        raise ValueError(f"Expected HTML for {source['key']}, received {content_type or 'unknown'}")
    return payload, final_url, content_type


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
        filename = f"{_safe_name(source['key'])}{extension}"
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
