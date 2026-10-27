"""Comprehensive unit tests for ML preprocessors and domain inference models."""

import base64
import io
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from app.ml.models.base import BaseModel
from app.ml.models.nlp_model import NLPClassifier
from app.ml.models.tabular_model import FraudDetector
from app.ml.models.vision_model import VisionClassifier
from app.ml.preprocessors import (
    ImageTensorPipeline,
    TabularScaler,
    TextTokenizer,
)
from data.seed import seed_database


def _generate_test_image_b64(color: tuple = (255, 0, 0), size: tuple = (16, 16)) -> str:
    """Helper to generate a base64 encoded PNG image."""
    img = Image.new("RGB", size, color=color)
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("utf-8")


class TestTextTokenizer:
    """Tests for TextTokenizer preprocessor."""

    def test_tokenize_basic(self) -> None:
        tokenizer = TextTokenizer()
        tokens = tokenizer.tokenize("Hello, World! This is a TEST.")
        assert tokens == ["hello", "world", "this", "is", "a", "test"]

    def test_tokenize_empty_and_invalid(self) -> None:
        tokenizer = TextTokenizer()
        assert tokenizer.tokenize("") == []
        assert tokenizer.tokenize(None) == []  # type: ignore

    def test_build_vocab(self) -> None:
        tokenizer = TextTokenizer()
        texts = [
            "quick brown fox",
            "quick brown dog",
            "fast brown fox",
        ]
        vocab = tokenizer.build_vocab(texts, max_vocab=3)
        assert len(vocab) == 3
        assert "brown" in vocab  # appears 3 times
        assert vocab["brown"] == 0

    def test_transform_single(self) -> None:
        vocab = {"good": 0, "great": 1, "service": 2}
        tokenizer = TextTokenizer(vocabulary=vocab)
        vec = tokenizer.transform("Good service, really good!")
        assert len(vec) == 3
        # "good" appears twice, "service" appears once -> total 3 tokens counted
        assert vec[0] == pytest.approx(2.0 / 3.0)
        assert vec[2] == pytest.approx(1.0 / 3.0)
        assert vec[1] == 0.0

    def test_transform_empty_vocab_and_empty_text(self) -> None:
        tokenizer = TextTokenizer(vocabulary={})
        vec = tokenizer.transform("some random text")
        assert len(vec) == 1
        assert vec[0] == 0.0

        vocab = {"hello": 0}
        tokenizer2 = TextTokenizer(vocabulary=vocab)
        vec2 = tokenizer2.transform("")
        assert np.all(vec2 == 0.0)

    def test_transform_batch(self) -> None:
        vocab = {"cat": 0, "dog": 1}
        tokenizer = TextTokenizer(vocabulary=vocab)
        batch = ["cat", "dog", "cat dog"]
        mat = tokenizer.transform_batch(batch)
        assert mat.shape == (3, 2)
        assert mat[0, 0] == 1.0 and mat[0, 1] == 0.0
        assert mat[1, 0] == 0.0 and mat[1, 1] == 1.0

        empty_mat = tokenizer.transform_batch([])
        assert empty_mat.shape == (0, 2)


