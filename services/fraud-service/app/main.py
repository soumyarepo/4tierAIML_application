"""FastAPI application for the Fraud Detection Service (Tier 3)."""

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI, status
from prometheus_client import Counter

from app.schemas import (
    FraudAnalyzeRequest,
    FraudAnalyzeResponse,
    FraudBatchRequest,
    FraudBatchResponse,
    ModelInfoResponse,
)
from app.model_service import FraudModelService
from app import synthetic_data
from shared.logging_config import configure_logging, get_logger
from shared.metrics import setup_metrics

# ---------------------------------------------------------------------------
# Application state
# ---------------------------------------------------------------------------

MODEL_PATH = Path("/data/fraud_model.pkl")
MODEL_DIR = Path("/data")

# Global model service instance — shared across all request handlers
_model_service: FraudModelService | None = None
_logger: "structlog.BoundLogger | None" = None

# Prometheus metric
FRAUD_PREDICTIONS_TOTAL = Counter(
    "fraud_predictions_total",
    "Total fraud analysis requests processed",
    ["mode"],
)


def _get_model_service() -> FraudModelService:
    if _model_service is None:
        raise RuntimeError("Model service not initialised during startup")
    return _model_service


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Initialise the model on startup; graceful shutdown on exit."""
    global _model_service, _logger

    configure_logging(
        debug=False,
        service_name="fraud-service",
    )
    _logger = get_logger("fraud-service")
    _logger.info("fraud_service_starting")

    _model_service = FraudModelService()
    MODEL_DIR.mkdir(parents=True, exist_ok=True)

    if MODEL_PATH.exists():
        _logger.info("loading_existing_model", path=str(MODEL_PATH))
        _model_service.load_model(MODEL_PATH)
    else:
        _logger.info("no_existing_model_training", path=str(MODEL_PATH))
        data = synthetic_data.generate_fraud_transactions(n=10000)
        _model_service.train(data)
        _model_service.save_model(MODEL_PATH)
        _logger.info("model_trained_and_saved", dataset_size=len(data))

    _logger.info(
        "fraud_service_ready",
        model_version=_model_service.model_version,
        training_date=str(_model_service.training_date),
        dataset_size=_model_service.dataset_size,
    )
    yield
    _logger.info("fraud_service_shutting_down")


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Fraud Detection Service",
    description="AI/ML microservice that scores banking transactions for fraud risk.",
    version="1.0.0",
    lifespan=lifespan,
)

setup_metrics(app)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/health", tags=["health"])
async def health_check() -> dict:
    """Liveness probe for Kubernetes."""
    return {"status": "healthy", "service": "fraud-service"}


@app.post(
    "/api/v1/fraud/analyze",
    response_model=FraudAnalyzeResponse,
    tags=["fraud"],
    summary="Analyze a single transaction for fraud risk",
)
async def analyze_transaction(request: FraudAnalyzeRequest) -> FraudAnalyzeResponse:
    """Score a single transaction and return the fraud assessment.

    The ML model evaluates the transaction against patterns learned from
    synthetic data and returns a risk score between 0 (safe) and 100 (high risk).
    """
    FRAUD_PREDICTIONS_TOTAL.labels(mode="single").inc()

    # Run sync inference in a thread pool to avoid blocking the async event loop
    features = request.to_features()
    result: dict = await asyncio.to_thread(_get_model_service().predict, features)

    return FraudAnalyzeResponse(
        is_fraudulent=result["is_fraudulent"],
        risk_score=result["risk_score"],
        confidence=result["confidence"],
        model_version=result["model_version"],
    )


@app.post(
    "/api/v1/fraud/analyze/batch",
    response_model=FraudBatchResponse,
    tags=["fraud"],
    summary="Analyze multiple transactions for fraud risk",
)
async def analyze_batch(request: FraudBatchRequest) -> FraudBatchResponse:
    """Batch fraud analysis endpoint — processes up to 1000 transactions per request."""
    FRAUD_PREDICTIONS_TOTAL.labels(mode="batch").inc()

    service = _get_model_service()
    results: list[FraudAnalyzeResponse] = []
    flagged_count = 0

    for tx_req in request.transactions:
        features = tx_req.to_features()
        raw: dict = await asyncio.to_thread(service.predict, features)
        resp = FraudAnalyzeResponse(
            is_fraudulent=raw["is_fraudulent"],
            risk_score=raw["risk_score"],
            confidence=raw["confidence"],
            model_version=raw["model_version"],
        )
        results.append(resp)
        if resp.is_fraudulent:
            flagged_count += 1

    return FraudBatchResponse(
        results=results,
        total=len(results),
        flagged_count=flagged_count,
    )


@app.post(
    "/api/v1/fraud/model/retrain",
    response_model=ModelInfoResponse,
    tags=["model"],
    summary="Retrain the fraud detection model",
    description="Admin-only endpoint that regenerates synthetic data and retrains the model.",
)
async def retrain_model() -> ModelInfoResponse:
    """Retrain the IsolationForest model with fresh synthetic data."""
    service = _get_model_service()

    # Run training in threadpool — can be slow for large datasets
    data = await asyncio.to_thread(synthetic_data.generate_fraud_transactions, 10000)
    await asyncio.to_thread(service.train, data)
    await asyncio.to_thread(service.save_model, MODEL_PATH)

    _logger.info(
        "model_retrained",
        model_version=service.model_version,
        dataset_size=service.dataset_size,
    )

    return ModelInfoResponse(
        model_version=service.model_version,
        training_date=service.training_date,
        dataset_size=service.dataset_size,
    )


@app.get(
    "/api/v1/fraud/model/info",
    response_model=ModelInfoResponse,
    tags=["model"],
    summary="Get information about the active model",
)
async def model_info() -> ModelInfoResponse:
    """Return metadata about the currently loaded fraud detection model."""
    service = _get_model_service()
    return ModelInfoResponse(
        model_version=service.model_version,
        training_date=service.training_date,
        dataset_size=service.dataset_size,
    )