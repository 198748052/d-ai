from __future__ import annotations

import re

from ..segmenter import split_sentences
from .context_guard import Whitelist, load_whitelist
from .diagnosis import diagnose
from .features import analyze
from .rule_engine import RuleEngine

SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}


def _kept_matches(
    matches: list[re.Match[str]],
    text: str,
    whitelist: Whitelist | None,
) -> list[re.Match[str]]:
    if whitelist is None:
        return matches
    return [
        match
        for match in matches
        if not whitelist.is_protected(text, match.start(), match.end())
    ]


def audit_text(
    text: str,
    engine: RuleEngine,
    use_local: bool = False,
    whitelist: Whitelist | None = None,
    context: str = "academic",
) -> dict:
    whitelist = whitelist or load_whitelist()
    items: list[dict] = []
    total = 0

    for rule in engine.regex_rules:
        if not rule.pattern:
            continue
        try:
            if rule.pattern.startswith("^"):
                matches = [
                    match
                    for sentence in split_sentences(text)
                    for match in re.finditer(rule.pattern, sentence)
                ]
            else:
                matches = list(re.finditer(rule.pattern, text, flags=re.MULTILINE))
        except re.error:
            continue
        matches = _kept_matches(matches, text, whitelist)
        if matches:
            items.append(
                {
                    "category": "regex",
                    "pattern": rule.pattern,
                    "severity": rule.severity,
                    "count": len(matches),
                    "note": rule.note or rule.pattern,
                }
            )
            total += len(matches)

    for rule in engine.lexicon_rules:
        if not rule.pattern:
            continue
        try:
            matches = list(re.finditer(re.escape(rule.pattern), text))
        except re.error:
            matches = []
        matches = _kept_matches(matches, text, whitelist)
        count = len(matches)
        if count:
            items.append(
                {
                    "category": "lexicon",
                    "pattern": rule.pattern,
                    "severity": rule.severity,
                    "count": count,
                    "note": rule.note or rule.pattern,
                }
            )
            total += count

    items.sort(key=lambda item: (SEVERITY_ORDER.get(item["severity"], 9), -item["count"]))
    metrics = analyze(text)
    if use_local:
        try:
            from ..local_model import summarize

            local = summarize(text)
            metrics["perplexity"] = local["average"]
            metrics["perplexity_min"] = local["min"]
            metrics["perplexity_max"] = local["max"]
            metrics["low_ppl_count"] = local["low_count"]
        except Exception:  # noqa: BLE001
            pass

    diagnosis = diagnose(text, context)
    return {
        "total": total,
        "items": items[:60],
        "metrics": metrics,
        "diagnosis": diagnosis,
    }


def collect_hits(
    text: str,
    engine: RuleEngine,
    allowed: set[str] | None = None,
    limit: int = 30,
    whitelist: Whitelist | None = None,
) -> list[dict]:
    """Return concrete rule hits with matched text, used to constrain the LLM."""
    allowed = allowed or {"high", "medium"}
    whitelist = whitelist or load_whitelist()
    hits: list[dict] = []

    for rule in engine.regex_rules:
        if rule.severity not in allowed or not rule.pattern:
            continue
        try:
            matches = list(re.finditer(rule.pattern, text, flags=re.MULTILINE))
        except re.error:
            continue
        matches = _kept_matches(matches, text, whitelist)
        if not matches:
            continue
        hits.append(
            {
                "category": "regex",
                "pattern": rule.pattern,
                "matched": matches[0].group(0)[:40],
                "severity": rule.severity,
                "count": len(matches),
                "note": rule.note or rule.pattern,
                "replacements": rule.replacements,
            }
        )

    for rule in engine.lexicon_rules:
        if rule.severity not in allowed or not rule.pattern:
            continue
        try:
            matches = list(re.finditer(re.escape(rule.pattern), text))
        except re.error:
            continue
        matches = _kept_matches(matches, text, whitelist)
        if not matches:
            continue
        hits.append(
            {
                "category": "lexicon",
                "pattern": rule.pattern,
                "matched": rule.pattern,
                "severity": rule.severity,
                "count": len(matches),
                "note": rule.note or rule.pattern,
                "replacements": rule.replacements,
            }
        )

    hits.sort(key=lambda item: (SEVERITY_ORDER.get(item["severity"], 9), -item["count"]))
    return hits[:limit]
