"""HNSW-backed ticket retrieval."""

from __future__ import annotations

import logging
from typing import Any

from .rag_embedding import clean_text, get_vector_store, initialize_embedding_model

logger = logging.getLogger(__name__)


def retrieve_tickets(question: str, project_id: Any = None, ticket_id: Any = None, k: int = 5) -> list[dict[str, Any]]:
    query = clean_text(question)
    if not query:
        return []
    where: dict[str, Any] = {}
    if project_id is not None and clean_text(project_id):
        where["project_id"] = clean_text(project_id)
    if ticket_id is not None and clean_text(ticket_id):
        where["ticket_id"] = clean_text(ticket_id)
    try:
        store = get_vector_store(initialize_embedding_model())
        results = store.similarity_search_with_relevance_scores(query, k=max(1, min(k, 20)), filter=where or None)
        retrieved: list[dict[str, Any]] = []
        seen: set[str] = set()
        for document, score in results:
            ticket_id = document.metadata.get("ticket_id")
            ticket_chunks = store._collection.get(
                where={"ticket_id": ticket_id},
                include=["documents", "metadatas"],
            )
            documents = ticket_chunks.get("documents", []) or [document.page_content]
            metadatas = ticket_chunks.get("metadatas", []) or [document.metadata]
            for content, metadata in zip(documents, metadatas):
                source_key = f"{metadata.get('ticket_id')}:{metadata.get('chunk_index')}"
                if source_key in seen:
                    continue
                seen.add(source_key)
                retrieved.append({
                    "content": content,
                    "score": float(score),
                    "metadata": dict(metadata),
                })
        return retrieved
    except Exception:
        logger.exception("Ticket retrieval failed")
        return []


def get_documents(question: str) -> list[Any]:
    """Compatibility wrapper retaining the original retrieval API."""
    return [item["content"] for item in retrieve_tickets(question)]
