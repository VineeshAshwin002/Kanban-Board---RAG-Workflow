"""Ticket-to-vector-store synchronization helpers."""

from __future__ import annotations

import logging
from typing import Any, Mapping

from .rag_embedding import delete_ticket, store_ticket

logger = logging.getLogger(__name__)


def synchronize_ticket(ticket: Mapping[str, Any]) -> int:
    """Replace every indexed chunk for one ticket, leaving other tickets intact."""
    return store_ticket(ticket)


def create_ticket_embedding(ticket: Mapping[str, Any]) -> int:
    return synchronize_ticket(ticket)


def update_ticket_embedding(ticket: Mapping[str, Any]) -> int:
    return synchronize_ticket(ticket)


def delete_ticket_embedding(ticket_id: Any) -> int:
    return delete_ticket(ticket_id)


def sync_ticket(ticket: Mapping[str, Any]) -> int:
    return synchronize_ticket(ticket)
