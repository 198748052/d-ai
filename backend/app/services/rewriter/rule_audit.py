from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path

from ...core.config import LEXICON_DIR, PATTERN_DIR


def _entries() -> list[dict]:
    entries: list[dict] = []
    for directory, category in ((LEXICON_DIR, "lexicon"), (PATTERN_DIR, "regex")):
        for path in sorted(directory.glob("*.json")):
            data = json.loads(path.read_text(encoding="utf-8"))
            scope = data.get("scope", "general")
            for item in data.get("rules", []):
                entries.append(
                    {
                        "file": path.name,
                        "scope": scope,
                        "category": category,
                        "pattern": item.get("pattern", ""),
                        "replacements": [
                            str(value) for value in item.get("replacements", [])
                        ],
                        "severity": item.get("severity", "medium"),
                        "replace_mode": item.get("replace_mode", "all"),
                    }
                )
    return entries


def audit_rules() -> dict:
    entries = _entries()
    by_pattern: dict[str, list[dict]] = {}
    for entry in entries:
        by_pattern.setdefault(entry["pattern"], []).append(entry)

    duplicates: list[dict] = []
    conflicts: list[dict] = []
    for pattern, items in by_pattern.items():
        if len(items) < 2:
            continue
        variants = [
            {
                "file": item["file"],
                "scope": item["scope"],
                "category": item["category"],
                "replacements": item["replacements"],
            }
            for item in items
        ]
        record = {"pattern": pattern, "count": len(items), "variants": variants}
        duplicates.append(record)
        if len({tuple(item["replacements"]) for item in items}) > 1:
            conflicts.append(record)

    invalid_regex: list[dict] = []
    for entry in entries:
        if entry["category"] != "regex" or not entry["pattern"]:
            continue
        try:
            re.compile(entry["pattern"])
        except re.error as exc:
            invalid_regex.append(
                {
                    "file": entry["file"],
                    "pattern": entry["pattern"],
                    "error": str(exc),
                }
            )

    short_patterns = [
        {"file": entry["file"], "pattern": entry["pattern"], "severity": entry["severity"]}
        for entry in entries
        if entry["category"] == "lexicon" and len(entry["pattern"]) <= 1
    ]
    high_without_replacement = [
        {"file": entry["file"], "pattern": entry["pattern"]}
        for entry in entries
        if entry["category"] == "lexicon"
        and entry["severity"] == "high"
        and not entry["replacements"]
    ]

    return {
        "total": len(entries),
        "by_category": dict(Counter(entry["category"] for entry in entries)),
        "by_severity": dict(Counter(entry["severity"] for entry in entries)),
        "by_scope": dict(Counter(entry["scope"] for entry in entries)),
        "duplicate_patterns": duplicates,
        "conflicting_replacements": conflicts,
        "invalid_regex": invalid_regex,
        "short_lexicon_patterns": short_patterns,
        "high_severity_without_replacement": high_without_replacement,
        "summary": {
            "duplicate_patterns": len(duplicates),
            "conflicting_replacements": len(conflicts),
            "invalid_regex": len(invalid_regex),
            "short_lexicon_patterns": len(short_patterns),
            "high_severity_without_replacement": len(high_without_replacement),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit built-in rewrite rules")
    parser.add_argument("--output", default="", help="write JSON report to this path")
    parser.add_argument("--summary", action="store_true", help="print summary only")
    args = parser.parse_args()
    report = audit_rules()
    payload = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(payload + "\n", encoding="utf-8")
        print(f"report written to {args.output}")
        return
    if args.summary:
        print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
        return
    print(payload)


if __name__ == "__main__":
    main()
