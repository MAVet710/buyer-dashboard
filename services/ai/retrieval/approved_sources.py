from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from typing import Any
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .embeddings import LocalEmbeddingProvider
from .ingestion import KnowledgeIngestionService
from .store import KnowledgeScope, KnowledgeStore

MAX_BYTES = 25 * 1024 * 1024
USER_AGENT = "DoobieLogic-Knowledge/1.0"
DEFAULT_MANIFEST = Path(__file__).resolve().parents[3] / "knowledge_sources" / "approved_sources.json"


class SafeRedirectHandler(HTTPRedirectHandler):
    def __init__(self, allowed_domains: set[str]) -> None:
        super().__init__()
        self.allowed_domains = allowed_domains

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        validate_source_url(newurl, self.allowed_domains)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def validate_source_url(url: str, allowed_domains: set[str]) -> str:
    parsed = urlparse(str(url or ""))
    host = (parsed.hostname or "").casefold()
    if parsed.scheme != "https" or not host or host not in allowed_domains:
        raise ValueError(f"Knowledge source URL is not allowlisted: {url}")
    if parsed.username or parsed.password or parsed.port not in {None, 443}:
        raise ValueError(f"Knowledge source URL contains unsupported authority components: {url}")
    return host


def safe_key(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9._-]+", "-", str(value or "").strip()).strip("-._")
    if not cleaned:
        raise ValueError("Knowledge source key is required.")
    return cleaned[:160]


def validate_manifest(payload: dict[str, Any]) -> tuple[set[str], list[dict[str, Any]]]:
    allowed = {str(value).casefold().strip() for value in payload.get("allowed_domains") or [] if str(value).strip()}
    if not allowed:
        raise ValueError("Knowledge manifest requires at least one allowed domain.")
    sources = payload.get("sources")
    if not isinstance(sources, list) or not sources:
        raise ValueError("Knowledge manifest requires sources.")
    keys: set[str] = set()
    validated: list[dict[str, Any]] = []
    for source in sources:
        if not isinstance(source, dict):
            raise ValueError("Each knowledge source must be an object.")
        key = safe_key(source.get("key", ""))
        if key in keys:
            raise ValueError(f"Duplicate knowledge source key: {key}")
        keys.add(key)
        validate_source_url(str(source.get("url") or ""), allowed)
        source_format = str(source.get("format") or "").casefold()
        if source_format not in {"pdf", "html"}:
            raise ValueError(f"Unsupported source format for {key}: {source_format}")
        authority = int(source.get("authority_level") or 0)
        if authority not in range(1, 7):
            raise ValueError(f"Invalid authority level for {key}")
        if authority == 1 and str(source.get("jurisdiction") or "").strip() and not bool(source.get("facility_scope", True)):
            raise ValueError(f"Jurisdiction-specific regulatory source must remain facility scoped: {key}")
        validated.append(dict(source))
    return allowed, validated


def load_approved_sources(path: Path = DEFAULT_MANIFEST) -> tuple[dict[str, Any], set[str], list[dict[str, Any]]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    allowed, sources = validate_manifest(payload)
    return payload, allowed, sources


def public_catalog(path: Path = DEFAULT_MANIFEST) -> dict[str, Any]:
    payload, _allowed, sources = load_approved_sources(path)
    return {
        "schema_version": payload.get("schema_version", 1),
        "reviewed_at": payload.get("reviewed_at", ""),
        "sources": [
            {
                key: source.get(key)
                for key in (
                    "key", "title", "source", "source_type", "authority_level", "jurisdiction",
                    "effective_date", "version", "url", "format", "facility_scope", "review_every_days", "active"
                )
            }
            for source in sources
            if bool(source.get("active", True))
        ],
    }


def download_source(source: dict[str, Any], *, allowed_domains: set[str]) -> tuple[bytes, str, str]:
    url = str(source["url"])
    validate_source_url(url, allowed_domains)
    opener = build_opener(SafeRedirectHandler(allowed_domains))
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/pdf,text/html;q=0.9,*/*;q=0.1"})
    with opener.open(request, timeout=30) as response:
        final_url = str(response.geturl())
        validate_source_url(final_url, allowed_domains)
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


def seed_approved_sources(
    *,
    store: KnowledgeStore,
    scope: KnowledgeScope,
    embeddings: LocalEmbeddingProvider | None = None,
    keys: set[str] | None = None,
    manifest_path: Path = DEFAULT_MANIFEST,
    force_reindex: bool = False,
) -> dict[str, Any]:
    _manifest, allowed_domains, sources = load_approved_sources(manifest_path)
    ingestion = KnowledgeIngestionService(store, embeddings)
    results: list[dict[str, Any]] = []
    for source in sources:
        if not bool(source.get("active", True)):
            continue
        key = str(source["key"])
        if keys and key not in keys:
            continue
        # The built-in starter catalog deliberately does not publish jurisdiction-specific material
        # globally or organization-wide. Facility scope is the isolation boundary until facilities
        # have an explicit state/jurisdiction field that can be enforced at retrieval time.
        if not bool(source.get("facility_scope", True)) or bool(source.get("global_scope", False)):
            results.append({"key": key, "status": "rejected_scope"})
            continue
        try:
            payload, final_url, content_type = download_source(source, allowed_domains=allowed_domains)
            digest = hashlib.sha256(payload).hexdigest()
            existing = store.find_document_by_hash(scope=scope, document_hash=digest, facility_scope=True)
            if existing and not force_reindex:
                results.append({"key": key, "status": "unchanged", "document_id": existing["id"], "sha256": digest})
                continue
            result = ingestion.ingest(
                scope=scope,
                filename=f"{safe_key(key)}.{source['format']}",
                payload=payload,
                title=str(source.get("title") or key),
                source=str(source.get("source") or final_url),
                source_type=str(source.get("source_type") or "internal_document"),
                authority_level=int(source.get("authority_level") or 6),
                jurisdiction=str(source.get("jurisdiction") or ""),
                effective_date=str(source.get("effective_date") or ""),
                version=str(source.get("version") or ""),
                source_url=final_url,
                global_scope=False,
                facility_scope=True,
            )
            store.deactivate_superseded_source(
                scope=scope,
                source_url=final_url,
                keep_document_id=str(result["document_id"]),
                facility_scope=True,
            )
            results.append({
                "key": key,
                "status": "reindexed" if existing else "indexed",
                "document_id": result["document_id"],
                "chunks": result["chunks"],
                "sha256": digest,
                "content_type": content_type,
            })
        except Exception as exc:
            results.append({"key": key, "status": "failed", "error": f"{exc.__class__.__name__}: {exc}"[:500]})
    indexed = sum(1 for row in results if row["status"] in {"indexed", "reindexed"})
    unchanged = sum(1 for row in results if row["status"] == "unchanged")
    failed = sum(1 for row in results if row["status"] in {"failed", "rejected_scope"})
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "indexed": indexed,
        "unchanged": unchanged,
        "failed": failed,
        "results": results,
    }
