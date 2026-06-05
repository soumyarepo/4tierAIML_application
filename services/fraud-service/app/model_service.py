"""Fraud model lifecycle: training, inference, and persistence."""

import joblib
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

from app.features import extract_features


class FraudModelService:
    """Manages the fraud detection IsolationForest model lifecycle.

    Uses sklearn IsolationForest for unsupervised anomaly detection
    on transaction feature vectors.
    """

    MODEL_VERSION_PREFIX = "v1.0.0"

    def __init__(self) -> None:
        self._model: IsolationForest | None = None
        self._model_version: str = ""
        self._training_date: datetime | None = None
        self._dataset_size: int = 0

    @property
    def model(self) -> IsolationForest:
        """Return the loaded model, raising if not yet loaded."""
        if self._model is None:
            raise RuntimeError("Model not loaded. Call load_model() or train() first.")
        return self._model

    @property
    def model_version(self) -> str:
        """Semantic version string of the active model."""
        return self._model_version

    @property
    def training_date(self) -> datetime | None:
        """UTC timestamp of when the model was trained."""
        return self._training_date

    @property
    def dataset_size(self) -> int:
        """Number of samples the model was trained on."""
        return self._dataset_size

    def train(self, data: pd.DataFrame) -> None:
        """Train an IsolationForest on the provided transaction DataFrame.

        The target column ``is_fraud`` is NOT used during training (unsupervised).
        It is only for evaluation/analysis after the fact.

        Args:
            data: DataFrame with feature columns matching extract_features() order.
        """
        feature_names = [
            "amount",
            "transaction_type",
            "merchant_risk_score",
            "hour_of_day",
            "day_of_week",
            "is_international",
            "user_age_days",
            "num_recent_transactions",
            "avg_transaction_amount_7d",
        ]
        X = data[feature_names].values.astype(np.float64)

        self._model = IsolationForest(
            contamination=0.05,
            random_state=42,
            n_jobs=-1,
        )
        self._model.fit(X)

        self._training_date = datetime.now(timezone.utc)
        self._model_version = f"{self.MODEL_VERSION_PREFIX}-{self._training_date.isoformat()}"
        self._dataset_size = len(data)

    def predict(self, transaction_features: dict) -> dict:
        """Score a single transaction and return the fraud assessment.

        Args:
            transaction_features: Raw transaction dict passed through extract_features.

        Returns:
            Dictionary with keys:
                is_fraudulent (bool),
                risk_score (float 0-100),
                confidence (float 0-1),
                model_version (str)
        """
        features = extract_features(transaction_features)
        features_2d = features.reshape(1, -1)

        # decision_function: lower = more anomalous; score_samples: higher = more normal
        raw_score = self.model.decision_function(features_2d)[0]

        # Normalise to 0-100 (IsolationForest scores are in roughly [-0.5, 0.5])
        risk_score = float(np.clip((0.5 - raw_score) / 1.0 * 100.0, 0.0, 100.0))

        # is_fraudulent when risk_score exceeds threshold
        is_fraudulent = risk_score > 50.0

        # Confidence based on magnitude of anomaly — how far from decision boundary
        confidence = float(np.clip(abs(raw_score) * 2.0, 0.0, 1.0))

        return {
            "is_fraudulent": is_fraudulent,
            "risk_score": round(risk_score, 2),
            "confidence": round(confidence, 2),
            "model_version": self._model_version,
        }

    def save_model(self, path: str | Path) -> None:
        """Persist the model and metadata to disk using joblib.

        Args:
            path: File path where the model archive will be written.
        """
        if self._model is None:
            raise RuntimeError("No model to save – call train() first.")
        payload = {
            "model": self._model,
            "model_version": self._model_version,
            "training_date": self._training_date,
            "dataset_size": self._dataset_size,
        }
        joblib.dump(payload, path)

    def load_model(self, path: str | Path) -> None:
        """Load a previously saved model and metadata from disk.

        Args:
            path: Path to the joblib archive.

        Raises:
            FileNotFoundError: If the file does not exist.
        """
        payload: dict = joblib.load(path)
        self._model = payload["model"]
        self._model_version = payload["model_version"]
        self._training_date = payload["training_date"]
        self._dataset_size = payload["dataset_size"]