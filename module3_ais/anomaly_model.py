"""
Module 3: AIS & Intelligence - Behavioral Anomaly Detection (Isolation Forest)
Detects unusual maritime navigation behaviors (sudden decelerations, loitering, course deviations)
using scikit-learn's IsolationForest. Measures behavioral unusualness, NOT guilt.
"""

from typing import Dict, Any, List, Optional, Tuple, Union
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

from .config import AISConfig, DEFAULT_CONFIG


# Explicit list of kinematic and behavioral features
# Proximity, time delta, MMSI, and guilt scores are STRICTLY EXCLUDED.
BEHAVIORAL_FEATURE_COLUMNS = [
    "avg_speed_knots",
    "max_speed_knots",
    "speed_std",
    "stop_count",
    "avg_heading_change_deg",
    "max_heading_change_deg",
    "total_track_distance_km",
    "ais_observation_count",
    "speed_change_avg_knots",
    "speed_change_max_knots",
]


class AISAnomalyDetector:
    """
    Unsupervised behavioral anomaly detector for marine AIS trajectories.

    Conversion from raw Isolation Forest to Normalized Score:
    ----------------------------------------------------------
    In scikit-learn, IsolationForest.decision_function(X) outputs:
      - Positive values (> 0) for normal inliers
      - Negative values (< 0) for abnormal outliers / anomalies
      - Exactly 0 at the model's contamination decision boundary

    To convert this raw score into an intuitive, normalized score S in [0.0, 1.0]
    where higher values indicate MORE anomalous behaviour:
      S_anom = 1.0 / (1.0 + exp(sigmoid_k * decision_function(X)))

    With sigmoid_k = 6.0:
      - Extreme inlier (df = +0.4) -> S_anom ~ 0.08 (highly typical)
      - Decision boundary (df = 0.0) -> S_anom = 0.50 (threshold)
      - Definite anomaly (df = -0.2) -> S_anom ~ 0.77 (unusual)
      - Extreme anomaly (df = -0.5) -> S_anom ~ 0.95 (highly unusual)

    This logistic mapping ensures:
      1. Strict bounds in (0.0, 1.0)
      2. Monotonicity: lower decision_function -> higher anomaly score
      3. Robustness against single-sample outlier skew
    """

    def __init__(
        self,
        contamination: float = DEFAULT_CONFIG.anomaly_contamination,
        random_state: int = DEFAULT_CONFIG.anomaly_random_state,
        sigmoid_k: float = 6.0,
        feature_columns: Optional[List[str]] = None
    ):
        self.contamination = contamination
        self.random_state = random_state
        self.sigmoid_k = sigmoid_k
        self.feature_columns = feature_columns or BEHAVIORAL_FEATURE_COLUMNS
        self.model: Optional[IsolationForest] = None
        self._feature_means: Optional[pd.Series] = None

    def _prepare_matrix(self, df_features: pd.DataFrame) -> Tuple[np.ndarray, List[str]]:
        """
        Extracts, validates, and imputes missing values in the behavioral feature matrix.
        Missing values are safely filled with column medians or 0.0.
        """
        available_cols = [col for col in self.feature_columns if col in df_features.columns]
        if not available_cols:
            raise ValueError(
                f"None of the required behavioral features {self.feature_columns} found in DataFrame."
            )

        X = df_features[available_cols].copy()

        # Numeric coercion and median/zero imputation
        for col in available_cols:
            X[col] = pd.to_numeric(X[col], errors="coerce")
            median_val = X[col].median()
            fill_val = median_val if pd.notna(median_val) else 0.0
            X[col] = X[col].fillna(fill_val)

        return X.to_numpy(dtype=np.float64), available_cols

    def fit(self, df_features: pd.DataFrame) -> "AISAnomalyDetector":
        """
        Fits the IsolationForest model on a population of vessel features.
        Gracefully handles small vessel populations (N < 2).
        """
        if df_features.empty or len(df_features) < 2:
            # Cannot fit an outlier model on fewer than 2 samples
            self.model = None
            return self

        X, _ = self._prepare_matrix(df_features)
        n_samples = len(X)

        # Scikit-learn requires contamination <= 0.5
        effective_contamination = min(self.contamination, 0.5)

        self.model = IsolationForest(
            n_estimators=100,
            contamination=effective_contamination,
            random_state=self.random_state,
            max_samples=min(n_samples, 256),
            n_jobs=-1
        )
        self.model.fit(X)
        return self

    def score(self, df_features: pd.DataFrame) -> Tuple[np.ndarray, np.ndarray]:
        """
        Computes normalized behavioral anomaly scores and binary anomaly flags.

        Args:
            df_features: DataFrame containing vessel-level features.

        Returns:
            Tuple[anomaly_scores, is_anomaly_flags]
              - anomaly_scores: np.ndarray of floats in [0.0, 1.0] (higher = more anomalous)
              - is_anomaly_flags: np.ndarray of booleans (True if flagged by model)
        """
        n_samples = len(df_features)
        if n_samples == 0:
            return np.array([]), np.array([], dtype=bool)

        # Handle very small vessel population gracefully (< 2 samples)
        if self.model is None or n_samples < 2:
            # For 1 sample or un-fitted detector, check simple heuristic indicator:
            # (e.g. sharp speed changes or stopping)
            heuristic_scores = []
            heuristic_flags = []
            for _, row in df_features.iterrows():
                stop_count = row.get("stop_count", 0)
                max_turn = row.get("max_heading_change_deg", 0.0)
                speed_drop = row.get("speed_change_max_knots", 0.0)

                # Mild baseline score: 0.5 neutral, adjusted by obvious kinematic anomalies
                score = 0.50
                is_flag = False
                if speed_drop > 8.0 or max_turn > 60.0 or stop_count > 0:
                    score = min(0.85, score + 0.30)
                    is_flag = True
                heuristic_scores.append(round(score, 4))
                heuristic_flags.append(is_flag)

            return np.array(heuristic_scores), np.array(heuristic_flags, dtype=bool)

        X, _ = self._prepare_matrix(df_features)

        # Raw scikit-learn decision function (lower = more abnormal)
        raw_df = self.model.decision_function(X)
        raw_preds = self.model.predict(X)  # -1 for anomaly, 1 for inlier

        # Normalized score via logistic transformation: S = 1 / (1 + exp(k * df))
        scores = 1.0 / (1.0 + np.exp(self.sigmoid_k * raw_df))
        scores = np.clip(np.round(scores, 4), 0.0, 1.0)

        # Binary flag: flagged as outlier by Isolation Forest (-1) or score >= 0.65
        is_anomaly = (raw_preds == -1) | (scores >= 0.65)

        return scores, is_anomaly

    def score_features_df(self, df_features: pd.DataFrame) -> pd.DataFrame:
        """
        Convenience wrapper that fits/scores the input DataFrame and appends
        'behavioral_anomaly_score' and 'is_behavioral_anomaly' columns.
        """
        if df_features.empty:
            res = df_features.copy()
            res["behavioral_anomaly_score"] = pd.Series(dtype=float)
            res["is_behavioral_anomaly"] = pd.Series(dtype=bool)
            return res

        # Fit model on current traffic
        self.fit(df_features)
        scores, flags = self.score(df_features)

        res = df_features.copy()
        res["behavioral_anomaly_score"] = scores
        res["is_behavioral_anomaly"] = flags
        return res
