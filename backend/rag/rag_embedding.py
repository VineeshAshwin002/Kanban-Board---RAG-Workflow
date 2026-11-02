"""Ticket cleaning, structure-aware chunking, and Chroma indexing."""

from __future__ import annotations

import hashlib
import logging
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Mapping

from dotenv import load_dotenv
from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_openai import OpenAIEmbeddings

load_dotenv(dotenv_path=Path(__file__).resolve().parents[1] / ".env")

logger = logging.getLogger(__name__)
COLLECTION_NAME = os.getenv("CHROMA_COLLECTION", "board_documets")
PERSIST_DIRECTORY = os.getenv(
    "CHROMA_PERSIST_DIRECTORY",
    str(Path(__file__).resolve().parents[2] / "vectorstore"),
)
API_KEY = os.getenv("AZURE_OPENAI_API_KEY") or os.getenv("API_KEY")
EMBEDDING_MODEL = os.getenv("AZURE_OPENAI_EMBEDDING_DEPLOYMENT", "text-embedding-3-small")
BASE_URL = os.getenv(
    "AZURE_OPENAI_EMBEDDING_ENDPOINT",
    "https://vineesh-ai-uae-resource.services.ai.azure.com/openai/v1",
).rstrip("/")


def clean_text(value: Any) -> str:
    """Normalize formatting noise while preserving the ticket's meaning."""
    if value is None:
        return ""
    text = str(value).replace("\x00", "")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _value(ticket: Mapping[str, Any], *names: str) -> str:
    for name in names:
        if ticket.get(name) is not None and clean_text(ticket.get(name)):
            return clean_text(ticket.get(name))
    return ""


def _metadata_value(value: Any) -> str | int | float | bool:
    """Chroma metadata supports scalar values, not None or nested objects."""
    if isinstance(value, (bool, int, float)):
        return value
    return clean_text(value)


def _base_metadata(ticket: Mapping[str, Any], chunk_index: int) -> dict[str, Any]:
    ticket_id = _value(ticket, "ticket_id", "id")
    project_id = _value(ticket, "project_id")
    fields = {
        "ticket_id": clean_text(ticket_id),
        "project_id": clean_text(project_id),
        "chunk_index": chunk_index,
        "title": _value(ticket, "ticket_title", "title"),
        "assigned_to": _value(ticket, "assigned_user_name", "assigned_to"),
        "created_by": _value(ticket, "ticket_created_by", "created_by"),
        "created_on": _value(ticket, "ticket_created_at", "created_at"),
        "updated_by": _value(ticket, "ticket_updated_by", "updated_by"),
        "updated_on": _value(ticket, "ticket_updated_at", "updated_at"),
        "source": "project_ticket",
    }
    return {key: _metadata_value(value) for key, value in fields.items()}


def ticket_chunks(ticket: Mapping[str, Any]) -> list[Document]:
    """Build deterministic, logical ticket sections with identity on every chunk."""
    sections = [
        ("Identity", [
            ("Ticket ID", _value(ticket, "ticket_id", "id")),
            ("Title", _value(ticket, "ticket_title", "title")),
            ("Project ID", _value(ticket, "project_id")),
            ("Project Name", _value(ticket, "project_name")),
        ]),
        ("Description", [
            ("Ticket Description", _value(ticket, "ticket_description", "description")),
            ("Project Description", _value(ticket, "project_description")),
        ]),
        ("Assignment", [
            ("Assigned User", _value(ticket, "assigned_user_name", "assigned_to")),
            ("Ticket Created By", _value(ticket, "ticket_created_by", "created_by")),
        ]),
        ("Workflow", [
            ("Status", _value(ticket, "status_name", "status")),
            ("Due Date", _value(ticket, "ticket_due_date", "due_date")),
        ]),
        ("Activity", [
            ("Ticket Created At", _value(ticket, "ticket_created_at", "created_at")),
            ("Ticket Updated At", _value(ticket, "ticket_updated_at", "updated_at")),
            ("Ticket Updated By", _value(ticket, "ticket_updated_by", "updated_by")),
        ]),
    ]
    documents: list[Document] = []
    for index, (section_name, values) in enumerate(sections):
        content = "\n".join(f"{label}: {value}" for label, value in values if value)
        if not content:
            continue
        metadata = _base_metadata(ticket, index)
        metadata["section"] = section_name
        documents.append(Document(page_content=content, metadata=metadata))
    return documents


@lru_cache(maxsize=1)
def call_embeddings() -> OpenAIEmbeddings:
    try:
        if not API_KEY:
            raise RuntimeError("AZURE_OPENAI_API_KEY is missing.")
        return OpenAIEmbeddings(
            model=EMBEDDING_MODEL,
            api_key=API_KEY,
            base_url=BASE_URL,
        )
    except Exception as e:
        logger.error("Failed to initialize OpenAIEmbeddings: %s", e)
        raise


initialize_embedding_model = call_embeddings


def get_vector_store(embeddings: Any | None = None) -> Chroma:
    return Chroma(
        collection_name=COLLECTION_NAME,
        persist_directory=PERSIST_DIRECTORY,
        embedding_function=embeddings or call_embeddings(),
        collection_metadata={"hnsw:space": "cosine"},
    )


def document_id(document: Document) -> str:
    ticket_id = str(document.metadata.get("ticket_id", "unknown"))
    index = str(document.metadata.get("chunk_index", "0"))
    digest = hashlib.sha256(document.page_content.encode("utf-8")).hexdigest()[:12]
    return f"ticket-{ticket_id}-chunk-{index}-{digest}"


def store_ticket(ticket: Mapping[str, Any], embeddings: Any | None = None) -> int:
    try:
        documents = ticket_chunks(ticket)
        if not documents:
            logger.warning("Ticket %s has no indexable content", ticket.get("ticket_id", ticket.get("id")))
            return 0
        store = get_vector_store(embeddings)
        ticket_id = _value(ticket, "ticket_id", "id")
        existing = store._collection.get(where={"ticket_id": ticket_id}, include=[])
        old_ids = existing.get("ids", [])
        if old_ids:
            store._collection.delete(ids=old_ids)
        store.add_documents(
            documents,
            ids=[document_id(document) for document in documents],
        )
        logger.info("Indexed ticket %s in %d chunks", ticket_id, len(documents))
        return len(documents)
    except Exception as e:
        logger.error("Error " , e)
        return 0


def delete_ticket(ticket_id: Any, embeddings: Any | None = None) -> int:
    store = get_vector_store(embeddings)
    result = store._collection.get(where={"ticket_id": _metadata_value(ticket_id)}, include=[])
    ids = result.get("ids", [])
    if ids:
        store._collection.delete(ids=ids)
    logger.info("Deleted %d chunks for ticket %s", len(ids), ticket_id)
    return len(ids)


def store_vectors(documents: Iterable[Document], embeddings: Any) -> int:
    """Compatibility wrapper for the original public function."""
    documents = list(documents)
    if not documents:
        return 0
    store = get_vector_store(embeddings)
    store.add_documents(
        documents,
        ids=[document_id(document) for document in documents],
    )
    return len(documents)
