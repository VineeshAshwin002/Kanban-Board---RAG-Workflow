"""Backward-compatible imports for the original RAG integration points."""

from .rag_embedding import call_embeddings, initialize_embedding_model, store_vectors
from .rag_retriever import get_documents

__all__ = ["call_embeddings", "initialize_embedding_model", "store_vectors", "get_documents"]
