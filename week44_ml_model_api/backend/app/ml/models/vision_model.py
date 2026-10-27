"""Computer Vision image classification model."""

from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from app.ml.models.base import BaseModel
from app.ml.preprocessors import ImageTensorPipeline


class VisionClassifier(BaseModel):
    """Linear projection and normalized tensor classifier for visual domains."""

    DEFAULT_CLASSES = ["landscape", "document", "portrait", "product"]

    def __init__(
        self,
        model_id: str = "vision-classifier",
        version: str = "v1",
        classes: Optional[List[str]] = None,
        target_size: Tuple[int, int] = (32, 32),
        projection_weights: Optional[np.ndarray] = None,
        bias: Optional[List[float]] = None,
        weights: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Initialize vision classifier with dimension targets and class projections."""
        super().__init__(
            model_id=model_id,
            version=version,
            domain="vision",
            weights=weights or {},
        )
        self.classes = classes or self.DEFAULT_CLASSES
        self.target_size = target_size
        self.projection_weights = projection_weights
        self.bias = np.array(
            bias or [0.1 * idx for idx in range(len(self.classes))],
            dtype=np.float64,
        )
        self.pipeline = ImageTensorPipeline(target_size=target_size, flatten=True)

    @classmethod
    def from_weights(cls, weights: Dict[str, Any]) -> "VisionClassifier":
        """Build VisionClassifier instance from weights dictionary artifact."""
        model_id = weights.get("model_id", "vision-classifier")
        version = weights.get("version", "v1")
        classes = weights.get("classes", cls.DEFAULT_CLASSES)
        raw_size = weights.get("target_size", [32, 32])
        target_size = (int(raw_size[0]), int(raw_size[1]))

        raw_weights = weights.get("projection_weights")
        proj_arr = (
            np.array(raw_weights, dtype=np.float64) if raw_weights is not None else None
        )
        bias = weights.get("bias")

        return cls(
            model_id=model_id,
            version=version,
            classes=classes,
            target_size=target_size,
            projection_weights=proj_arr,
            bias=bias,
            weights=weights,
        )

    def _extract_image_input(self, input_data: Any) -> Any:
        """Extract base64 string or image buffer from dictionary payload."""
        if isinstance(input_data, dict):
            return (
                input_data.get("image_base64")
                or input_data.get("image")
                or input_data.get("data")
                or ""
            )
        return input_data

    def _compute_logits(self, tensor: np.ndarray) -> np.ndarray:
        """Calculate class logits from preprocessed image tensor vector."""
        num_classes = len(self.classes)
        logits = np.zeros(num_classes, dtype=np.float64)

        if self.bias is not None and len(self.bias) == num_classes:
            logits += self.bias

        if self.projection_weights is not None:
            weights_arr = np.array(self.projection_weights, dtype=np.float64)
            if weights_arr.shape == (1, num_classes):
                # Scale projection weights by mean tensor luminance
                scalar_signal = float(np.mean(tensor))
                logits += scalar_signal * weights_arr[0]
            elif weights_arr.shape == (len(tensor), num_classes):
                logits += np.dot(tensor, weights_arr)
            else:
                # Summary pooling projection
                chunk_size = max(1, len(tensor) // num_classes)
                for idx in range(num_classes):
                    start = idx * chunk_size
                    end = min(len(tensor), (idx + 1) * chunk_size)
                    logits[idx] += float(np.mean(tensor[start:end]))
        else:
            # Fallback deterministic partition
            chunk_size = max(1, len(tensor) // num_classes)
            for idx in range(num_classes):
                start = idx * chunk_size
                end = min(len(tensor), (idx + 1) * chunk_size)
                logits[idx] += float(np.mean(tensor[start:end]))

        return logits

    def predict(self, input_data: Any) -> Dict[str, Any]:
        """Classify a single image and return scores for each class."""
        raw_input = self._extract_image_input(input_data)
        tensor = self.pipeline.transform(raw_input)
        logits = self._compute_logits(tensor)
        probs = self.softmax(logits)

        best_idx = int(np.argmax(probs))
        top_class = self.classes[best_idx]
        confidence = float(np.round(probs[best_idx], 4))

        scores = {
            self.classes[i]: float(np.round(probs[i], 4))
            for i in range(len(self.classes))
        }

        return {
            "top_class": top_class,
            "confidence": confidence,
            "class_scores": scores,
        }

    def predict_batch(self, batch_data: List[Any]) -> List[Dict[str, Any]]:
        """Vectorize inference across multiple visual inputs."""
        if not batch_data:
            return []
        return [self.predict(item) for item in batch_data]

    def get_schema(self) -> Dict[str, Any]:
        """Return input and output contract schemas for Vision classifier."""
        schema = super().get_schema()
        schema.update(
            {
                "input_schema": {"image_base64": "string"},
                "output_schema": {
                    "top_class": "string",
                    "confidence": "float",
                    "class_scores": "dict",
                },
            }
        )
        return schema
