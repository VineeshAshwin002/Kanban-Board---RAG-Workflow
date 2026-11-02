"""Context-grounded answer generation and source formatting."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).resolve().parents[1] / ".env")

logger = logging.getLogger(__name__)
FALLBACK = "I don't know based on the provided ticket context."


def sources_for_context(context: list[dict[str, Any]]) -> list[dict[str, Any]]:
    sources = []
    seen: set[str] = set()
    template = os.getenv("TICKET_VIEW_URL_TEMPLATE", "").strip()
    for item in context:
        metadata = item.get("metadata", {})
        key = f"{metadata.get('project_id')}:{metadata.get('ticket_id')}"
        if key in seen:
            continue
        seen.add(key)
        source = {
            "project_id": metadata.get("project_id", ""),
            "ticket_id": metadata.get("ticket_id", ""),
            "title": metadata.get("title", ""),
        }
        if template and source["ticket_id"]:
            source["view_url"] = template.format(
                project_id=source["project_id"], ticket_id=source["ticket_id"]
            )
        sources.append(source)
    return sources


def _build_prompt(
    question: str,
    context: list[dict[str, Any]],
    history: list[dict[str, str]] | None = None,
) -> str:
    context_text = "\n\n".join(item["content"] for item in context)
    history_text = "\n".join(
        f"{item['role'].title()}: {item['content']}"
        for item in (history or [])
    )
    conversation = f"Previous conversation:\n{history_text}\n\n" if history_text else ""
    return (
        "Answer the question only from the ticket context below. "
        "If the context does not contain the answer, say exactly: " + FALLBACK + "\n"
        "Do not guess or combine unsupported details. Keep the answer concise.\n\n"
        f"{conversation}Question: {question}\n\nTicket context:\n{context_text}"
    )


def _create_chat_model():
    from langchain_openai import ChatOpenAI

    api_key = os.getenv("AZURE_OPENAI_API_KEY") or os.getenv("API_KEY")
    model = os.getenv("OPENAI_CHAT_MODEL", "gpt-4.1-mini")
    base_url = os.getenv(
        "AZURE_OPENAI_CHAT_ENDPOINT",
        "https://vineesh-ai-uae-resource.services.ai.azure.com/openai/v1",
    ).rstrip("/")
    if not api_key:
        raise RuntimeError("AZURE_OPENAI_API_KEY is missing")
    logger.info("Initializing OpenAI chat model: model=%s base_url=%s", model, base_url)
    return ChatOpenAI(
        model=model,
        api_key=api_key,
        base_url=base_url,
        temperature=0.5,
    )


def stream_answer(
    question: str,
    context: list[dict[str, Any]],
    history: list[dict[str, str]] | None = None,
):
    """Yield native provider chunks without buffering the completed answer."""
    if not context:
        yield FALLBACK
        return
    for chunk in _create_chat_model().stream(_build_prompt(question, context, history)):
        content = getattr(chunk, "content", chunk)
        if isinstance(content, str) and content:
            yield content


def generate_answer(question: str, context: list[dict[str, Any]]) -> dict[str, Any]:
    sources = sources_for_context(context)
    try:
        answer = "".join(stream_answer(question, context)).strip() or FALLBACK
    except Exception:
        logger.exception("Answer generation failed")
        answer = FALLBACK
    return {"answer": answer, "sources": sources}
