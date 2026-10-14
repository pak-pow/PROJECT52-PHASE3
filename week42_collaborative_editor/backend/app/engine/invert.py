"""Operation inversion algorithm for generating undo and redo inverses."""

from app.engine.operation import OpKind, TextOperation


def invert(op: TextOperation, document_text: str) -> TextOperation:
    """Invert an operation against document text to generate its undo inverse.

    Given an operation op applied to document_text:
        new_text = op.apply(document_text)
        inverted_op = invert(op, document_text)
        inverted_op.apply(new_text) == document_text

    Args:
        op: The operation to invert.
        document_text: The document string before op was applied.

    Returns:
        The inverted TextOperation.

    Raises:
        ValueError: If len(document_text) does not match op.base_length.
    """
    if len(document_text) != op.base_length:
        raise ValueError(
            f"Cannot invert operation: document_text length ({len(document_text)}) "
            f"does not match operation base_length ({op.base_length})"
        )

    inverse = TextOperation()
    cursor = 0

    for comp in op.components:
        if comp.kind == OpKind.RETAIN:
            count = int(comp.value)
            inverse.retain(count)
            cursor += count
        elif comp.kind == OpKind.INSERT:
            text = str(comp.value)
            inverse.delete(len(text))
        elif comp.kind == OpKind.DELETE:
            count = int(comp.value)
            end_pos = cursor + count
            deleted_text = document_text[cursor:end_pos]
            inverse.insert(deleted_text)
            cursor = end_pos

    if cursor != len(document_text):
        raise ValueError(
            f"Operation ended at cursor {cursor}, expected {len(document_text)}"
        )

    return inverse
