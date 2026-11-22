from __future__ import annotations

import unittest

from app.services.rewriter.eval import (
    DEFAULT_SAMPLES_PATH,
    evaluate_samples,
    load_samples,
    summarize,
)
from app.services.rewriter.rule_audit import audit_rules


class EvalHarnessTest(unittest.TestCase):
    def test_fixture_runs_without_llm(self) -> None:
        samples = load_samples(DEFAULT_SAMPLES_PATH)
        self.assertGreaterEqual(len(samples), 5)
        results = evaluate_samples(samples)
        self.assertEqual(len(results), len(samples))
        summary = summarize(results)
        self.assertEqual(summary["samples"], len(samples))
        self.assertIn("avg_drop", summary)


class RuleAuditTest(unittest.TestCase):
    def test_report_shape(self) -> None:
        report = audit_rules()
        self.assertGreater(report["total"], 0)
        self.assertIn("summary", report)
        self.assertIn("conflicting_replacements", report)


if __name__ == "__main__":
    unittest.main()
