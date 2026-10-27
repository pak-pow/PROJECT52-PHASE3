"""Vectorized data preprocessing pipelines for NLP, Vision, and Tabular models."""

import base64
import io
import re
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np
from PIL import Image


class TextTokenizer:
    """Preprocesses and vectorizes raw text into token index or frequency matrices."""

    PUNCTUATION_REGEX = re.compile(r"[^\w\s]")

    def __init__(
        self,
        vocabulary: Optional[Dict[str, int]] = None,
        lower: bool = True,
        strip_punctuation: bool = True,
    ) -> None:
        """Initialize text tokenizer with optional pre-built vocabulary dictionary."""
        self.vocabulary = vocabulary or {}
        self.lower = lower
        self.strip_punctuation = strip_punctuation

    def tokenize(self, text: str) -> List[str]:
        """Normalize text and split into clean word tokens."""
        if not text or not isinstance(text, str):
            return []

        cleaned = text.lower() if self.lower else text
        if self.strip_punctuation:
            cleaned = self.PUNCTUATION_REGEX.sub(" ", cleaned)

        return [token.strip() for token in cleaned.split() if token.strip()]

    def build_vocab(self, texts: List[str], max_vocab: int = 1000) -> Dict[str, int]:
        """Construct a frequency-ranked word vocabulary mapping token to index."""
        counts: Dict[str, int] = {}
        for text in texts:
            for token in self.tokenize(text):
                counts[token] = counts.get(token, 0) + 1

        sorted_tokens = sorted(counts.items(), key=lambda x: x[1], reverse=True)
        self.vocabulary = {
            token: idx for idx, (token, _) in enumerate(sorted_tokens[:max_vocab])
        }
        return self.vocabulary

    def transform(self, text: str) -> np.ndarray:
        """Transform single text string into a 1D term frequency vector."""
        vocab_size = max(len(self.vocabulary), 1)
        vector = np.zeros(vocab_size, dtype=np.float32)

        if not self.vocabulary:
            return vector

        tokens = self.tokenize(text)
        for token in tokens:
            idx = self.vocabulary.get(token)
            if idx is not None and idx < vocab_size:
                vector[idx] += 1.0

        # Term frequency normalization
        total = np.sum(vector)
        if total > 0:
            vector /= total

        return vector

    def transform_batch(self, texts: List[str]) -> np.ndarray:
        """Transform text strings into a 2D matrix (batch_size, vocab)."""
        if not texts:
            vocab_size = max(len(self.vocabulary), 1)
            return np.zeros((0, vocab_size), dtype=np.float32)

        vectors = [self.transform(t) for t in texts]
        return np.vstack(vectors)


class ImageTensorPipeline:
    """Decodes, resizes, and normalizes visual inputs into numerical tensors."""

    DEFAULT_MEAN: List[float] = [0.485, 0.456, 0.406]
    DEFAULT_STD: List[float] = [0.229, 0.224, 0.225]

    def __init__(
        self,
        target_size: Tuple[int, int] = (32, 32),
        mean: Optional[List[float]] = None,
        std: Optional[List[float]] = None,
        flatten: bool = True,
    ) -> None:
        """Initialize image pipeline with target dimensions and scaling statistics."""
        self.target_size = target_size
        self.mean = np.array(mean or self.DEFAULT_MEAN, dtype=np.float32)
        self.std = np.array(std or self.DEFAULT_STD, dtype=np.float32)
        self.flatten = flatten

    def decode_image(self, input_data: Union[str, bytes, Image.Image]) -> Image.Image:
        """Decode base64 string, byte buffer, or PIL Image into standard RGB Image."""
        if isinstance(input_data, Image.Image):
            return input_data.convert("RGB")

        if isinstance(input_data, bytes):
            return Image.open(io.BytesIO(input_data)).convert("RGB")

        if isinstance(input_data, str):
            # Check for data URI prefix (e.g. data:image/png;base64,...)
            clean_str = input_data
            if "," in clean_str:
                clean_str = clean_str.split(",", 1)[1]

            try:
                decoded_bytes = base64.b64decode(clean_str.strip())
                return Image.open(io.BytesIO(decoded_bytes)).convert("RGB")
            except Exception:
                # If decoding fails or input is a placeholder string, create canvas
                img = Image.new("RGB", self.target_size, color=(128, 128, 128))
                return img

        # Fallback to neutral gray canvas
        return Image.new("RGB", self.target_size, color=(128, 128, 128))

    def transform(self, input_data: Union[str, bytes, Image.Image]) -> np.ndarray:
        """Transform image into a standardized floating-point tensor vector."""
        image = self.decode_image(input_data)
        resized = image.resize(self.target_size, Image.Resampling.BILINEAR)

        # Scale pixel values to [0.0, 1.0]
        array = np.array(resized, dtype=np.float32) / 255.0

        # Channel-wise normalization: (X - mean) / std
        normalized = (array - self.mean) / self.std

        if self.flatten:
            return normalized.flatten()
        # Returns shape: (channels, height, width)
        return np.transpose(normalized, (2, 0, 1))

    def transform_batch(
        self, inputs: List[Union[str, bytes, Image.Image]]
    ) -> np.ndarray:
        """Transform multiple image inputs into a contiguous batch tensor."""
        if not inputs:
            feature_dim = self.target_size[0] * self.target_size[1] * 3
            return np.zeros((0, feature_dim), dtype=np.float32)

        tensors = [self.transform(inp) for inp in inputs]
        return np.vstack(tensors)


class TabularScaler:
    """Preprocesses structured tabular records with imputation and z-score scaling."""

    def __init__(
        self,
        feature_names: List[str],
        means: Optional[Dict[str, float]] = None,
        stds: Optional[Dict[str, float]] = None,
        defaults: Optional[Dict[str, float]] = None,
    ) -> None:
        """Initialize tabular scaler with column expectations and scaling statistics."""
        self.feature_names = feature_names
        self.means = means or {col: 0.0 for col in feature_names}
        self.stds = stds or {col: 1.0 for col in feature_names}
        self.defaults = defaults or self.means

    def transform(self, data: Dict[str, Any]) -> np.ndarray:
        """Extract features, impute missing values, and apply standard scaling."""
        vector = np.zeros(len(self.feature_names), dtype=np.float32)

        for idx, col in enumerate(self.feature_names):
            raw_val = data.get(col)

            # Impute missing or invalid values
            if raw_val is None or not isinstance(raw_val, (int, float)):
                val = self.defaults.get(col, 0.0)
            else:
                val = float(raw_val)

            mean = self.means.get(col, 0.0)
            std = self.stds.get(col, 1.0)
            std_safe = std if abs(std) > 1e-7 else 1.0

            # Z-score normalization
            vector[idx] = (val - mean) / std_safe

        return vector

    def transform_batch(self, batch_data: List[Dict[str, Any]]) -> np.ndarray:
        """Vectorize a list of tabular record dictionaries into a 2D matrix."""
        if not batch_data:
            return np.zeros((0, len(self.feature_names)), dtype=np.float32)

        vectors = [self.transform(row) for row in batch_data]
        return np.vstack(vectors)
