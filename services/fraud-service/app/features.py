"""Feature extraction for the fraud detection model."""

import numpy as np


def extract_features(transaction: dict) -> np.ndarray:
    """Convert a raw transaction dict into the feature array expected by the model.

    Feature vector order (matching training data columns):
        [amount, transaction_type, merchant_risk_score, hour_of_day,
         day_of_week, is_international, user_age_days, num_recent_transactions,
         avg_transaction_amount_7d]

    Args:
        transaction: Dictionary with keys matching FraudAnalyzeRequest fields.

    Returns:
        1-D NumPy array of float features, shape (9,).

    Raises:
        KeyError: If a required field is missing from the transaction dict.
    """
    features = np.array(
        [
            float(transaction["amount"]),
            float(transaction["transaction_type"]),
            float(transaction["merchant_risk_score"]),
            float(transaction["hour_of_day"]),
            float(transaction["day_of_week"]),
            float(transaction["is_international"]),
            float(transaction["user_age_days"]),
            float(transaction["num_recent_transactions"]),
            float(transaction["avg_transaction_amount_7d"]),
        ],
        dtype=np.float64,
    )
    return features