from __future__ import annotations

import unittest
from unittest.mock import patch

from sqlmodel import SQLModel, create_engine

from app.services.protector import Protector
from app.services.rewriter.context_guard import load_whitelist
from app.services.rewriter.lessons import (
    _normalize_pattern,
    extract_template,
    lesson_stats,
    list_lessons,
    match_forbidden_templates,
    recent_forbidden_templates,
    recent_lessons,
    record_lesson,
    update_lesson,
)
from app.services.rewriter.llm_engine import LLMContext, LLMEngine
from app.services.rewriter.orchestrator import RewriteContext, _enforce_perplexity
from app.services.rewriter.rule_engine import RuleEngine


class LessonLibraryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}
        )
        SQLModel.metadata.create_all(self.engine)
        self.patch = patch("app.services.rewriter.lessons.engine", self.engine)
        self.patch.start()

    def tearDown(self) -> None:
        self.patch.stop()
        self.engine.dispose()

    def test_pattern_normalization(self) -> None:
        pattern = _normalize_pattern(
            "2024年ABC公司在5个城市增长12.5%，引用“某研究”。"
        )
        self.assertIn("{日期}", pattern)
        self.assertIn("{术语}", pattern)
        self.assertIn("{数字}", pattern)
        self.assertIn("{引文}", pattern)

    def test_template_extraction_abstracts_content(self) -> None:
        template = extract_template(
            "首先，值得注意的是，2024年ABC公司在5个城市增长了12.5%。"
        )
        self.assertIn("首先", template)
        self.assertIn("值得注意", template)
        self.assertIn("{", template)
        self.assertNotIn("2024", template)
        self.assertNotIn("ABC", template)

    def test_pending_is_not_injected_and_survived_counts_once_per_job(self) -> None:
        sentence = "首先，值得注意的是，本文在多个方面具有十分重要的意义。"
        record_lesson(
            style="academic",
            sentence=sentence,
            outcome="pending",
            source_job_id=1,
        )
        self.assertEqual(recent_lessons("academic"), [])

        record_lesson(
            style="academic",
            sentence=sentence,
            outcome="survived",
            source_job_id=1,
            increment_hits=True,
        )
        hints = recent_lessons("academic")
        self.assertEqual(len(hints), 1)
        self.assertTrue(hints[0].startswith("["))
        self.assertTrue(list_lessons(style="academic")[0].template)

        record_lesson(
            style="academic",
            sentence=sentence,
            outcome="survived",
            source_job_id=1,
            increment_hits=True,
        )
        self.assertEqual(list_lessons(style="academic")[0].hits, 1)

        record_lesson(
            style="academic",
            sentence=sentence,
            outcome="survived",
            source_job_id=2,
            increment_hits=True,
        )
        self.assertEqual(list_lessons(style="academic")[0].hits, 2)

    def test_prompt_injection_caps_lessons_at_50(self) -> None:
        ctx = LLMContext(
            lessons=[
                f"模板{i}：这是一段用于测试的禁用模板，长度适中"
                for i in range(80)
            ]
        )
        lines: list[str] = []
        LLMEngine._append_lessons(lines, ctx)
        count = sum(1 for line in lines if line.startswith("- [禁用]"))
        self.assertEqual(count, 50)
        self.assertIn("禁用模板", "\n".join(lines))

    def test_forbidden_templates_are_matched(self) -> None:
        sentence = "首先，值得注意的是，本文在多个方面具有十分重要的意义。"
        record_lesson(
            style="academic",
            sentence=sentence,
            outcome="survived",
            source_job_id=1,
            increment_hits=True,
        )
        templates = recent_forbidden_templates("academic")
        self.assertTrue(templates)
        self.assertTrue(match_forbidden_templates(sentence, templates))
        self.assertEqual(
            match_forbidden_templates(
                "这段文字采用了完全不同的结构和表达方式。", templates
            ),
            [],
        )

    def test_ignored_lesson_is_not_injected(self) -> None:
        sentence = "综上所述，该研究具有重要的理论意义和现实意义。"
        record_lesson(
            style="academic",
            sentence=sentence,
            outcome="survived",
            source_job_id=1,
            increment_hits=True,
        )
        row = list_lessons(style="academic")[0]
        update_lesson(row.id, status="ignored")
        self.assertEqual(recent_lessons("academic"), [])
        self.assertEqual(lesson_stats("academic")["ignored"], 1)


