from __future__ import annotations

import json
from dataclasses import dataclass, field

from sqlmodel import Session, select

from ..core.config import LEXICON_DIR, PATTERN_DIR
from ..models.models import FeatureRule, Preset

BUILTIN_PRESETS = [
    {
        "name": "学术论文",
        "style": "academic",
        "lexicon_scope": "academic",
        "strength": "medium",
        "person": "keep",
        "colloquial": 0,
        "length_ratio_min": 0.9,
        "length_ratio_max": 1.1,
        "banned_words": ["说白了", "踩坑", "拉满", "整明白", "搞", "挺", "贼", "其实", "说到底", "说实话", "特别", "非常", "超级"],
        "use_rule_engine": True,
        "use_llm": True,
        "max_rounds": 2,
    },
]


def _read_json(path) -> dict:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _upsert_rule(session: Session, existing: dict, scope: str, category: str, item: dict) -> None:
    key = (item["pattern"], scope, category)
    payload = {
        "name": item.get("note") or item["pattern"],
        "replacements": json.dumps(item.get("replacements", []), ensure_ascii=False),
        "severity": item.get("severity", "medium"),
        "replace_mode": item.get("replace_mode", "all"),
        "note": item.get("note", ""),
    }
    row = existing.get(key)
    if row is None:
        row = FeatureRule(
            category=category,
            scope=scope,
            pattern=item["pattern"],
            builtin=True,
            **payload,
        )
        session.add(row)
        existing[key] = row
        return
    row.name = payload["name"]
    row.replacements = payload["replacements"]
    row.severity = payload["severity"]
    row.replace_mode = payload["replace_mode"]
    row.note = payload["note"]


def seed(session: Session) -> None:
    existing_rows = session.exec(select(FeatureRule).where(FeatureRule.builtin == True)).all()  # noqa: E712
    existing = {(row.pattern, row.scope, row.category): row for row in existing_rows}
    seen: set[tuple[str, str, str]] = set()

    for path in sorted(LEXICON_DIR.glob("*.json")):
        data = _read_json(path)
        scope = data.get("scope", "general")
        for item in data.get("rules", []):
            seen.add((item["pattern"], scope, "lexicon"))
            _upsert_rule(session, existing, scope, "lexicon", item)

    for path in sorted(PATTERN_DIR.glob("*.json")):
        data = _read_json(path)
        scope = data.get("scope", "general")
        for item in data.get("rules", []):
            seen.add((item["pattern"], scope, "regex"))
            _upsert_rule(session, existing, scope, "regex", item)

    for key, row in existing.items():
        if key not in seen:
            session.delete(row)

    session.commit()

    existing_presets = session.exec(select(Preset)).all()
    academic = None
    for row in existing_presets:
        if row.name == "学术论文":
            academic = row
        else:
            session.delete(row)
    if academic is None:
        academic = Preset(name="学术论文", builtin=True)
        session.add(academic)

    item = BUILTIN_PRESETS[0]
    academic.style = item["style"]
    academic.lexicon_scope = item["lexicon_scope"]
    academic.strength = item["strength"]
    academic.person = item["person"]
    academic.colloquial = item["colloquial"]
    academic.length_ratio_min = item["length_ratio_min"]
    academic.length_ratio_max = item["length_ratio_max"]
    academic.banned_words = json.dumps(item["banned_words"], ensure_ascii=False)
    academic.use_rule_engine = True
    academic.use_llm = True
    academic.max_rounds = item["max_rounds"]
    academic.builtin = True
    session.commit()
