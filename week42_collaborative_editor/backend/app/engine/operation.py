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
                f"Operation ended at cursor {cursor}, expected {len(document_text)}"
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
        """Deserialize operation from dictionary."""
        components = [OpComponent.from_dict(c) for c in data.get("components", [])]
        return cls(
            components=components,
            base_length=data.get("base_length", 0),
            target_length=data.get("target_length", 0),
        )
