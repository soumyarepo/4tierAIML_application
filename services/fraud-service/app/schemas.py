"""Pydantic v2 request/response schemas for the Fraud Detection API."""

from datetime import datetime
from enum import Enum
from typing import Annotated

from pydantic import BaseModel, Field, field_validator


class TransactionType(str, Enum):
    """Enumeration of supported transaction types."""

    TRANSFER = "transfer"
    DEPOSIT = "deposit"
    WITHDRAWAL = "withdrawal"
    PAYMENT = "payment"

    @classmethod
    def from_str(cls, value: str) -> int:
        mapping = {"transfer": 0, "deposit": 1, "withdrawal": 2, "payment": 3}
        return mapping.get(value.lower(), 0)


class FraudAnalyzeRequest(BaseModel):
    """Request payload for single-transaction fraud analysis."""

    amount: Annotated[float, Field(gt=0, description="Transaction amount in dollars")]
    transaction_type: TransactionType = Field(
        description="Type of transaction (transfer, deposit, withdrawal, payment)"
    )
    merchant_risk_score: Annotated[
        int, Field(ge=0, le=100, description="Merchant risk score 0–100")
    ]
    hour_of_day: Annotated[int, Field(ge=0, le=23, description="Hour of the day (0–23)")]
    day_of_week: Annotated[int, Field(ge=0, le=6, description="Day of week (0=Mon, 6=Sun)")]
    is_international: bool = Field(description="Whether the transaction is international")
    user_age_days: Annotated[
        int, Field(ge=0, description="Number of days since the user registered")
    ]
    num_recent_transactions: Annotated[
        int, Field(ge=0, description="Transactions the user made in the last hour")
    ]
    avg_transaction_amount_7d: Annotated[
        float, Field(ge=0, description="User's average transaction amount over the last 7 days")
    ]

    def to_features(self) -> dict:
        """Convert request to the feature dict expected by the model service."""
        return {
            "amount": self.amount,
            "transaction_type": TransactionType.from_str(self.transaction_type.value),
            "merchant_risk_score": self.merchant_risk_score,
            "hour_of_day": self.hour_of_day,
            "day_of_week": self.day_of_week,
            "is_international": int(self.is_international),
            "user_age_days": self.user_age_days,
            "num_recent_transactions": self.num_recent_transactions,
            "avg_transaction_amount_7d": self.avg_transaction_amount_7d,
        }


class FraudAnalyzeResponse(BaseModel):
    """Response payload for single-transaction fraud analysis."""

    is_fraudulent: bool = Field(description="True if the transaction is flagged as fraudulent")
    risk_score: Annotated[float, Field(ge=0, le=100, description="Risk score from 0 to 100")]
    confidence: Annotated[float, Field(ge=0, le=1, description="Model confidence in the prediction")]
    model_version: str = Field(description="Version identifier of the model that produced this result")


class FraudBatchRequest(BaseModel):
    """Request payload for batch fraud analysis (max 1000 transactions per request)."""

    transactions: Annotated[
        list[FraudAnalyzeRequest],
        Field(max_length=1000, description="List of transactions to analyze"),
    ]


class FraudBatchResponse(BaseModel):
    """Response payload for batch fraud analysis."""

    results: list[FraudAnalyzeResponse]
    total: int = Field(description="Total number of transactions analyzed")
    flagged_count: int = Field(description="Number of transactions flagged as fraudulent")


class ModelInfoResponse(BaseModel):
    """Response payload for the model info endpoint."""

    model_version: str = Field(description="Semantic version of the active model")
    training_date: datetime = Field(description="UTC timestamp when the model was trained")
    dataset_size: int = Field(description="Number of samples used for training")
    algorithm: str = Field(default="sklearn.ensemble.IsolationForest")