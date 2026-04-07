"""Bootstrap structured compliance records and vector knowledge chunks."""

from __future__ import annotations

import json
import os
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import chromadb

from ai.compliance_store import ComplianceRecord, SQLiteComplianceStore
from ai.embedder import get_embedding


def load_json(path: Path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def seed_compliance(seed_path: Path, db_path: str) -> int:
    records_raw = load_json(seed_path)
    store = SQLiteComplianceStore(db_path)
    try:
        records = [ComplianceRecord(**item) for item in records_raw]
        return store.upsert_many(records)
    finally:
        store.close()


def seed_vectorstore(seed_path: Path, vector_db_path: str) -> int:
    chunks = load_json(seed_path)
    client = chromadb.PersistentClient(path=vector_db_path)
    collection = client.get_or_create_collection(name="cannabis_knowledge")

    ids = [item["id"] for item in chunks]
    docs = [item["document"] for item in chunks]
    metas = [item["metadata"] for item in chunks]

    existing = set(collection.get(ids=ids).get("ids", []))
    add_ids, add_docs, add_metas = [], [], []

    for doc_id, doc, meta in zip(ids, docs, metas):
        if doc_id in existing:
            continue
        add_ids.append(doc_id)
        add_docs.append(doc)
        add_metas.append(meta)

    if not add_ids:
        return 0

    try:
        embeddings = [get_embedding(doc) for doc in add_docs]
        collection.add(ids=add_ids, documents=add_docs, metadatas=add_metas, embeddings=embeddings)
    except Exception as exc:
        print(f"WARNING: vector chunk seeding skipped because embedding service is unavailable: {exc}")
        return 0

    return len(add_ids)


def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    compliance_seed = repo_root / "data" / "seed" / "compliance_sources.json"
    chunks_seed = repo_root / "data" / "seed" / "knowledge_chunks.json"

    compliance_db_path = os.getenv("COMPLIANCE_DB_PATH", str(repo_root / "data" / "compliance" / "compliance.db"))
    vector_db_path = os.getenv("VECTOR_DB_PATH", str(repo_root / "data" / "vectorstore" / "chroma_db"))

    count_compliance = seed_compliance(compliance_seed, compliance_db_path)
    count_chunks = seed_vectorstore(chunks_seed, vector_db_path)

    print(f"Seeded compliance records: {count_compliance}")
    print(f"Seeded vector chunks: {count_chunks}")
    print(f"Compliance DB: {compliance_db_path}")
    print(f"Vector DB: {vector_db_path}")


if __name__ == "__main__":
    main()
