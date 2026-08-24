from __future__ import annotations

from io import BytesIO
import hashlib
import re

from bs4 import BeautifulSoup
from pypdf import PdfReader

try:
    from docx import Document
except Exception:  # pragma: no cover
    Document = None

from .embeddings import LocalEmbeddingProvider
from .store import KnowledgeScope, KnowledgeStore

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md", ".markdown", ".html", ".htm"}


def extract_sections(filename: str, payload: bytes) -> list[tuple[str, str]]:
    lower = str(filename or "").casefold()
    if lower.endswith(".pdf"):
        reader = PdfReader(BytesIO(payload))
        sections: list[tuple[str, str]] = []
        for index, page in enumerate(reader.pages, start=1):
            text = str(page.extract_text() or "").strip()
            if text:
                sections.append((f"page {index}", text))
        return sections
    if lower.endswith(".docx"):
        if Document is None:
            raise ValueError("DOCX support is unavailable in this deployment.")
        document = Document(BytesIO(payload))
        text = "\n".join(paragraph.text for paragraph in document.paragraphs if paragraph.text.strip())
        return [("document", text)] if text.strip() else []
    text = payload.decode("utf-8", errors="replace")
    if lower.endswith((".html", ".htm")):
        soup = BeautifulSoup(text, "html.parser")
        for tag in soup.find_all(["script", "style", "nav", "footer", "header", "form", "noscript"]):
            tag.decompose()
        primary = soup.find("main") or soup.find("article") or soup.body or soup
        text = primary.get_text("\n")
    return [("document", text.strip())] if text.strip() else []


def chunk_text(text: str, *, max_chars: int = 2400, overlap_chars: int = 240) -> list[str]:
    cleaned = re.sub(r"[ \t]+", " ", str(text or ""))
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    if not cleaned:
        return []
    chunks: list[str] = []
    start = 0
    maximum = max(600, int(max_chars))
    overlap = max(0, min(int(overlap_chars), maximum // 3))
    while start < len(cleaned):
        end = min(len(cleaned), start + maximum)
        if end < len(cleaned):
            boundary = max(cleaned.rfind("\n", start, end), cleaned.rfind(". ", start, end))
            if boundary > start + maximum // 2:
                end = boundary + 1
        chunks.append(cleaned[start:end].strip())
        if end >= len(cleaned):
            break
        start = max(start + 1, end - overlap)
    return [chunk for chunk in chunks if chunk]


class KnowledgeIngestionService:
    def __init__(self, store: KnowledgeStore, embeddings: LocalEmbeddingProvider | None = None) -> None:
        self.store = store
        self.embeddings = embeddings

    def ingest(self, *, scope: KnowledgeScope, filename: str, payload: bytes, title: str, source: str, source_type: str, authority_level: int, jurisdiction: str = "", effective_date: str = "", version: str = "", source_url: str = "", global_scope: bool = False, facility_scope: bool = True) -> dict:
        if not payload:
            raise ValueError("Knowledge document is empty.")
        if len(payload) > 25 * 1024 * 1024:
            raise ValueError("Knowledge document exceeds the 25 MB limit.")
        sections = extract_sections(filename, payload)
        if not sections:
            raise ValueError("No readable text was found in the document.")
        document_hash = hashlib.sha256(payload).hexdigest()
        document_id = self.store.add_document(
            scope=scope,
            title=title or filename,
            source=source or filename,
            source_type=source_type,
            authority_level=authority_level,
            jurisdiction=jurisdiction,
            effective_date=effective_date,
            version=version,
            source_url=source_url,
            global_scope=global_scope,
            facility_scope=facility_scope,
            document_hash=document_hash,
        )
        indexed = 0
        for section, section_text in sections:
            chunks = chunk_text(section_text)
            embeddings = self.embeddings.embed(chunks) if self.embeddings and chunks else []
            for index, content in enumerate(chunks):
                embedding = embeddings[index] if index < len(embeddings) else []
                self.store.add_chunk(
                    document_id=document_id,
                    scope=scope,
                    content=content,
                    chunk_number=indexed,
                    page_or_section=section,
                    authority_level=authority_level,
                    embedding=embedding,
                    global_scope=global_scope,
                    facility_scope=facility_scope,
                )
                indexed += 1
        return {"document_id": document_id, "chunks": indexed, "embedding": bool(self.embeddings and indexed), "document_hash": document_hash}
