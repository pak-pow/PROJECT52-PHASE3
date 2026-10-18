"""Operational transformation engine package for PulsePad."""

from app.engine.compose import compose
from app.engine.cursor import (
    PRESENCE_COLORS,
    get_user_color,
    transform_cursor_position,
    transform_selection,
)
from app.engine.document import DocumentState
from app.engine.invert import invert
from app.engine.operation import (
    OpComponent,
    OpKind,
    TextOperation,
    create_operation_from_diff,
)
from app.engine.transform import transform

__all__ = [
    "OpComponent",
    "OpKind",
    "TextOperation",
    "DocumentState",
    "compose",
    "invert",
    "transform",
    "get_user_color",
    "transform_cursor_position",
    "transform_selection",
    "PRESENCE_COLORS",
    "create_operation_from_diff",
]
