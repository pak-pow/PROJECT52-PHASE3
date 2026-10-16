"""Remote cursor and selection transformation algorithms for collaborative presence."""

import hashlib
from typing import Optional, Tuple

from app.engine.operation import OpKind, TextOperation

PRESENCE_COLORS = [
    "#3b82f6",  # Blue
    "#10b981",  # Emerald
    "#f59e0b",  # Amber
    "#ec4899",  # Pink
    "#8b5cf6",  # Purple
    "#06b6d4",  # Cyan
    "#f97316",  # Orange
    "#14b8a6",  # Teal
    "#e11d48",  # Rose
    "#84cc16",  # Lime
]


def get_user_color(user_name: str) -> str:
    """Derive a deterministic, distinct pastel color for a given user name."""
    if not user_name:
        return PRESENCE_COLORS[0]
    hasher = hashlib.md5(user_name.encode("utf-8"), usedforsecurity=False)
    index = int(hasher.hexdigest(), 16) % len(PRESENCE_COLORS)
    return PRESENCE_COLORS[index]


def transform_cursor_position(cursor_pos: int, operation: TextOperation) -> int:
    """Transform a single cursor position against an applied TextOperation.

    Adjusts cursor offset so it maintains its relative position in the text
    when concurrent insertions or deletions occur.

    Args:
        cursor_pos: The 0-based character offset before operation is applied.
        operation: The TextOperation applied to the document.

    Returns:
        The new 0-based character offset after operation is applied.
    """
    if cursor_pos <= 0:
        # If cursor at or before start, any initial insert pushes cursor forward
        new_pos = 0
        for comp in operation.components:
            if comp.kind == OpKind.INSERT:
                new_pos += len(str(comp.value))
            else:
                break
        return new_pos

    new_pos = 0
    orig_pos = 0

    for comp in operation.components:
        if comp.kind == OpKind.RETAIN:
            count = int(comp.value)
            if cursor_pos < orig_pos + count:
                # Cursor is strictly inside this retained block
                return new_pos + (cursor_pos - orig_pos)
            new_pos += count
            orig_pos += count

        elif comp.kind == OpKind.INSERT:
            new_pos += len(str(comp.value))

        elif comp.kind == OpKind.DELETE:
            count = int(comp.value)
            del_end = orig_pos + count
            if cursor_pos < del_end:
                # Cursor was inside deleted span; collapse to deletion start
                return new_pos
            orig_pos = del_end

    return min(new_pos, operation.target_length)


def transform_selection(
    start: int, end: Optional[int], operation: TextOperation
) -> Tuple[int, Optional[int]]:
    """Transform both boundaries of a text selection range against an operation.

    Args:
        start: Selection anchor offset.
        end: Selection active head offset (or None if no range selected).
        operation: The TextOperation applied to the document.

    Returns:
        Tuple of (transformed_start, transformed_end).
    """
    new_start = transform_cursor_position(start, operation)
    if end is None:
        return new_start, None

    new_end = transform_cursor_position(end, operation)
    return new_start, new_end
