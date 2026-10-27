"""Tabular fraud detection and risk scoring model."""

from typing import Any, Dict, List, Optional

import numpy as np

from app.ml.models.base import BaseModel
from app.ml.preprocessors import TabularScaler


class FraudDetector(BaseModel):
    """Calibrated logistic regression model for tabular transaction fraud detection."""

    DEFAULT_FEATURES = [
        "transaction_amount",
        "user_age",
        "velocity_1h",
        "is_foreign",
    ]
    DEFAULT_COEFFICIENTS = [0.005, -0.02, 0.35, 1.2]
    DEFAULT_INTERCEPT = -1.8
    DEFAULT_THRESHOLD = 0.5

    def __init__(
        self,
        model_id: str = "fraud-detector",
        version: str = "v1",
        features: Optional[List[str]] = None,
        coefficients: Optional[List[float]] = None,
        intercept: float = DEFAULT_INTERCEPT,
        threshold: float = DEFAULT_THRESHOLD,
        means: Optional[Dict[str, float]] = None,
        stds: Optional[Dict[str, float]] = None,
        weights: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Initialize fraud detector with feature definitions, weights, and rules."""
        super().__init__(
            model_id=model_id,
            version=version,
            domain="tabular",
            weights=weights or {},
        )
        self.features = features or self.DEFAULT_FEATURES
        self.coefficients = np.array(
            coefficients if coefficients is not None else self.DEFAULT_COEFFICIENTS,
            dtype=np.float64,
        )
        self.intercept = float(intercept)
        self.threshold = float(threshold)
        self.means = means
        self.stds = stds

        # Tabular scaler used if scaling parameters are specified
        self.scaler = (
            TabularScaler(feature_names=self.features, means=means, stds=stds)
            if (means and stds)
            else None
        )

    @classmethod
    def from_weights(cls, weights: Dict[str, Any]) -> "FraudDetector":
        """Build FraudDetector instance from weights dictionary artifact."""
        model_id = weights.get("model_id", "fraud-detector")
        version = weights.get("version", "v1")
        features = weights.get("features", cls.DEFAULT_FEATURES)
        coefficients = weights.get("coefficients", cls.DEFAULT_COEFFICIENTS)
        intercept = weights.get("intercept", cls.DEFAULT_INTERCEPT)
        threshold = weights.get("threshold", cls.DEFAULT_THRESHOLD)
        means = weights.get("means")
        stds = weights.get("stds")

        return cls(
            model_id=model_id,
            version=version,
            features=features,
            coefficients=coefficients,
            intercept=intercept,
            threshold=threshold,
            means=means,
            stds=stds,
            weights=weights,
        )

    def _extract_vector(self, data: Dict[str, Any]) -> np.ndarray:
        """Extract and optionally scale feature vector from input record."""
        if self.scaler:
            return self.scaler.transform(data)

        vec = np.zeros(len(self.features), dtype=np.float64)
        for idx, col in enumerate(self.features):
            val = data.get(col, 0.0)
            try:
                vec[idx] = float(val) if val is not None else 0.0
            except (ValueError, TypeError):
                vec[idx] = 0.0
        return vec

    def _determine_risk_level(self, risk_score: float) -> str:
        """Categorize numerical risk score into qualitative risk tier."""
        if risk_score >= 0.75:
            return "HIGH"
        elif risk_score >= 0.40:
            return "MEDIUM"
        return "LOW"

    def predict(self, input_data: Any) -> Dict[str, Any]:
        """Compute fraud probability and risk score for a single transaction."""
        data_dict = input_data if isinstance(input_data, dict) else {}
        vec = self._extract_vector(data_dict)

        logit = self.intercept + float(np.dot(vec, self.coefficients))
        risk_score = float(np.round(self.sigmoid(logit), 4))
        is_flagged = bool(risk_score >= self.threshold)
        risk_level = self._determine_risk_level(risk_score)

        return {
            "risk_score": risk_score,
            "is_flagged": is_flagged,
            "risk_level": risk_level,
        }

    def predict_batch(self, batch_data: List[Any]) -> List[Dict[str, Any]]:
        """Vectorize inference across a batch of tabular transaction records."""
        if not batch_data:
            return []

        # Vectorized batch computation
        vectors = np.array(
            [
                self._extract_vector(item if isinstance(item, dict) else {})
                for item in batch_data
            ],
            dtype=np.float64,
        )

        logits = self.intercept + np.dot(vectors, self.coefficients)
        probs = np.array(self.sigmoid(logits), dtype=np.float64)

        results: List[Dict[str, Any]] = []
        for p in probs:
            score = float(np.round(p, 4))
            results.append(
                {
                    "risk_score": score,
                    "is_flagged": bool(score >= self.threshold),
                    "risk_level": self._determine_risk_level(score),
                }
            )

        return results

    def get_schema(self) -> Dict[str, Any]:
        """Return input and output contract schemas for Fraud Detector."""
        schema = super().get_schema()
        schema.update(
            {
                "input_schema": {
                    feat: "float" if "amount" in feat else "int"
                    for feat in self.features
                },
                "output_schema": {
                    "risk_score": "float",
                    "is_flagged": "bool",
                    "risk_level": "string",
                },
            }
        )
        return schema
