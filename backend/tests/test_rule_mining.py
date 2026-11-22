from __future__ import annotations

import unittest

from app.services.rewriter.rule_mining import mine_rules


class RuleMiningTest(unittest.TestCase):
    def test_finds_high_ai_lexicon_and_regex(self) -> None:
        high = [
            "首先，值得注意的是，赋能传统行业，打造闭环。不是简单的升级，而是深层的重构。",
            "其次，赋能传统行业，打造闭环，形成抓手。不是简单的升级，而是深层的重构。",
            "最后，赋能传统行业，打造闭环，形成抓手。",
        ]
        low = [
            "2024 年的实验中，样本量 1200 条，准确率从 82.3% 提升到 91.7%。",
            "我们在三个数据集上做了对照，失败案例主要集中在低光照条件。",
            "该方法的局限是样本量有限，结论仍需更多数据验证。",
        ]
        result = mine_rules(high, low)
        self.assertEqual(result["summary"]["high_count"], 3)
        self.assertTrue(result["lexicon"])
        patterns = {item["pattern"] for item in result["lexicon"]}
        self.assertTrue(any("赋能" in pattern or "抓手" in pattern for pattern in patterns))
        self.assertTrue(result["regex"])

    def test_requires_both_sides(self) -> None:
        result = mine_rules(["只有高 AI 文本"], [])
        self.assertEqual(result["lexicon"], [])
        self.assertIn("message", result["summary"])


if __name__ == "__main__":
    unittest.main()
