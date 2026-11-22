from __future__ import annotations

import unittest

from app.services.rewriter.context_guard import load_whitelist
from app.services.rewriter.orchestrator import RewriteContext, rewrite_document


class FakeDocumentLLM:
    configured = True

    async def rewrite_document(self, text, ctx, hits=None, context=None):
        return text.replace("显著提升", "提高")


class DocumentRewriteTest(unittest.IsolatedAsyncioTestCase):
    async def test_document_mode_preserves_paragraphs_and_headings(self) -> None:
        text = "一、研究背景\n\n本文方法显著提升了检测精度。\n\n实验表明该方法有效。"
        ctx = RewriteContext(
            style="academic",
            use_rule_engine=True,
            use_llm=True,
            rewrite_granularity="document",
            whitelist=load_whitelist(),
        )
        response = await rewrite_document(text, ctx, [], FakeDocumentLLM())
        self.assertEqual(len(response.paragraphs), 3)
        self.assertEqual(response.paragraphs[0].rewritten, "一、研究背景")
        self.assertIn("提高", response.rewritten_text)


if __name__ == "__main__":
    unittest.main()
