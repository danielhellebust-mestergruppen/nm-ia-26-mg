from __future__ import annotations

import unittest

import numpy as np

from src.scoring import (
    apply_probability_floor,
    round_score,
    score_prediction,
    validate_prediction_tensor,
)


class ScoringTests(unittest.TestCase):
    def test_probability_floor(self) -> None:
        p = np.array([[[0.0, 1.0, 0.0, 0.0, 0.0, 0.0]]], dtype=np.float64)
        out = apply_probability_floor(p, floor=0.01)
        self.assertTrue(np.all(out >= 0.01))
        self.assertAlmostEqual(float(out.sum()), 1.0, places=8)

    def test_validation(self) -> None:
        p = np.full((2, 3, 6), 1.0 / 6.0, dtype=np.float64)
        ok, _ = validate_prediction_tensor(p, 2, 3)
        self.assertTrue(ok)

    def test_score_identity(self) -> None:
        gt = np.full((3, 3, 6), 1.0 / 6.0, dtype=np.float64)
        score = score_prediction(gt, gt.copy())
        self.assertGreater(score, 99.9)

    def test_round_average(self) -> None:
        self.assertAlmostEqual(round_score([50.0, 100.0]), 75.0)


if __name__ == "__main__":
    unittest.main()