class TestImageTensorPipeline:
    """Tests for ImageTensorPipeline preprocessor."""

    def test_decode_image_types(self) -> None:
        pipeline = ImageTensorPipeline(target_size=(8, 8))

        # 1. Raw PIL Image
        pil_img = Image.new("RGB", (10, 10), color="blue")
        decoded_pil = pipeline.decode_image(pil_img)
        assert decoded_pil.size == (10, 10)

        # 2. Bytes
        buffer = io.BytesIO()
        pil_img.save(buffer, format="PNG")
        decoded_bytes = pipeline.decode_image(buffer.getvalue())
        assert decoded_bytes.size == (10, 10)

        # 3. Base64 string with prefix
        b64_str = _generate_test_image_b64()
        data_uri = f"data:image/png;base64,{b64_str}"
        decoded_uri = pipeline.decode_image(data_uri)
        assert decoded_uri.size == (16, 16)

        # 4. Corrupted / invalid input fallback
        decoded_invalid = pipeline.decode_image("not_a_valid_base64_string!!!")
        assert decoded_invalid.size == (8, 8)

        # 5. Non-string non-byte fallback
        decoded_fallback = pipeline.decode_image(12345)  # type: ignore
        assert decoded_fallback.size == (8, 8)

    def test_transform_flatten_and_channel_first(self) -> None:
        b64_img = _generate_test_image_b64(size=(8, 8))

        pipeline_flat = ImageTensorPipeline(target_size=(8, 8), flatten=True)
        tensor_flat = pipeline_flat.transform(b64_img)
        assert tensor_flat.shape == (8 * 8 * 3,)

        pipeline_channels = ImageTensorPipeline(target_size=(8, 8), flatten=False)
        tensor_channels = pipeline_channels.transform(b64_img)
        assert tensor_channels.shape == (3, 8, 8)

    def test_transform_batch(self) -> None:
        pipeline = ImageTensorPipeline(target_size=(8, 8), flatten=True)
        b64_1 = _generate_test_image_b64(color=(255, 0, 0), size=(16, 16))
        b64_2 = _generate_test_image_b64(color=(0, 255, 0), size=(16, 16))

        batch = pipeline.transform_batch([b64_1, b64_2])
        assert batch.shape == (2, 8 * 8 * 3)

        empty_batch = pipeline.transform_batch([])
        assert empty_batch.shape == (0, 8 * 8 * 3)


class TestTabularScaler:
    """Tests for TabularScaler preprocessor."""

    def test_transform_standard(self) -> None:
        features = ["age", "income", "credit_score"]
        means = {"age": 40.0, "income": 50000.0, "credit_score": 700.0}
        stds = {"age": 10.0, "income": 10000.0, "credit_score": 50.0}

        scaler = TabularScaler(features, means=means, stds=stds)
        data = {"age": 50.0, "income": 60000.0, "credit_score": 750.0}
        vec = scaler.transform(data)

        # (50-40)/10 = 1.0, (60000-50000)/10000 = 1.0, (750-700)/50 = 1.0
        assert np.allclose(vec, [1.0, 1.0, 1.0])

    def test_imputation_and_zero_std(self) -> None:
        features = ["x", "y"]
        means = {"x": 5.0, "y": 10.0}
        stds = {"x": 0.0, "y": 2.0}  # x has std 0 -> should avoid ZeroDivision
        defaults = {"x": 5.0, "y": 10.0}

        scaler = TabularScaler(features, means=means, stds=stds, defaults=defaults)
        # Missing values and invalid strings
        data = {"x": "invalid", "y": None}
        vec = scaler.transform(data)
        assert np.allclose(vec, [0.0, 0.0])

    def test_transform_batch(self) -> None:
        features = ["col1", "col2"]
        scaler = TabularScaler(features)
        batch = [
            {"col1": 1.0, "col2": 2.0},
            {"col1": 3.0, "col2": 4.0},
        ]
        mat = scaler.transform_batch(batch)
        assert mat.shape == (2, 2)
        assert mat[0, 0] == 1.0 and mat[1, 1] == 4.0

        empty_mat = scaler.transform_batch([])
        assert empty_mat.shape == (0, 2)


class TestBaseModelUtilities:
    """Tests for BaseModel numeric activations and static methods."""

    def test_softmax_stability(self) -> None:
        # Large logits that would overflow naive exp
        logits = np.array([1000.0, 1001.0, 1002.0])
        probs = BaseModel.softmax(logits)
        assert np.isclose(np.sum(probs), 1.0)
        assert probs[2] > probs[1] > probs[0]

        # 2D batch
        batch_logits = np.array([[1000.0, 1000.0], [500.0, 502.0]])
        batch_probs = BaseModel.softmax(batch_logits)
        assert batch_probs.shape == (2, 2)
        assert np.isclose(batch_probs[0, 0], 0.5)
        assert np.isclose(np.sum(batch_probs[1]), 1.0)

    def test_sigmoid_stability(self) -> None:
        assert BaseModel.sigmoid(0.0) == pytest.approx(0.5)
        assert BaseModel.sigmoid(1000.0) == pytest.approx(1.0)
        assert BaseModel.sigmoid(-1000.0) == pytest.approx(0.0)

    def test_load_from_file_not_found(self) -> None:
        with pytest.raises(FileNotFoundError):
            NLPClassifier.load_from_file("/path/that/does/not/exist.json")


