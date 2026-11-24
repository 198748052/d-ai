from __future__ import annotations

import time
import unittest

from app.services.rewriter.timing import (
    add_coverage,
    add_llm,
    add_ppl,
    add_rhythm,
    add_rule,
    finish_timing,
    start_timing,
)


class RewriteTimingTest(unittest.TestCase):
    def test_collects_metrics(self) -> None:
        timing = start_timing()
        add_llm(1.5)
        add_llm(0.5)
        add_ppl(0.25)
        add_rule(0.1)
        add_rhythm()
        add_coverage()
        data = finish_timing(timing, time.perf_counter() - 2)
        self.assertEqual(data["llm_calls"], 2)
        self.assertAlmostEqual(data["llm_seconds"], 2.0)
        self.assertEqual(data["ppl_calls"], 1)
        self.assertAlmostEqual(data["ppl_seconds"], 0.25)
        self.assertAlmostEqual(data["rule_seconds"], 0.1)
        self.assertEqual(data["rhythm_calls"], 1)
        self.assertEqual(data["coverage_passes"], 1)
        self.assertGreaterEqual(data["total_seconds"], 2.0)


if __name__ == "__main__":
    unittest.main()
