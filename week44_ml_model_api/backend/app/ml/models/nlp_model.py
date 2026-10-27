"""NLP text sentiment and intent classification model."""

from typing import Any, Dict, List, Optional

import numpy as np

from app.ml.models.base import BaseModel
from app.ml.preprocessors import TextTokenizer


class NLPClassifier(BaseModel):
    """Linear projection and Softmax classifier for sentiment and intent."""

    DEFAULT_CLASSES = ["negative", "neutral", "positive"]

    def __init__(
        self,
        model_id: str = "nlp-sentiment",
        version: str = "v1",
        classes: Optional[List[str]] = None,
        vocabulary: Optional[Dict[str, float]] = None,
        bias: Optional[List[float]] = None,
        projection_matrix: Optional[np.ndarray] = None,
        weights: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Initialize NLP classifier with vocabulary weights, bias, and classes."""
        super().__init__(
            model_id=model_id,
            version=version,
            domain="nlp",
            weights=weights or {},
        )
        self.classes = classes or self.DEFAULT_CLASSES
        self.vocabulary = vocabulary or {}
        self.bias = np.array(bias or [0.1, 0.5, 0.1], dtype=np.float64)
        self.projection_matrix = projection_matrix
        self.tokenizer = TextTokenizer()

    @classmethod
    def from_weights(cls, weights: Dict[str, Any]) -> "NLPClassifier":
        """Build NLPClassifier instance from weights dictionary artifact."""
        model_id = weights.get("model_id", "nlp-sentiment")
        version = weights.get("version", "v1")
        classes = weights.get("classes", cls.DEFAULT_CLASSES)
        vocab = weights.get("vocabulary", {})
        bias = weights.get("bias", [0.1, 0.5, 0.1])
        proj = weights.get("projection_matrix")
        proj_arr = np.array(proj, dtype=np.float64) if proj is not None else None

        return cls(
            model_id=model_id,
            version=version,
            classes=classes,
            vocabulary=vocab,
            bias=bias,
            projection_matrix=proj_arr,
            weights=weights,
        )

    def _extract_text(self, input_data: Any) -> str:
        """Extract raw text string from dictionary or scalar payload."""
        if isinstance(input_data, dict):
            return str(input_data.get("text") or input_data.get("input") or "")
        return str(input_data or "")

    def _compute_logits(self, text: str) -> np.ndarray:
        """Calculate class logits from extracted token features."""
        tokens = self.tokenizer.tokenize(text)
        score = sum(self.vocabulary.get(token, 0.0) for token in tokens)

        # Map aggregate sentiment score into class logits
        logits = np.copy(self.bias)
        if len(logits) == 3:
            # [negative, neutral, positive]
            neg_boost = max(0.0, -score) * 1.5
            neu_boost = max(0.0, 1.0 - abs(score)) * 0.8
            pos_boost = max(0.0, score) * 1.5

            logits[0] += neg_boost
            logits[1] += neu_boost
            logits[2] += pos_boost
        else:
            # Generic multi-class logit accumulation
            for idx in range(len(logits)):
                logits[idx] += score / (idx + 1.0)

        return logits

    def predict(self, input_data: Any) -> Dict[str, Any]:
        """Classify a single text snippet and return probabilities and top class."""
        text = self._extract_text(input_data)
        logits = self._compute_logits(text)
        probs = self.softmax(logits)

        best_idx = int(np.argmax(probs))
        top_class = self.classes[best_idx]
        confidence = float(np.round(probs[best_idx], 4))

        prob_dict = {
            self.classes[i]: float(np.round(probs[i], 4))
            for i in range(len(self.classes))
        }

        return {
            "sentiment": top_class,
            "confidence": confidence,
            "probabilities": prob_dict,
        }

    def predict_batch(self, batch_data: List[Any]) -> List[Dict[str, Any]]:
        """Vectorize inference across multiple text samples."""
        if not batch_data:
            return []
        return [self.predict(item) for item in batch_data]

    def get_schema(self) -> Dict[str, Any]:
        """Return input and output contract schemas for NLP sentiment model."""
        schema = super().get_schema()
        schema.update(
            {
                "input_schema": {"text": "string"},
                "output_schema": {
                    "sentiment": "string",
                    "confidence": "float",
                    "probabilities": "dict",
                },
            }
        )
        return schema