class TestNLPClassifier:
    """Tests for NLPClassifier domain inference model."""

    def test_sentiment_classification(self) -> None:
        weights = {
            "model_id": "nlp-sentiment",
            "version": "v1",
            "classes": ["negative", "neutral", "positive"],
            "vocabulary": {
                "great": 2.0,
                "excellent": 2.5,
                "love": 2.0,
                "terrible": -2.5,
                "awful": -2.0,
                "bad": -1.5,
            },
            "bias": [0.1, 0.5, 0.1],
        }
        model = NLPClassifier.from_weights(weights)

        # Positive case
        pos_res = model.predict({"text": "Great service, I love it!"})
        assert pos_res["sentiment"] == "positive"
        assert pos_res["confidence"] > 0.5
        assert "positive" in pos_res["probabilities"]

        # Negative case
        neg_res = model.predict("Terrible experience, very bad and awful")
        assert neg_res["sentiment"] == "negative"
        assert neg_res["confidence"] > 0.5

        # Neutral case
        neu_res = model.predict("Today is Wednesday.")
        assert neu_res["sentiment"] == "neutral"

    def test_predict_batch_and_schema(self) -> None:
        model = NLPClassifier()
        batch_res = model.predict_batch(["Great!", "Awful!"])
        assert len(batch_res) == 2
        assert batch_res[0]["sentiment"] in ["positive", "neutral", "negative"]

        empty_res = model.predict_batch([])
        assert empty_res == []

        # Generic multi-class branch test (classes != 3)
        binary_model = NLPClassifier(
            classes=["ham", "spam"],
            vocabulary={"spam": 2.0},
            bias=[0.1, 0.2],
        )
        res_binary = binary_model.predict({"text": "spam spam"})
        assert res_binary["sentiment"] in ["ham", "spam"]

        schema = model.get_schema()
        assert schema["domain"] == "nlp"
        assert "input_schema" in schema
        assert "output_schema" in schema


class TestVisionClassifier:
    """Tests for VisionClassifier domain inference model."""

    def test_vision_classification(self) -> None:
        weights = {
            "model_id": "vision-classifier",
            "version": "v1",
            "classes": ["landscape", "document", "portrait", "product"],
            "target_size": [16, 16],
            "projection_weights": [[0.5, -0.2, 0.1, 0.4]],
            "bias": [0.2, 0.1, 0.1, 0.3],
        }
        model = VisionClassifier.from_weights(weights)

        b64_img = _generate_test_image_b64(size=(16, 16))
        res = model.predict({"image_base64": b64_img})

        assert res["top_class"] in weights["classes"]
        assert 0.0 <= res["confidence"] <= 1.0
        assert len(res["class_scores"]) == 4

    def test_vision_predict_batch_and_projection_shapes(self) -> None:
        # Full matrix projection test
        feat_dim = 8 * 8 * 3
        proj_matrix = np.ones((feat_dim, 2), dtype=np.float64) * 0.01
        weights = {
            "classes": ["class_a", "class_b"],
            "target_size": [8, 8],
            "projection_weights": proj_matrix.tolist(),
        }
        model = VisionClassifier.from_weights(weights)

        b64_img = _generate_test_image_b64(size=(8, 8))
        batch_res = model.predict_batch([b64_img, {"image_base64": b64_img}])
        assert len(batch_res) == 2
        assert batch_res[0]["top_class"] in ["class_a", "class_b"]

        # Test arbitrary shape projection weights (chunk pooling)
        arb_weights = {
            "classes": ["c1", "c2"],
            "target_size": [8, 8],
            "projection_weights": [[0.1, 0.2], [0.3, 0.4]],
        }
        model_arb = VisionClassifier.from_weights(arb_weights)
        res_arb = model_arb.predict({"image_base64": b64_img})
        assert res_arb["top_class"] in ["c1", "c2"]

        # Test None projection weights fallback
        model_none = VisionClassifier(classes=["c1", "c2"], projection_weights=None)
        res_none = model_none.predict({"image_base64": b64_img})
        assert res_none["top_class"] in ["c1", "c2"]

        assert model.predict_batch([]) == []
        schema = model.get_schema()
        assert schema["domain"] == "vision"


