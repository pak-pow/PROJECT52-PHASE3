"""Model Registry service managing version lifecycles and zero-downtime hot-swapping."""

import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from app.ml.models.base import BaseModel
from app.ml.models.nlp_model import NLPClassifier
from app.ml.models.tabular_model import FraudDetector
from app.ml.models.vision_model import VisionClassifier
from app.models.model_entity import ModelDAO
from app.models.model_version import ModelVersionDAO
from app.models.prediction_log import PredictionLogDAO
from app.services.batcher_service import DynamicBatcher
from app.services.cache_service import InferenceCache
from app.services.telemetry_service import TelemetryEngine


class ModelLifecycleState:
    """Enumeration of model runtime lifecycle states."""

    UNREGISTERED = "unregistered"
    LOADING = "loading"
    WARMING_UP = "warming_up"
    ACTIVE = "active"
    HOT_RELOADING = "hot_reloading"
    UNLOADED = "unloaded"


class RegisteredModel:
    """Container holding runtime state, model instance, batcher, and metadata."""

    def __init__(
        self,
        model_id: str,
        name: str,
        domain: str,
        active_version: str,
        instance: BaseModel,
        batcher: DynamicBatcher,
        description: Optional[str] = None,
        input_schema: Optional[Dict[str, Any]] = None,
        output_schema: Optional[Dict[str, Any]] = None,
        metrics: Optional[Dict[str, Any]] = None,
        state: str = ModelLifecycleState.ACTIVE,
    ) -> None:
        """Initialize registered model container with runtime execution pointers."""
        self.model_id = model_id
        self.name = name
        self.domain = domain
        self.active_version = active_version
        self.instance = instance
        self.batcher = batcher
        self.description = description
        self.input_schema = input_schema or {}
        self.output_schema = output_schema or {}
        self.metrics = metrics or {}
        self.state = state
        self.lock = threading.RLock()


