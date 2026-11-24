from __future__ import annotations

import unittest

from app.services.rewriter.context_guard import (
    ReplacementGuard,
    load_blacklist,
    load_whitelist,
)
from app.services.rewriter.diagnosis import compare, diagnose
from app.services.rewriter.features import short_sentence_runs, structural_metrics
from app.services.rewriter.guards import acceptable, merge_short_runs
from app.services.rewriter.leakage import clean, scan
from app.services.rewriter.rule_engine import Rule, RuleEngine, RewriteOptions


class LeakageTest(unittest.TestCase):
    def test_ui_residue_is_removed(self) -> None:
        text = "这是正文。已深度思考（用时 7.41 秒）继续写。"
        cleaned, hits = clean(text)
        self.assertNotIn("深度思考", cleaned)
        self.assertTrue(any(item["id"] == "X2" for item in hits))

    def test_checkbox_is_removed(self) -> None:
        cleaned, hits = clean("- [x] 完成任务\n正文内容。")
        self.assertNotIn("[x]", cleaned)
        self.assertTrue(any(item["id"] == "X4" for item in hits))

    def test_plain_text_untouched(self) -> None:
        text = "这是一段正常的学术文本，没有过程痕迹。"
        cleaned, hits = clean(text)
        self.assertEqual(cleaned, text)
        self.assertEqual(hits, [])


class WhitelistTest(unittest.TestCase):
    def test_fixed_collocations_are_protected(self) -> None:
        engine = RuleEngine(
            [
                Rule("生态环境", ["生态"], "lexicon", "high"),
                Rule("数字化转型", ["数字化升级"], "lexicon", "medium"),
                Rule("控制闭环", ["完整流程"], "lexicon", "high"),
            ],
            load_whitelist(),
            ReplacementGuard(load_blacklist()),
        )
        text = "生态环境和数字化转型需要保护，控制闭环也要保护。"
        output = engine.rewrite(text, RewriteOptions(style="academic", strength="medium"))
        self.assertIn("生态环境", output)
        self.assertIn("数字化转型", output)
        self.assertIn("控制闭环", output)


class ReplacementGuardTest(unittest.TestCase):
    def test_banned_product_is_skipped(self) -> None:
        guard = ReplacementGuard(load_blacklist())
        self.assertEqual(guard.pick(["不只仅", "并非"], {}), "并非")

    def test_empty_replacement_means_delete(self) -> None:
        guard = ReplacementGuard(load_blacklist())
        self.assertEqual(guard.pick([""], {}), "")

    def test_rule_engine_can_delete(self) -> None:
        engine = RuleEngine([Rule("首先", [""], "lexicon", "high")])
        output = engine.rewrite("首先，本文讨论问题。", RewriteOptions(style="academic"))
        self.assertNotIn("首先", output)

    def test_backrefs_are_expanded(self) -> None:
        engine = RuleEngine(
            [
                Rule(
                    r"对([^，。；]{1,20})进行([^，。；的]{1,10})(?=[，。；！？、]|$)",
                    [r"\2\1"],
                    "regex",
                    "medium",
                )
            ]
        )
        output = engine.rewrite("对数据进行分析。", RewriteOptions(style="academic"))
        self.assertEqual(output, "分析数据。")


class DiagnosisTest(unittest.TestCase):
    def test_flavors_and_plan(self) -> None:
        text = (
            "首先，值得注意的是，随着数字经济的发展，农村电商发挥着越来越重要的作用。"
            "赋能传统行业，打造全方位的智能化解决方案。让我们拭目以待。"
        )
        result = diagnose(text, "academic")
        self.assertGreater(result["total_per_1000"], 0)
        self.assertIn(result["dominant"], result["flavors"])
        self.assertTrue(result["plan"])
        self.assertTrue(any(item["code"] == "C-04" for item in result["plan"]))

    def test_compare_reports_drop(self) -> None:
        before = diagnose("首先，值得注意的是，赋能传统行业。", "academic")
        after = diagnose("传统行业得到支持。", "academic")
        report = compare(before, after)
        self.assertTrue(report["improved"])
        self.assertGreater(report["drop"], 0)


class StructuralGuardTest(unittest.TestCase):
    def test_short_sentence_run(self) -> None:
        self.assertEqual(short_sentence_runs("很短。也很短。还很短。"), 1)

    def test_merge_short_runs(self) -> None:
        output = merge_short_runs("很短。也很短。还很短。这是一句正常长度的话。")
        self.assertNotEqual(output, "很短。也很短。还很短。这是一句正常长度的话。")

    def test_acceptable_rejects_new_short_run(self) -> None:
        ok, reason = acceptable(
            "这是一句长度正常的句子，包含足够多的信息。",
            "很短。也很短。还很短。",
        )
        self.assertFalse(ok)
        self.assertIn("短句", reason)

    def test_structural_metrics(self) -> None:
        metrics = structural_metrics("这是一个基于深度学习的多模态的实时的目标检测算法。")
        self.assertGreaterEqual(metrics["de_chain"], 1)

    def test_post_rhythm_respects_max_cv(self) -> None:
        engine = RuleEngine([])
        text = (
            "本文研究了A对B的影响。实验采用了两种不同的方法。"
            "结果表明该方法效果较好。进一步分析发现存在一些差异。"
            "这些差异值得继续讨论。未来还需要更多样本验证。"
        )
        output = engine.post_rhythm(text, 0.45, max_cv=0.6)
        self.assertLessEqual(structural_metrics(output)["cv"], 0.61)


if __name__ == "__main__":
    unittest.main()