class TestFraudDetector:
    """Tests for FraudDetector tabular risk inference model."""

    def test_fraud_risk_tiers(self) -> None:
        weights = {
            "model_id": "fraud-detector",
            "version": "v1",
            "features": [
                "transaction_amount",
                "user_age",
                "velocity_1h",
                "is_foreign",
            ],
            "coefficients": [0.005, -0.02, 0.35, 1.2],
            "intercept": -1.8,
            "threshold": 0.5,
        }
        model = FraudDetector.from_weights(weights)

        # High risk: large foreign transaction with high velocity
        high_risk_input = {
            "transaction_amount": 2500.0,
            "user_age": 22,
            "velocity_1h": 8,
            "is_foreign": 1,
        }
        high_res = model.predict(high_risk_input)
        assert high_res["is_flagged"] is True
        assert high_res["risk_level"] == "HIGH"
        assert high_res["risk_score"] > 0.75

        # Low risk: small domestic transaction with zero velocity
        low_risk_input = {
            "transaction_amount": 15.0,
            "user_age": 45,
            "velocity_1h": 0,
            "is_foreign": 0,
        }
        low_res = model.predict(low_risk_input)
        assert low_res["is_flagged"] is False
        assert low_res["risk_level"] == "LOW"
        assert low_res["risk_score"] < 0.40

        # Invalid string value fallback
        inv_input = {
            "transaction_amount": "not_a_number",
            "user_age": None,
        }
        inv_res = model.predict(inv_input)
        assert "risk_score" in inv_res

    def test_batch_and_scaler_integration(self) -> None:
        weights = {
            "features": ["f1", "f2"],
            "coefficients": [1.0, -1.0],
            "intercept": 0.0,
            "threshold": 0.5,
            "means": {"f1": 10.0, "f2": 20.0},
            "stds": {"f1": 2.0, "f2": 5.0},
        }
        model = FraudDetector.from_weights(weights)
        batch_inputs = [
            # f1 norm: +2.0, f2 norm: -1.0 -> logit: 3.0 -> high
            {"f1": 14.0, "f2": 15.0},
            # f1 norm: -2.0, f2 norm: +1.0 -> logit: -3.0 -> low
            {"f1": 6.0, "f2": 25.0},
        ]
        batch_res = model.predict_batch(batch_inputs)
        assert len(batch_res) == 2
        assert batch_res[0]["risk_score"] > 0.8
        assert batch_res[1]["risk_score"] < 0.2

        assert model.predict_batch([]) == []
        schema = model.get_schema()
        assert schema["domain"] == "tabular"


class TestSeededArtifactsLoading:
    """Verifies that actual seeded artifacts from disk load and run correctly."""

    def test_load_seeded_weights(self, tmp_path: Path) -> None:
        db_file = tmp_path / "test_models_vault.db"
        vault_dir = tmp_path / "models_vault"

        seed_database(db_path=db_file, vault_dir=vault_dir)

        # NLP model
        nlp_path = vault_dir / "nlp-sentiment" / "v1" / "weights.json"
        assert nlp_path.exists()
        nlp_model = NLPClassifier.load_from_file(nlp_path)
        nlp_res = nlp_model.predict({"text": "Excellent service and great speed!"})
        assert nlp_res["sentiment"] == "positive"

        # Vision model
        vision_path = vault_dir / "vision-classifier" / "v1" / "weights.json"
        assert vision_path.exists()
        vision_model = VisionClassifier.load_from_file(vision_path)
        b64_img = _generate_test_image_b64()
        vis_res = vision_model.predict({"image_base64": b64_img})
        assert "top_class" in vis_res

        # Tabular model
        tab_path = vault_dir / "fraud-detector" / "v1" / "weights.json"
        assert tab_path.exists()
        tab_model = FraudDetector.load_from_file(tab_path)
        tab_res = tab_model.predict(
            {
                "transaction_amount": 500.0,
                "user_age": 30,
                "velocity_1h": 2,
                "is_foreign": 0,
            }
        )
        assert "risk_score" in tab_res
