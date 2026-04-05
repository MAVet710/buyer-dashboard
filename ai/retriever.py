import os

import chromadb

from ai.embedder import get_embedding



def get_chroma_collection():
    db_path = os.getenv("VECTOR_DB_PATH", "./data/vectorstore/chroma_db")
    client = chromadb.PersistentClient(path=db_path)
    return client.get_or_create_collection(name="cannabis_knowledge")


def retrieve_context(
    question: str,
    module: str = "buyer",
    state: str = "MA",
    program: str = "medical",
    n_results: int = 5,
):
    collection = get_chroma_collection()
    query_embedding = get_embedding(question)

    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=n_results,
        where={
            "$and": [
                {"module": {"$eq": module}},
                {"state": {"$eq": state}},
                {"program": {"$eq": program}},
            ]
        },
    )
    return results