class ModelRegistry:
    """Manages active models, lifecycle states, and zero-downtime swapping."""

    def __init__(
        self,
        cache: Optional[InferenceCache] = None,
        telemetry: Optional[TelemetryEngine] = None,
        max_batch_size: int = 32,
        batch_timeout_ms: float = 10.0,
    ) -> None:
        """Initialize model registry with cache, telemetry, and batching parameters."""
        self.cache = cache or InferenceCache()
        self.telemetry = telemetry or TelemetryEngine()
        self.max_batch_size = max_batch_size
        self.batch_timeout_ms = batch_timeout_ms

        self._models: Dict[str, RegisteredModel] = {}
        self._lock = threading.RLock()

    @staticmethod
    def _instantiate_model(domain: str, artifact_path: Union[str, Path]) -> BaseModel:
        """Factory creating domain model instance directly from disk artifact."""
        clean_domain = domain.strip().lower()
        if clean_domain == "nlp":
            return NLPClassifier.load_from_file(artifact_path)
        elif clean_domain == "vision":
            return VisionClassifier.load_from_file(artifact_path)
        elif clean_domain == "tabular":
            return FraudDetector.load_from_file(artifact_path)
        raise ValueError(f"Unsupported model domain category: {domain}")

    @staticmethod
    def _warmup_model(domain: str, instance: BaseModel) -> None:
        """Execute a synthetic dry-run inference to prime execution pipelines."""
        clean_domain = domain.strip().lower()
        try:
            if clean_domain == "nlp":
                instance.predict({"text": "warmup dry run"})
            elif clean_domain == "vision":
                instance.predict({"image_base64": ""})
            elif clean_domain == "tabular":
                instance.predict({})
        except Exception as exc:  # nosec B110
            # Warmup is best-effort and must not abort model activation
            _ = str(exc)

    def load_model(
        self,
        model_id: str,
        conn: sqlite3.Connection,
        version: Optional[str] = None,
    ) -> RegisteredModel:
        """Load, warm up, and activate a model version from storage and database."""
        clean_id = model_id.strip().lower()
        model_rec = ModelDAO.get_by_id(conn, clean_id)
        if not model_rec:
            raise ValueError(f"Model '{clean_id}' does not exist in registry database")

        target_version = version or model_rec["active_version"]
        version_rec = ModelVersionDAO.get(conn, clean_id, target_version)
        if not version_rec:
            raise ValueError(
                f"Version '{target_version}' for model '{clean_id}' not found"
            )

        domain = model_rec["domain"]
        artifact_path = version_rec["artifact_path"]

        # Instantiate concrete model and warm up
        instance = self._instantiate_model(domain, artifact_path)
        self._warmup_model(domain, instance)

        # Initialize and start micro-batcher
        batcher = DynamicBatcher(
            predict_fn=instance.predict_batch,
            max_batch_size=self.max_batch_size,
            timeout_ms=self.batch_timeout_ms,
            name=f"{clean_id}-{target_version}",
        )
        batcher.start()

        registered = RegisteredModel(
            model_id=clean_id,
            name=model_rec["name"],
            domain=domain,
            active_version=target_version,
            instance=instance,
            batcher=batcher,
            description=model_rec.get("description"),
            input_schema=version_rec.get("input_schema"),
            output_schema=version_rec.get("output_schema"),
            metrics=version_rec.get("metrics"),
            state=ModelLifecycleState.ACTIVE,
        )

        with self._lock:
            # If an existing model was loaded, stop its batcher
            if clean_id in self._models:
                self._models[clean_id].batcher.stop()
            self._models[clean_id] = registered

        return registered

    def load_all_active_models(self, conn: sqlite3.Connection) -> int:
        """Load and activate all registered production models from database."""
        records = ModelDAO.list_all(conn)
        loaded_count = 0
        for rec in records:
            try:
                self.load_model(rec["id"], conn)
                loaded_count += 1
            except Exception as exc:  # nosec B112
                _ = str(exc)
                continue
        return loaded_count

    def hot_swap_version(
        self,
        model_id: str,
        new_version: str,
        conn: sqlite3.Connection,
    ) -> None:
        """Perform zero-downtime atomic swap from current model to new version."""
        clean_id = model_id.strip().lower()
        clean_ver = new_version.strip().lower()

        with self._lock:
            if clean_id not in self._models:
                raise KeyError(f"Model '{clean_id}' is not loaded in registry")
            current = self._models[clean_id]

        version_rec = ModelVersionDAO.get(conn, clean_id, clean_ver)
        if not version_rec:
            raise ValueError(f"Target version '{clean_ver}' for '{clean_id}' not found")

        # Mark state as hot-reloading (in-flight queries continue on current version)
        with current.lock:
            current.state = ModelLifecycleState.HOT_RELOADING

        try:
            # Instantiate and warm up new version instance in background
            new_instance = self._instantiate_model(
                current.domain, version_rec["artifact_path"]
            )
            self._warmup_model(current.domain, new_instance)

            new_batcher = DynamicBatcher(
                predict_fn=new_instance.predict_batch,
                max_batch_size=self.max_batch_size,
                timeout_ms=self.batch_timeout_ms,
                name=f"{clean_id}-{clean_ver}",
            )
            new_batcher.start()

            # Atomic reference replacement under lock
            old_batcher: Optional[DynamicBatcher] = None
            with current.lock:
                old_batcher = current.batcher
                current.instance = new_instance
                current.batcher = new_batcher
                current.active_version = clean_ver
                current.input_schema = version_rec.get("input_schema") or {}
                current.output_schema = version_rec.get("output_schema") or {}
                current.metrics = version_rec.get("metrics") or {}
                current.state = ModelLifecycleState.ACTIVE

            # Invalidate cached predictions for this model
            self.cache.invalidate_model(clean_id)

            # Persist active version in database
            ModelDAO.update_active_version(conn, clean_id, clean_ver)

            # Gracefully stop old batcher
            if old_batcher:
                old_batcher.stop(timeout=2.0)

        except Exception as exc:
            # Revert state on failure
            with current.lock:
                current.state = ModelLifecycleState.ACTIVE
            raise RuntimeError(
                f"Hot swap failed for '{clean_id}' to version '{clean_ver}': {exc}"
            ) from exc

    def validate_input(
        self,
        model_id: str,
        payload: Any,
    ) -> Tuple[bool, Optional[str]]:
        """Validate inference input payload against model schema specification."""
        clean_id = model_id.strip().lower()
        with self._lock:
            if clean_id not in self._models:
                return False, f"Model '{clean_id}' is not registered"
            model = self._models[clean_id]

        if payload is None:
            return False, "Inference payload cannot be None"

        domain = model.domain
        if domain == "nlp":
            if isinstance(payload, dict):
                if "text" not in payload and "input" not in payload:
                    return False, "NLP payload dictionary must contain 'text' key"
            elif not isinstance(payload, str):
                return False, "NLP payload must be a string or dictionary with 'text'"

        elif domain == "vision":
            if isinstance(payload, dict):
                if not any(k in payload for k in ("image_base64", "image", "data")):
                    return False, "Vision payload must contain 'image_base64' key"

        elif domain == "tabular":
            if not isinstance(payload, dict):
                return False, "Tabular payload must be a key-value dictionary"

        return True, None

    def predict(
        self,
        model_id: str,
        payload: Any,
        use_cache: bool = True,
        use_batcher: bool = True,
        timeout: Optional[float] = None,
        conn: Optional[sqlite3.Connection] = None,
    ) -> Dict[str, Any]:
        """Perform end-to-end model inference with validation, caching, and batching."""
        clean_id = model_id.strip().lower()
        with self._lock:
            if clean_id not in self._models:
                raise KeyError(f"Model '{clean_id}' is not loaded in registry")
            model = self._models[clean_id]

        with model.lock:
            active_version = model.active_version
            state = model.state
            instance = model.instance
            batcher = model.batcher

        if state not in (ModelLifecycleState.ACTIVE, ModelLifecycleState.HOT_RELOADING):
            raise RuntimeError(f"Model '{clean_id}' is in inactive state: {state}")

        # Input schema validation
        is_valid, error_msg = self.validate_input(clean_id, payload)
        if not is_valid:
            self.telemetry.record(
                clean_id, active_version, 0.0, cached=False, status="error"
            )
            if conn:
                PredictionLogDAO.log_prediction(
                    conn,
                    clean_id,
                    active_version,
                    latency_ms=0.0,
                    status="error",
                    error_message=error_msg,
                )
            raise ValueError(error_msg or "Invalid input payload schema")

        # Cache inspection
        cache_key = self.cache.compute_hash(clean_id, active_version, payload)
        if use_cache:
            cached_result = self.cache.get(cache_key)
            if cached_result is not None:
                self.telemetry.record(
                    clean_id, active_version, 0.05, cached=True, status="success"
                )
                if conn:
                    PredictionLogDAO.log_prediction(
                        conn,
                        clean_id,
                        active_version,
                        latency_ms=0.05,
                        cached=True,
                        status="success",
                    )
                return {
                    "model_id": clean_id,
                    "version": active_version,
                    "prediction": cached_result,
                    "latency_ms": 0.05,
                    "cached": True,
                    "status": "success",
                }

        # Cache miss - execute inference
        t0 = time.perf_counter()
        try:
            if use_batcher:
                prediction = batcher.submit(payload, timeout=timeout)
            else:
                prediction = instance.predict(payload)

            latency_ms = (time.perf_counter() - t0) * 1000.0

            if use_cache:
                self.cache.set(cache_key, prediction)

            self.telemetry.record(
                clean_id, active_version, latency_ms, cached=False, status="success"
            )
            if conn:
                PredictionLogDAO.log_prediction(
                    conn,
                    clean_id,
                    active_version,
                    latency_ms=latency_ms,
                    cached=False,
                    status="success",
                )

            return {
                "model_id": clean_id,
                "version": active_version,
                "prediction": prediction,
                "latency_ms": round(latency_ms, 3),
                "cached": False,
                "status": "success",
            }

        except Exception as exc:
            latency_ms = (time.perf_counter() - t0) * 1000.0
            self.telemetry.record(
                clean_id, active_version, latency_ms, cached=False, status="error"
            )
            if conn:
                PredictionLogDAO.log_prediction(
                    conn,
                    clean_id,
                    active_version,
                    latency_ms=latency_ms,
                    cached=False,
                    status="error",
                    error_message=str(exc),
                )
            raise

    def predict_batch(
        self,
        model_id: str,
        batch_payload: List[Any],
        conn: Optional[sqlite3.Connection] = None,
    ) -> List[Dict[str, Any]]:
        """Direct vectorized batch inference executing across payload records."""
        clean_id = model_id.strip().lower()
        with self._lock:
            if clean_id not in self._models:
                raise KeyError(f"Model '{clean_id}' is not loaded in registry")
            model = self._models[clean_id]

        with model.lock:
            instance = model.instance
            version = model.active_version

        t0 = time.perf_counter()
        try:
            results = instance.predict_batch(batch_payload)
            latency_ms = (time.perf_counter() - t0) * 1000.0

            self.telemetry.record(
                clean_id,
                version,
                latency_ms,
                cached=False,
                status="success",
                batch_size=len(batch_payload),
            )
            if conn:
                PredictionLogDAO.log_prediction(
                    conn,
                    clean_id,
                    version,
                    batch_size=len(batch_payload),
                    latency_ms=latency_ms,
                    cached=False,
                    status="success",
                )
            return results

        except Exception as exc:
            latency_ms = (time.perf_counter() - t0) * 1000.0
            self.telemetry.record(
                clean_id,
                version,
                latency_ms,
                cached=False,
                status="error",
                batch_size=len(batch_payload),
            )
            if conn:
                PredictionLogDAO.log_prediction(
                    conn,
                    clean_id,
                    version,
                    batch_size=len(batch_payload),
                    latency_ms=latency_ms,
                    cached=False,
                    status="error",
                    error_message=str(exc),
                )
            raise

    def unload_model(self, model_id: str) -> bool:
        """Stop worker batcher and remove active model instance from memory."""
        clean_id = model_id.strip().lower()
        with self._lock:
            if clean_id not in self._models:
                return False
            model = self._models.pop(clean_id)

        with model.lock:
            model.state = ModelLifecycleState.UNLOADED
            model.batcher.stop()

        self.cache.invalidate_model(clean_id)
        return True

    def get_model_status(self, model_id: str) -> Dict[str, Any]:
        """Return comprehensive lifecycle state, configuration, and runtime metrics."""
        clean_id = model_id.strip().lower()
        with self._lock:
            if clean_id not in self._models:
                raise KeyError(f"Model '{clean_id}' is not loaded in registry")
            model = self._models[clean_id]

        with model.lock:
            batcher_metrics = model.batcher.get_metrics()
            telemetry_metrics = self.telemetry.get_model_metrics(clean_id)

            return {
                "model_id": model.model_id,
                "name": model.name,
                "domain": model.domain,
                "active_version": model.active_version,
                "state": model.state,
                "description": model.description,
                "input_schema": model.input_schema,
                "output_schema": model.output_schema,
                "metrics": model.metrics,
                "batcher": batcher_metrics,
                "telemetry": telemetry_metrics,
            }

    def list_models(self) -> List[Dict[str, Any]]:
        """Return list of summaries for all currently loaded in-memory models."""
        with self._lock:
            model_ids = list(self._models.keys())

        return [self.get_model_status(mid) for mid in model_ids]

    def shutdown(self) -> None:
        """Gracefully unload all active models and stop background worker threads."""
        with self._lock:
            model_ids = list(self._models.keys())
        for mid in model_ids:
            self.unload_model(mid)
