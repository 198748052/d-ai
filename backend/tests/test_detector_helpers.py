from __future__ import annotations

import unittest

from app.routers.detector import _cluster_red_sentences, _group_report, _parse_csv
from app.services.rewriter.calibration import extract_features
from app.services.rewriter.diagnosis import diagnose


class DetectorCsvTest(unittest.TestCase):
    def test_parse_csv(self) -> None:
        text = (
            "job_id,detector,detector_version,checked_at,score_before,score_after,red_sentences,notes\n"
            '1,知网,v1,2026-11-21,60,35,"首先，值得注意的是|这是一句标红句",note\n'
            "2,知网,v1,,101,20,bad,skip\n"
        )
        rows = _parse_csv(text)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["detector"], "知网")
        self.assertEqual(len(rows[0]["red_sentences"]), 2)

    def test_cluster_red_sentences(self) -> None:
        clusters = _cluster_red_sentences(
            [
                "首先，值得注意的是，该方法效果显著。",
                "这是一个很长的句子，" * 8,
                "不是简单的替换，而是深层的重构。",
            ]
        )
        labels = {item["label"] for item in clusters}
        self.assertIn("模板连接词", labels)
        self.assertIn("不是…而是", labels)

    def test_group_report(self) -> None:
        records = []
        for index in range(12):
            diagnosis = diagnose("首先，值得注意的是，赋能传统行业。" * (index % 3 + 1))
            records.append(
                {
                    "features": extract_features(diagnosis),
                    "score_after": 30 + index,
                    "detector": "知网",
                    "detector_version": "v1",
                }
            )
        for index in range(10):
            diagnosis = diagnose("本文方法显著提升精度。" * (index % 3 + 1))
            records.append(
                {
                    "features": extract_features(diagnosis),
                    "score_after": 40 + index,
                    "detector": "万方",
                    "detector_version": "v2",
                }
            )
        report = _group_report(records)
        self.assertEqual(report["sample_count"], 22)
        self.assertEqual(len(report["groups"]), 2)
        self.assertIn("知网 / v1", report["active_group"])


if __name__ == "__main__":
    unittest.main()
