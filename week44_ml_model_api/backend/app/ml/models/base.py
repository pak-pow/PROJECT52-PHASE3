"""Abstract base class and numerical utilities for PulseInfer inference models."""

import abc
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import numpy as np


class BaseModel(abc.ABC):
    """Abstract base class for domain-specific PulseInfer machine learning models."""

    def __init__(
        self,
        model_id: str,
        version: str,
        domain: str,
        weights: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Initialize base model with identifiers, domain category, and weights."""
        self.model_id = model_id
        self.version = version
        self.domain = domain
        self.weights = weights or {}

    @classmethod
    def load_from_file(cls, filepath: Union[str, Path]) -> "BaseModel":
        """Load model configuration and weights directly from a JSON artifact file."""
        target_path = Path(filepath)
        if not target_path.exists():
            raise FileNotFoundError(f"Model artifact not found at: {target_path}")

        with open(target_path, "r", encoding="utf-8") as f:
            weights_data = json.load(f)

        return cls.from_weights(weights_data)

    @classmethod
    @abc.abstractmethod
    def from_weights(cls, weights: Dict[str, Any]) -> "BaseModel":
        """Instantiate a concrete model instance from raw deserialized weights."""
        pass

    @abc.abstractmethod
    def predict(self, input_data: Any) -> Dict[str, Any]:
        """Perform inference on a single payload and return structured predictions."""
        pass

    @abc.abstractmethod
    def predict_batch(self, batch_data: List[Any]) -> List[Dict[str, Any]]:
        """Perform vectorized batch inference across a collection of inputs."""
        pass

    def get_schema(self) -> Dict[str, Any]:
        """Return input and output contract schemas for this model."""
        return {
            "model_id": self.model_id,
            "version": self.version,
            "domain": self.domain,
        }

    @staticmethod
    def softmax(logits: np.ndarray) -> np.ndarray:
        """Compute numerically stable softmax probability distribution."""
        logits_arr = np.array(logits, dtype=np.float64)
        if logits_arr.ndim == 1:
            shifted = logits_arr - np.max(logits_arr)
            exp_vals = np.exp(shifted)
            sum_exp = np.sum(exp_vals)
            return exp_vals / (sum_exp if sum_exp > 0 else 1.0)

        shifted = logits_arr - np.max(logits_arr, axis=-1, keepdims=True)
        exp_vals = np.exp(shifted)
        sum_exp = np.sum(exp_vals, axis=-1, keepdims=True)
        return exp_vals / np.where(sum_exp > 0, sum_exp, 1.0)

    @staticmethod
    def sigmoid(z: Union[float, np.ndarray]) -> Union[float, np.ndarray]:
        """Compute numerically stable logistic sigmoid activation."""
        z_arr = np.clip(np.array(z, dtype=np.float64), -500.0, 500.0)
        return 1.0 / (1.0 + np.exp(-z_arr))
