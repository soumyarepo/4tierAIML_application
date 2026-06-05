"""Synthetic transaction data generator for training the fraud detection model."""

import numpy as np
import pandas as pd


def generate_fraud_transactions(n: int = 10000) -> pd.DataFrame:
    """Generate a synthetic dataset of banking transactions with fraud labels.

    The dataset contains features that make fraud patterns detectable:
    - High-value international transfers
    - Burst of recent transactions (speed fraud)

    Args:
        n: Number of transactions to generate.

    Returns:
        DataFrame with columns:
            amount, transaction_type, merchant_risk_score, hour_of_day,
            day_of_week, is_international, user_age_days, num_recent_transactions,
            avg_transaction_amount_7d, is_fraud
    """
    rng = np.random.default_rng(seed=42)

    # Base features using realistic distributions
    amount = _generate_amounts(n, rng)
    transaction_type = rng.integers(0, 4, size=n)  # 0=transfer, 1=deposit, 2=withdrawal, 3=payment
    merchant_risk_score = rng.integers(0, 101, size=n)
    hour_of_day = rng.integers(0, 24, size=n)
    day_of_week = rng.integers(0, 7, size=n)
    is_international = rng.integers(0, 2, size=n)
    user_age_days = rng.integers(1, 3650, size=n)  # up to 10 years
    num_recent_transactions = _generate_recent_tx_count(n, rng)
    avg_transaction_amount_7d = _generate_avg_7d(amount, rng)

    # Generate fraud labels based on detectable patterns
    is_fraud = _generate_fraud_labels(
        amount=amount,
        is_international=is_international,
        num_recent_transactions=num_recent_transactions,
        rng=rng,
    )

    df = pd.DataFrame(
        {
            "amount": amount,
            "transaction_type": transaction_type,
            "merchant_risk_score": merchant_risk_score,
            "hour_of_day": hour_of_day,
            "day_of_week": day_of_week,
            "is_international": is_international,
            "user_age_days": user_age_days,
            "num_recent_transactions": num_recent_transactions,
            "avg_transaction_amount_7d": avg_transaction_amount_7d,
            "is_fraud": is_fraud,
        },
        index=pd.RangeIndex(start=0, stop=n, step=1),
    )
    return df


def _generate_amounts(n: int, rng: np.random.Generator) -> np.ndarray:
    """Generate transaction amounts using a log-normal distribution for realism."""
    # Most transactions are small; few are very large
    log_amount = rng.normal(loc=4.0, scale=1.5, size=n)  # median ~54
    amounts = np.exp(log_amount)
    # Clip to reasonable banking range
    amounts = np.clip(amounts, 0.01, 1_000_000.0)
    return amounts


def _generate_recent_tx_count(n: int, rng: np.random.Generator) -> np.ndarray:
    """Generate number of transactions in the last hour."""
    # Heavy tail – most users have 0-3, some burst
    raw = rng.exponential(scale=2.0, size=n)
    return np.clip(np.round(raw).astype(int), 0, 50)


def _generate_avg_7d(base_amounts: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """Generate 7-day average based on the transaction amount with noise."""
    noise = rng.normal(1.0, 0.2, size=len(base_amounts))
    return np.clip(base_amounts * noise, 0.01, None)


def _generate_fraud_labels(
    amount: np.ndarray,
    is_international: np.ndarray,
    num_recent_transactions: np.ndarray,
    rng: np.random.Generator,
) -> np.ndarray:
    """Apply fraud rules to generate labels.

    Fraud rules (observable patterns):
    1. High-value international transfers (amount > 10_000 AND is_international == 1)
    2. Burst transactions (num_recent_transactions > 10)
    """
    fraud = np.zeros(len(amount), dtype=np.int64)

    # Rule 1: high-value international
    rule1 = (amount > 10_000) & (is_international == 1)
    fraud[rule1] = 1

    # Rule 2: burst
    rule2 = num_recent_transactions > 10
    fraud[rule2] = 1

    # Add a small amount of random noise fraud (~0.5%) so model isn't purely rule-based
    random_fraud = rng.uniform(size=len(amount)) < 0.005
    fraud[random_fraud] = 1

    return fraud