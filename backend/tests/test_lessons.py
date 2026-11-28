from __future__ import annotations

import unittest
from unittest.mock import patch

from sqlmodel import Session, SQLModel, create_engine

from app.models.models import RewriteLesson
from app.services.protector import Protector
from app.services.rewriter.context_guard import load_whitelist
from app.services.rewriter.lessons import (
    LEXICAL_KIND,
    _normalize_pattern,
    clear_lessons,
    extract_lexical_terms,
    extract_template,
    lesson_stats,
    list_lessons,
    match_forbidden_terms,
    recent_forbidden_terms,
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

    def test_extract_lexical_terms(self) -> None:
        terms = extract_lexical_terms(
            "首先，该方案显著提升了治理效能，具有十分重要的意义。"
        )
        self.assertEqual(terms["首先"][0], "connector")
        self.assertIn("显著提升", terms)
        self.assertIn("重要意义", terms)
        self.assertEqual(terms["显著提升"][0], "collocation")

    def test_legacy_template_rows_are_not_injected(self) -> None:
        with Session(self.engine) as session:
            session.add(
                RewriteLesson(
                    style="academic",
                    kind="low_perplexity",
                    sentence="首先，值得注意的是，本文具有十分重要的意义。",
                    pattern="首先，值得注意的是，本文具有十分重要的意义。",
                    template="首先，值得注意的是，{内容}具有十分重要的意义。",
                    status="active",
                    outcome="survived",
                    hits=5,
                )
            )
            session.commit()
        self.assertEqual(recent_lessons("academic"), [])
        self.assertEqual(recent_forbidden_terms("academic"), [])

    def test_term_activates_only_after_repeated_sentences(self) -> None:
        sentence = "首先，值得注意的是，本文在多个方面具有十分重要的意义。"
        record_lesson(
            style="academic",
            sentence=sentence,
            outcome="pending",
            source_job_id=1,
        )
        self.assertEqual(recent_lessons("academic"), [])
        rows = list_lessons(style="academic")
        self.assertTrue(rows)
        self.assertTrue(all(row.kind == LEXICAL_KIND for row in rows))
        self.assertTrue(all(row.status == "candidate" for row in rows))

        record_lesson(
            style="academic",
            sentence=sentence,
            outcome="survived",
            source_job_id=1,
        )
        self.assertEqual(recent_lessons("academic"), [])

        record_lesson(
            style="academic",
            sentence="首先，该研究在多个层面具有十分重要的意义。",
            outcome="survived",
            source_job_id=2,
        )
        hints = recent_lessons("academic")
        self.assertTrue(any("首先" in hint for hint in hints))
        row = next(row for row in list_lessons(style="academic") if row.pattern == "首先")
        self.assertEqual(row.hits, 2)
        self.assertEqual(row.status, "active")

        record_lesson(
            style="academic",
            sentence="首先，该研究在多个层面具有十分重要的意义。",
            outcome="survived",
            source_job_id=3,
        )
        row = next(row for row in list_lessons(style="academic") if row.pattern == "首先")
        self.assertEqual(row.hits, 2)

    def test_prompt_injection_caps_lessons_at_50(self) -> None:
        ctx = LLMContext(
            lessons=[
                f"词语{i}：这是一段用于测试的禁用表达，长度适中"
                for i in range(80)
            ]
        )
        lines: list[str] = []
        LLMEngine._append_lessons(lines, ctx)
        count = sum(1 for line in lines if line.startswith("- [禁用]"))
        self.assertEqual(count, 50)
        self.assertIn("AI 高频表达", "\n".join(lines))

    def test_forbidden_terms_are_matched(self) -> None:
        first = "首先，该方案显著提升了治理效能。"
        second = "首先，该模型显著提升了处理速度。"
        record_lesson(
            style="academic",
            sentence=first,
            outcome="survived",
            source_job_id=1,
        )
        record_lesson(
            style="academic",
            sentence=second,
            outcome="survived",
            source_job_id=2,
        )
        terms = recent_forbidden_terms("academic")
        self.assertIn("首先", terms)
        self.assertIn("首先", match_forbidden_terms(first, terms))
        self.assertEqual(
            match_forbidden_terms(
                "这段文字采用了完全不同的结构和表达方式。", terms
            ),
            [],
        )

    def test_clear_lessons_removes_rows(self) -> None:
        sentence = "首先，值得注意的是，本文在多个方面具有十分重要的意义。"
        record_lesson(
            style="academic",
            sentence=sentence,
            outcome="survived",
            source_job_id=1,
        )
        record_lesson(
            style="general",
            sentence=sentence,
            outcome="survived",
            source_job_id=2,
        )
        academic_rows = list_lessons(style="academic")
        general_rows = list_lessons(style="general")
        self.assertTrue(academic_rows)
        self.assertTrue(general_rows)
        self.assertEqual(clear_lessons("academic"), len(academic_rows))
        self.assertEqual(list_lessons(style="academic"), [])
        self.assertEqual(len(list_lessons(style="general")), len(general_rows))

        self.assertEqual(clear_lessons(), len(general_rows))
        self.assertEqual(lesson_stats()["total"], 0)

    def test_ignored_lesson_is_not_injected(self) -> None:
        record_lesson(
            style="academic",
            sentence="综上所述，样本数量仍然偏少。",
            outcome="survived",
            source_job_id=1,
        )
        record_lesson(
            style="academic",
            sentence="综上所述，实验结果仍需复核。",
            outcome="survived",
            source_job_id=2,
        )
        row = next(
            row for row in list_lessons(style="academic") if row.pattern == "综上所述"
        )
        update_lesson(row.id, status="ignored")
        self.assertEqual(recent_lessons("academic"), [])
        self.assertEqual(lesson_stats("academic")["ignored"], 1)


class FakePPLRewriteLLM:
    def __init__(self, rewritten: str):
        self.rewritten = rewritten

    async def rewrite_low_perplexity(self, text, flagged, ctx, **kwargs):
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
                        "sentence": "首先，该方案显著提升了治理效能，具有十分重要的意义。",
                        "perplexity": 10.0,
                        "tokens": 20,
                    }
                ]
            return [
                {
                    "sentence": "该方案把审批时间缩短了一半，基层反馈更直接。",
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
        self.assertTrue(rows)
        self.assertTrue(all(row.kind == LEXICAL_KIND for row in rows))
        self.assertTrue(all(row.outcome == "fixed" for row in rows))
        self.assertTrue(all(row.hits == 1 for row in rows))

    async def test_low_ppl_survived_is_recorded(self) -> None:
        original = "这是一段足够长的原始文本，用来触发困惑度检测流程，并记录低困惑度句子。" * 2
        protector = Protector([])
        masked, spans = protector.protect(original)

        def fake_perplexities(text, max_sentences=40):
            return [
                {
                    "sentence": "首先，该方案显著提升了治理效能，具有十分重要的意义。",
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
        self.assertTrue(rows)
        self.assertTrue(all(row.kind == LEXICAL_KIND for row in rows))
        self.assertTrue(all(row.outcome == "survived" for row in rows))
        self.assertTrue(all(row.hits == 1 for row in rows))


if __name__ == "__main__":
    unittest.main()
