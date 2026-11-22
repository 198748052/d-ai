from __future__ import annotations

import unittest

from app.services.rewriter.context_guard import load_whitelist
from app.services.rewriter.orchestrator import (
    RewriteContext,
    _sentence_coverage,
    _sentence_risks,
    rewrite_document,
    rewrite_single,
)
from app.services.rewriter.rule_engine import Rule, RuleEngine

_REWRITES = [
    "作者在这里换了一种说法，把原来的判断拆成两个层次来讲。",
    "这一句重新组织了语序，并把抽象表述改成了具体动作。",
    "结尾处调整了连接方式，读起来更像人工写作的节奏。",
]


class NoopParagraphLLM:
    """主改写不改动正文，用来验证补全覆盖会强制重写。"""

    configured = True

    async def rewrite_paragraph(
        self, text, ctx, round_index=0, hits=None, context=None, temperature=None
    ):
        return text

    async def rewrite_unchanged(self, text, untouched, ctx, context=None):
        if not isinstance(untouched, list):
            raise TypeError("untouched must be a list of sentences")
        count = max(1, len([s for s in text.split("。") if s.strip()]))
        return "".join(_REWRITES[index % len(_REWRITES)] for index in range(count))

    async def correct_paragraph(self, text, hits, ctx, context=None):
        return text

    async def adjust_rhythm(self, text, metrics, ctx, issues=None):
        return text

    async def rewrite_low_perplexity(self, text, flagged, ctx):
        return text

    async def integrate_facts(self, text, facts, ctx):
        return text


class DensityRaisingLLM(NoopParagraphLLM):
    """改写后 AI 特征密度上升，用来验证不再整段退回原文。"""

    async def rewrite_paragraph(
        self, text, ctx, round_index=0, hits=None, context=None, temperature=None
    ):
        return text + "赋能抓手"

    async def rewrite_unchanged(self, text, untouched, ctx, context=None):
        return text


class SentenceCoverageTest(unittest.TestCase):
    def test_detects_untouched_sentences(self) -> None:
        coverage, changed, untouched = _sentence_coverage(
            "第一句保持完整。第二句也会保留。",
            "第一句保持完整。第二句换了说法。",
        )
        self.assertEqual(changed, 1)
        self.assertEqual(untouched, 1)
        self.assertEqual(coverage, 0.5)


class FullCoverageRewriteTest(unittest.IsolatedAsyncioTestCase):
    def _context(self) -> RewriteContext:
        return RewriteContext(
            style="academic",
            use_rule_engine=False,
            use_llm=True,
            max_rounds=1,
            whitelist=load_whitelist(),
        )

    async def test_untouched_sentences_get_rewritten(self) -> None:
        text = (
            "本文围绕A对B的影响展开研究，并结合样本数据讨论了作用机制。"
            "实验结果表明，该方法在多数测试条件下都能保持稳定。"
            "\n\n"
            "本文进一步分析了C在不同场景下的作用，并比较了两种处理方式。"
            "结果具有一定的参考价值，但仍需要更多样本验证。"
        )
        response = await rewrite_document(text, self._context(), [], NoopParagraphLLM())
        self.assertEqual(response.stats.sentences, 4)
        self.assertGreaterEqual(response.stats.coverage, 0.9)
        self.assertNotIn("本文围绕A对B的影响展开研究", response.rewritten_text)
        self.assertNotIn("结果具有一定的参考价值", response.rewritten_text)

    async def test_density_increase_does_not_revert_whole_paragraph(self) -> None:
        text = (
            "本文围绕A对B的影响展开研究，并结合样本数据讨论了作用机制。"
            "实验结果表明，该方法在多数测试条件下都能保持稳定。"
        )
        response = await rewrite_document(text, self._context(), [], DensityRaisingLLM())
        self.assertIn("赋能抓手", response.rewritten_text)
        self.assertNotEqual(response.paragraphs[0].rewritten, response.paragraphs[0].original)

    async def test_headings_stay_unchanged_by_default(self) -> None:
        text = "一、研究背景\n\n本文围绕A对B的影响展开研究，并讨论了作用机制。"
        response = await rewrite_document(text, self._context(), [], NoopParagraphLLM())
        self.assertEqual(response.paragraphs[0].rewritten, "一、研究背景")
        self.assertGreaterEqual(response.stats.coverage, 0.9)

    async def test_rewrite_single_returns_rewritten_text(self) -> None:
        text = "本文围绕A对B的影响展开研究，并讨论了作用机制。"
        result, _warnings = await rewrite_single(
            text, self._context(), [], NoopParagraphLLM()
        )
        self.assertNotEqual(result.rewritten, text)

    def test_sentence_risks_report_rule_hits(self) -> None:
        ctx = self._context()
        engine = RuleEngine([Rule("赋能", ["提升"], "lexicon", "high")], load_whitelist())
        risks = _sentence_risks("赋能行业。正常句子。", engine, ctx)
        self.assertEqual(len(risks), 2)
        self.assertGreaterEqual(risks[0]["hits"], 1)
        self.assertGreaterEqual(risks[0]["risk"], 0.0)


if __name__ == "__main__":
    unittest.main()
