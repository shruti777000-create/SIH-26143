"""
Module 3 Tests - Isolation Forest Behavioral Anomaly Detection
Tests anomaly scoring, NaN imputation, small populations, determinism, and normalization.
"""

import unittest
import numpy as np
import pandas as pd

from module3_ais.anomaly_model import AISAnomalyDetector, BEHAVIORAL_FEATURE_COLUMNS


class TestAISAnomalyDetector(unittest.TestCase):

    def setUp(self):
        # Create a synthetic population of 10 normal cruising vessels
        np.random.seed(42)
        normal_data = []
        for i in range(10):
            normal_data.append({
                "mmsi": 419000000 + i,
                "avg_speed_knots": 12.0 + np.random.uniform(-1.0, 1.0),
                "max_speed_knots": 14.0 + np.random.uniform(-0.5, 0.5),
                "speed_std": 0.5 + np.random.uniform(0.0, 0.3),
                "stop_count": 0,
                "avg_heading_change_deg": 2.0 + np.random.uniform(0.0, 1.0),
                "max_heading_change_deg": 5.0 + np.random.uniform(0.0, 2.0),
                "total_track_distance_km": 25.0 + np.random.uniform(-2.0, 2.0),
                "ais_observation_count": 12,
                "speed_change_avg_knots": 0.4 + np.random.uniform(0.0, 0.2),
                "speed_change_max_knots": 1.0 + np.random.uniform(0.0, 0.5),
            })
        self.df_normal = pd.DataFrame(normal_data)

    def test_detector_identifies_unusual_speed_and_heading(self):
        """Anomalous vessel with sharp turns and sudden deceleration receives high anomaly score."""
        anomalous_vessel = pd.DataFrame([{
            "mmsi": 419999999,
            "avg_speed_knots": 3.2,
            "max_speed_knots": 16.5,
            "speed_std": 6.8,  # extreme speed volatility
            "stop_count": 4,   # multiple stops
            "avg_heading_change_deg": 42.0,
            "max_heading_change_deg": 135.0,  # sharp zig-zag
            "total_track_distance_km": 10.0,
            "ais_observation_count": 12,
            "speed_change_avg_knots": 4.5,
            "speed_change_max_knots": 13.3,  # drastic speed drop
        }])

        combined = pd.concat([self.df_normal, anomalous_vessel], ignore_index=True)
        detector = AISAnomalyDetector(contamination=0.10, random_state=42)
        detector.fit(combined)

        scores, flags = detector.score(combined)

        # Output bounds: strictly [0.0, 1.0]
        self.assertTrue((scores >= 0.0).all() and (scores <= 1.0).all())

        # Anomalous vessel is at index -1
        anom_score = scores[-1]
        normal_scores = scores[:-1]

        # Anomaly score must be higher for the erratic ship than the normal fleet average
        self.assertGreater(anom_score, np.mean(normal_scores))
        self.assertGreater(anom_score, 0.60)
        self.assertTrue(flags[-1], "Erratic vessel must be flagged as anomalous.")

    def test_missing_and_nan_values_handled_safely(self):
        """Detector does not crash when NaN or null values are present in features."""
        df_nan = self.df_normal.copy()
        df_nan.loc[0, "speed_std"] = np.nan
        df_nan.loc[1, "avg_speed_knots"] = np.nan
        df_nan.loc[2, "max_heading_change_deg"] = None

        detector = AISAnomalyDetector(random_state=42)
        detector.fit(df_nan)
        scores, flags = detector.score(df_nan)

        self.assertEqual(len(scores), len(df_nan))
        self.assertFalse(np.isnan(scores).any(), "Scores must not contain NaNs.")
        self.assertTrue((scores >= 0.0).all() and (scores <= 1.0).all())

    def test_very_small_population_one_vessel(self):
        """Single vessel population handled gracefully without crashing."""
        single_df = self.df_normal.iloc[[0]].copy()
        detector = AISAnomalyDetector(random_state=42)
        detector.fit(single_df)
        scores, flags = detector.score(single_df)

        self.assertEqual(len(scores), 1)
        self.assertGreaterEqual(scores[0], 0.0)
        self.assertLessEqual(scores[0], 1.0)

    def test_very_small_population_two_vessels(self):
        """Two vessel population handled gracefully without sklearn parameter errors."""
        two_df = self.df_normal.iloc[:2].copy()
        detector = AISAnomalyDetector(contamination=0.5, random_state=42)
        detector.fit(two_df)
        scores, flags = detector.score(two_df)

        self.assertEqual(len(scores), 2)
        self.assertTrue((scores >= 0.0).all() and (scores <= 1.0).all())

    def test_deterministic_behaviour_with_fixed_random_state(self):
        """Identical random_state produces deterministic anomaly scores."""
        d1 = AISAnomalyDetector(random_state=123)
        d1.fit(self.df_normal)
        scores1, _ = d1.score(self.df_normal)

        d2 = AISAnomalyDetector(random_state=123)
        d2.fit(self.df_normal)
        scores2, _ = d2.score(self.df_normal)

        np.testing.assert_allclose(scores1, scores2, atol=1e-6)

    def test_score_features_df_convenience_method(self):
        """score_features_df appends new columns to DataFrame without modifying original structure."""
        detector = AISAnomalyDetector(random_state=42)
        enriched = detector.score_features_df(self.df_normal)

        self.assertIn("behavioral_anomaly_score", enriched.columns)
        self.assertIn("is_behavioral_anomaly", enriched.columns)
        self.assertEqual(len(enriched), len(self.df_normal))


    def test_typical_vessels_not_ranked_highly_anomalous(self):
        """Clearly typical vessels in a controlled synthetic population are not incorrectly ranked as highly anomalous."""
        detector = AISAnomalyDetector(contamination=0.10, random_state=42)
        detector.fit(self.df_normal)
        scores, _ = detector.score(self.df_normal)

        # In a uniform normal population, typical vessels should remain below the high anomaly threshold (0.65)
        for i, score in enumerate(scores):
            self.assertLess(score, 0.65, f"Normal vessel {i} unexpectedly assigned high anomaly score {score}")

        # The fleet average anomaly score should remain in the normal/mild baseline range (< 0.55)
        self.assertLess(float(np.mean(scores)), 0.55)

    def test_clearly_unusual_vessel_higher_score_than_normal_fleet(self):
        """Verify an intentionally constructed unusual vessel receives a higher anomaly score than normal vessels."""
        erratic = pd.DataFrame([{
            "mmsi": 999999999,
            "avg_speed_knots": 2.5,
            "max_speed_knots": 18.0,
            "speed_std": 7.5,
            "stop_count": 5,
            "avg_heading_change_deg": 65.0,
            "max_heading_change_deg": 160.0,
            "total_track_distance_km": 15.0,
            "ais_observation_count": 20,
            "speed_change_avg_knots": 5.0,
            "speed_change_max_knots": 15.0,
        }])
        population = pd.concat([self.df_normal, erratic], ignore_index=True)
        detector = AISAnomalyDetector(contamination=0.10, random_state=42)
        detector.fit(population)
        scores, flags = detector.score(population)

        erratic_score = scores[-1]
        normal_scores = scores[:-1]

        # The unusual vessel should score higher than the normal fleet average and 75th percentile
        self.assertGreater(erratic_score, float(np.mean(normal_scores)))
        self.assertGreater(erratic_score, float(np.percentile(normal_scores, 75)))
        self.assertTrue(flags[-1], "Clearly unusual vessel must be flagged.")

    def test_bounds_across_extreme_values(self):
        """Scores remain strictly within [0.0, 1.0] even with extreme or zeroed inputs."""
        extreme_df = pd.DataFrame([
            {col: 0.0 for col in BEHAVIORAL_FEATURE_COLUMNS},
            {col: 9999.0 for col in BEHAVIORAL_FEATURE_COLUMNS},
            {col: -100.0 for col in BEHAVIORAL_FEATURE_COLUMNS},
        ])
        extreme_df["mmsi"] = [1, 2, 3]
        detector = AISAnomalyDetector(random_state=42)
        detector.fit(extreme_df)
        scores, _ = detector.score(extreme_df)

        self.assertEqual(len(scores), 3)
        self.assertTrue((scores >= 0.0).all() and (scores <= 1.0).all())


if __name__ == '__main__':
    unittest.main()