class FakePPLRewriteLLM:
    def __init__(self, rewritten: str):
        self.rewritten = rewritten

    async def rewrite_low_perplexity(self, text, flagged, ctx):
        return self.rewritten


class PerplexityLessonTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}
        )
        SQLModel.metadata.create_all(self.engine)
        self.patch = patch("app.services.rewriter.lessons.engine", self.engine)
        self.patch.start()

    def tearDown(self) -> None:
        self.patch.stop()
        self.engine.dispose()

    async def test_low_ppl_fixed_is_recorded(self) -> None:
        original = "这是一段足够长的原始文本，用来触发困惑度检测流程，并记录低困惑度句子。" * 2
        rewritten = "这是一段改写后的文本，句式已经调整，长度和原文接近，用来模拟成功修复。" * 2
        protector = Protector([])
        masked, spans = protector.protect(original)
        calls = {"count": 0}

        def fake_perplexities(text, max_sentences=40):
            calls["count"] += 1
            if calls["count"] == 1:
                return [
                    {
                        "sentence": "这是一段足够长的原始文本，用来触发困惑度检测流程。",
                        "perplexity": 10.0,
                        "tokens": 20,
                    }
                ]
            return [
                {
                    "sentence": "这是一段改写后的文本，句式已经调整。",
                    "perplexity": 80.0,
                    "tokens": 20,
                }
            ]

        with patch(
            "app.services.local_model.status", return_value={"loaded": True}
        ), patch(
            "app.services.local_model.sentence_perplexities",
            side_effect=fake_perplexities,
        ), patch(
            "app.services.local_model.clause_perplexities", return_value=[]
        ):
            ctx = RewriteContext(
                style="academic",
                use_local_model=True,
                ppl_min=45,
                ppl_retry=1,
                ppl_severe=20,
                whitelist=load_whitelist(),
            )
            await _enforce_perplexity(
                0,
                original,
                original,
                ctx,
                FakePPLRewriteLLM(rewritten),
                LLMContext(),
                [],
                masked,
                protector,
                spans,
                [],
                RuleEngine([]),
                ctx.whitelist,
                job_id=1,
            )

        rows = list_lessons(style="academic")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].outcome, "fixed")
        self.assertEqual(rows[0].hits, 1)

    async def test_low_ppl_survived_is_recorded(self) -> None:
        original = "这是一段足够长的原始文本，用来触发困惑度检测流程，并记录低困惑度句子。" * 2
        protector = Protector([])
        masked, spans = protector.protect(original)

        def fake_perplexities(text, max_sentences=40):
            return [
                {
                    "sentence": "这是一段足够长的原始文本，用来触发困惑度检测流程。",
                    "perplexity": 10.0,
                    "tokens": 20,
                }
            ]

        with patch(
            "app.services.local_model.status", return_value={"loaded": True}
        ), patch(
            "app.services.local_model.sentence_perplexities",
            side_effect=fake_perplexities,
        ), patch(
            "app.services.local_model.clause_perplexities", return_value=[]
        ):
            ctx = RewriteContext(
                style="academic",
                use_local_model=True,
                ppl_min=45,
                ppl_retry=1,
                ppl_severe=20,
                whitelist=load_whitelist(),
            )
            await _enforce_perplexity(
                0,
                original,
                original,
                ctx,
                FakePPLRewriteLLM(original),
                LLMContext(),
                [],
                masked,
                protector,
                spans,
                [],
                RuleEngine([]),
                ctx.whitelist,
                job_id=2,
            )

        rows = list_lessons(style="academic")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].outcome, "survived")
        self.assertEqual(rows[0].hits, 1)


if __name__ == "__main__":
    unittest.main()
