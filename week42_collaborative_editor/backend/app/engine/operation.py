"""Operational Transformation operation definitions and data models."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Union


class OpKind(str, Enum):
    """Operation component types."""

    RETAIN = "retain"
    INSERT = "insert"
    DELETE = "delete"


@dataclass
class OpComponent:
    """Single atomic component within a text operation."""

    kind: OpKind
    value: Union[int, str]

    def to_dict(self) -> Dict[str, Any]:
        """Serialize component to dictionary."""
        return {"kind": self.kind.value, "value": self.value}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "OpComponent":
        """Deserialize component from dictionary."""
        return cls(kind=OpKind(data["kind"]), value=data["value"])


@dataclass
class TextOperation:
    """Compound text operation composed of sequential atomic components."""

    components: List[OpComponent] = field(default_factory=list)
    base_length: int = 0
    target_length: int = 0

    def retain(self, count: int) -> "TextOperation":
        """Retain count characters without alteration."""
        if count <= 0:
            return self
        if self.components and self.components[-1].kind == OpKind.RETAIN:
            prev = self.components[-1]
            self.components[-1] = OpComponent(OpKind.RETAIN, int(prev.value) + count)
        else:
            self.components.append(OpComponent(OpKind.RETAIN, count))
        self.base_length += count
        self.target_length += count
        return self

    def insert(self, text: str) -> "TextOperation":
        """Insert string at current position."""
        if not text:
            return self
        if self.components and self.components[-1].kind == OpKind.INSERT:
            prev = self.components[-1]
            self.components[-1] = OpComponent(OpKind.INSERT, str(prev.value) + text)
        else:
            self.components.append(OpComponent(OpKind.INSERT, text))
        self.target_length += len(text)
        return self

    def delete(self, count_or_text: Union[int, str]) -> "TextOperation":
        """Delete characters at current position."""
        count = len(count_or_text) if isinstance(count_or_text, str) else count_or_text
        if count <= 0:
            return self
        if self.components and self.components[-1].kind == OpKind.DELETE:
            prev = self.components[-1]
            self.components[-1] = OpComponent(OpKind.DELETE, int(prev.value) + count)
        else:
            self.components.append(OpComponent(OpKind.DELETE, count))
        self.base_length += count
        return self

    def is_noop(self) -> bool:
        """Check if operation performs no textual modifications."""
        return all(c.kind == OpKind.RETAIN for c in self.components)

    def copy(self) -> "TextOperation":
        """Return a deep copy of the operation."""
        return TextOperation(
            components=[OpComponent(c.kind, c.value) for c in self.components],
            base_length=self.base_length,
            target_length=self.target_length,
        )

    def __eq__(self, other: object) -> bool:
        """Compare two operations for equality."""
        if not isinstance(other, TextOperation):
            return False
        return (
            self.base_length == other.base_length
            and self.target_length == other.target_length
            and len(self.components) == len(other.components)
            and all(
                c1.kind == c2.kind and c1.value == c2.value
                for c1, c2 in zip(self.components, other.components)
            )
        )

    def apply(self, document_text: str) -> str:
        """Apply operation components sequentially to a source string."""
        if len(document_text) != self.base_length:
            raise ValueError(
                f"Operation base_length ({self.base_length}) does not match "
                f"document text length ({len(document_text)})"
            )

        result_parts: List[str] = []
        cursor = 0

        for comp in self.components:
            if comp.kind == OpKind.RETAIN:
                count = int(comp.value)
                end_pos = cursor + count
                result_parts.append(document_text[cursor:end_pos])
                cursor = end_pos
            elif comp.kind == OpKind.INSERT:
                result_parts.append(str(comp.value))
            elif comp.kind == OpKind.DELETE:
                count = int(comp.value)
                cursor += count

        if cursor != len(document_text):
            raise ValueError(
                f"Operation ended at cursor {cursor}, " f"expected {len(document_text)}"
            )

        new_text = "".join(result_parts)
        if len(new_text) != self.target_length:
            raise ValueError(
                f"Result text length ({len(new_text)}) does not match "
                f"operation target_length ({self.target_length})"
            )
        return new_text

    def to_dict(self) -> Dict[str, Any]:
        """Serialize entire operation."""
        return {
            "components": [c.to_dict() for c in self.components],
            "base_length": self.base_length,
            "target_length": self.target_length,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TextOperation":
        """Deserialize operation from dictionary, computing lengths if omitted."""
        components = [OpComponent.from_dict(c) for c in data.get("components", [])]
        base_len = data.get("base_length")
        target_len = data.get("target_length")
        if base_len is None:
            base_len = sum(
                int(c.value) if c.kind != OpKind.INSERT else 0 for c in components
            )
        if target_len is None:
            target_len = sum(
                (
                    int(c.value)
                    if c.kind == OpKind.RETAIN
                    else (len(str(c.value)) if c.kind == OpKind.INSERT else 0)
                )
                for c in components
            )
        return cls(
            components=components,
            base_length=base_len,
            target_length=target_len,
        )


def create_operation_from_diff(old_text: str, new_text: str) -> TextOperation:
    """Derive an optimal TextOperation transforming old_text into new_text."""
    if old_text == new_text:
        op = TextOperation()
        if old_text:
            op.retain(len(old_text))
        return op

    prefix_len = 0
    max_prefix = min(len(old_text), len(new_text))
    while prefix_len < max_prefix and old_text[prefix_len] == new_text[prefix_len]:
        prefix_len += 1

    suffix_len = 0
    max_suffix = min(len(old_text) - prefix_len, len(new_text) - prefix_len)
    while (
        suffix_len < max_suffix
        and old_text[len(old_text) - 1 - suffix_len]
        == new_text[len(new_text) - 1 - suffix_len]
    ):
        suffix_len += 1

    delete_len = len(old_text) - prefix_len - suffix_len
    inserted_end = len(new_text) - suffix_len
    inserted_text = new_text[prefix_len:inserted_end]

    op = TextOperation()
    if prefix_len > 0:
        op.retain(prefix_len)
    if delete_len > 0:
        op.delete(delete_len)
    if inserted_text:
        op.insert(inserted_text)
    if suffix_len > 0:
        op.retain(suffix_len)

    return op
