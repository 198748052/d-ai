from __future__ import annotations

import unittest

from app.schemas import ParagraphResult
from app.services.rewriter.calibration import build_report, extract_features, fit_linear
from app.services.rewriter.candidate import score_candidate, select_candidate
from app.services.rewriter.content import (
    assign_facts,
    content_density,
    scan_content_needs,
    verify_content,
)
from app.services.rewriter.diagnosis import diagnose
from app.services.rewriter.rule_engine import RuleEngine, RewriteOptions
from app.services.rewriter.structure import restructure


class ContentLayerTest(unittest.TestCase):
    def test_scan_finds_data_and_citation_gaps(self) -> None:
        text = "本文方法显著提升了检测精度。研究表明该方法具有明显优势。"
        questions = scan_content_needs(text)
        kinds = {question.kind for question in questions}
        self.assertIn("data", kinds)
        self.assertIn("citation", kinds)

    def test_density_counts_citations(self) -> None:
        density = content_density("结果提升到 91.7%（Zhang et al., 2024）。")
        self.assertGreaterEqual(density["numbers"], 1)
        self.assertGreaterEqual(density["citations"], 1)

    def test_assign_facts_by_anchor(self) -> None:
        facts = [
            {"kind": "data", "text": "精度从 82% 提升到 91%", "anchor": "第2段"},
            {"kind": "citation", "text": "Li et al., 2023", "anchor": ""},
        ]
        assignments = assign_facts(facts, ["第一段内容", "第二段内容"])
        self.assertEqual(len(assignments[1]), 1)

    def test_verify_reports_unused_fact(self) -> None:
        facts = [{"kind": "data", "text": "样本量 1200 条，精度 91.7%", "anchor": ""}]
        report = verify_content("原文没有数据。", "改写后仍然没有数据。", facts)
        self.assertEqual(report["facts_used"], 0)
        self.assertTrue(report["warnings"])


class StructureLayerTest(unittest.TestCase):
    def _result(self, index: int, text: str) -> ParagraphResult:
        return ParagraphResult(
            index=index,
            original=text,
            rewritten=text,
            changed_ratio=0.0,
            length_ratio=1.0,
        )

    def test_merges_two_short_paragraphs(self) -> None:
        results = [
            self._result(0, "这是一个足够长的段落，用于形成对照。" * 5),
            self._result(1, "短段一。"),
            self._result(2, "短段二。"),
            self._result(3, "另一个较长段落，用于保持结构。" * 4),
        ]
        new, changes = restructure(results)
        self.assertTrue(changes)
        self.assertLess(len(new), len(results))

    def test_split_long_paragraph(self) -> None:
        long_text = "这是第一句，包含足够的信息。" * 14
        results = [
            self._result(0, long_text),
            self._result(1, "另一个段落，长度正常。" * 3),
            self._result(2, "第三个段落，长度正常。" * 3),
        ]
        new, changes = restructure(results, intensity="light")
        self.assertTrue(changes)
        self.assertGreaterEqual(len(new), len(results))


class CandidateLayerTest(unittest.TestCase):
    def test_selector_prefers_lower_ai_candidate(self) -> None:
        original = "本文方法显著提升了检测精度，具有重要意义。"
        bad = original
        good = "在自建数据集上，检测精度从 82.3% 提升到 91.7%，样本量 1200 条。"
        before = diagnose(original, "academic")
        best, scores = select_candidate(original, [bad, good], before)
        self.assertEqual(best, good)
        self.assertEqual(len(scores), 2)

    def test_score_shape(self) -> None:
        before = diagnose("原文。", "academic")
        after = diagnose("改写后的文本。", "academic")
        score = score_candidate("原文。", "改写后的文本。", before, after)
        for key in ("score", "proxy", "semantic", "natural", "content"):
            self.assertIn(key, score)


class CalibrationLayerTest(unittest.TestCase):
    def test_report_with_varied_samples(self) -> None:
        records = []
        for index in range(25):
            text = "首先，值得注意的是，赋能传统行业。" * (index % 5 + 1)
            diagnosis = diagnose(text, "academic")
            records.append(
                {
                    "features": extract_features(diagnosis),
                    "score_after": 20 + index,
                }
            )
        report = build_report(records)
        self.assertEqual(report["sample_count"], 25)
        self.assertTrue(report["correlations"])
        self.assertIn("recommendation", report)
        weights = fit_linear(records, ["proxy_total", "template_per_1000", "cv"])
        self.assertTrue(weights)
        self.assertIn("coefficients", weights)


class SentenceLayerTest(unittest.TestCase):
    def test_connective_split_and_thin_in_deep_mode(self) -> None:
        engine = RuleEngine([])
        text = "实验结果表明方法有效，因此可以推广，然而样本量有限，因此需要更多验证。"
        output = engine.rewrite(
            text, RewriteOptions(style="academic", strength="medium", deep=True)
        )
        self.assertIn("。", output)
        self.assertLessEqual(output.count("因此"), 1)

    def test_stable_mode_keeps_connectives(self) -> None:
        engine = RuleEngine([])
        text = "实验结果表明方法有效，因此可以推广。"
        output = engine.rewrite(
            text, RewriteOptions(style="academic", strength="medium", deep=False)
        )
        self.assertIn("因此", output)


if __name__ == "__main__":
    unittest.main()
