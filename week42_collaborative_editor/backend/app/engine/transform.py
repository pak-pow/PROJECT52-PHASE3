"""Operational transformation function module for concurrent text edits."""

from typing import Tuple

from app.engine.operation import TextOperation


def transform(
    op1: TextOperation, op2: TextOperation, client_priority: bool = True
) -> Tuple[TextOperation, TextOperation]:
    """Transform two concurrent operations against each other."""
    # Scheduled for Day 2 implementation
    return op1, op2
