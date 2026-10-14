"""Operation composition algorithm for combining consecutive text edits."""

from app.engine.operation import OpComponent, OpKind, TextOperation


def compose(op1: TextOperation, op2: TextOperation) -> TextOperation:
    """Compose two consecutive operations into a single combined operation.

    Given op1: A -> B and op2: B -> C, produces op_composed: A -> C such that:
        apply(apply(S, op1), op2) == apply(S, op_composed)

    Args:
        op1: The first operation applied to state A.
        op2: The second operation applied to state B.

    Returns:
        A combined TextOperation representing op1 followed by op2.

    Raises:
        ValueError: If op1.target_length does not equal op2.base_length.
    """
    if op1.target_length != op2.base_length:
        raise ValueError(
            f"Cannot compose operations: op1.target_length ({op1.target_length}) "
            f"!= op2.base_length ({op2.base_length})"
        )

    op_composed = TextOperation()
    comps1 = [OpComponent(c.kind, c.value) for c in op1.components]
    comps2 = [OpComponent(c.kind, c.value) for c in op2.components]

    i = 0
    j = 0

    while i < len(comps1) or j < len(comps2):
        c1 = comps1[i] if i < len(comps1) else None
        c2 = comps2[j] if j < len(comps2) else None

        # Case 1: op1 deletes characters from original document A
        if c1 is not None and c1.kind == OpKind.DELETE:
            op_composed.delete(int(c1.value))
            i += 1
            continue

        # Case 2: op2 inserts characters into document C
        if c2 is not None and c2.kind == OpKind.INSERT:
            op_composed.insert(str(c2.value))
            j += 1
            continue

        if c1 is None or c2 is None:
            raise ValueError(
                "Cannot compose operations: mismatched intermediate lengths"
            )

        len1 = len(str(c1.value)) if c1.kind == OpKind.INSERT else int(c1.value)
        len2 = int(c2.value)
        min_len = min(len1, len2)

        if c1.kind == OpKind.RETAIN and c2.kind == OpKind.RETAIN:
            op_composed.retain(min_len)
        elif c1.kind == OpKind.INSERT and c2.kind == OpKind.RETAIN:
            op_composed.insert(str(c1.value)[:min_len])
        elif c1.kind == OpKind.INSERT and c2.kind == OpKind.DELETE:
            # Inserted text was subsequently deleted; cancels out
            pass
        elif c1.kind == OpKind.RETAIN and c2.kind == OpKind.DELETE:
            op_composed.delete(min_len)

        if c1.kind == OpKind.INSERT:
            if len1 > min_len:
                c1.value = str(c1.value)[min_len:]
            else:
                i += 1
        else:
            if len1 > min_len:
                c1.value = len1 - min_len
            else:
                i += 1

        if len2 > min_len:
            c2.value = len2 - min_len
        else:
            j += 1

    return op_composed
