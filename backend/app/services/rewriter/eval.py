from __future__ import annotations

import argparse
import json
from pathlib import Path

from ...core.config import LEXICON_DIR, PATTERN_DIR
from .context_guard import ReplacementGuard, load_blacklist, load_whitelist
from .diagnosis import diagnose
from .rule_engine import RewriteOptions, Rule, RuleEngine

DEFAULT_SAMPLES_PATH = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "rewrite_eval.json"


def load_builtin_rules(
    lexicon_scope: str = "academic",
    style: str = "academic",
) -> list[Rule]:
    """Load JSON rules without touching the database, mirroring orchestrator.load_rules."""
    selected: dict[tuple[str, str], Rule] = {}

    def collect(directory: Path, category: str) -> None:
        for path in sorted(directory.glob("*.json")):
            data = json.loads(path.read_text(encoding="utf-8"))
            scope = data.get("scope", "general")
            if scope not in ("general", lexicon_scope):
                continue
            for item in data.get("rules", []):
                if (
                    style in {"academic", "official"}
                    and scope == "general"
                    and item.get("severity") == "low"
                ):
                    continue
                key = (item["pattern"], category)
                if key in selected and scope != lexicon_scope:
                    continue
                selected[key] = Rule(
                    pattern=item["pattern"],
                    replacements=[str(value) for value in item.get("replacements", [])],
                    category=category,
                    severity=item.get("severity", "medium"),
                    replace_mode=item.get("replace_mode", "all"),
                    note=item.get("note", ""),
                )

    collect(LEXICON_DIR, "lexicon")
    collect(PATTERN_DIR, "regex")
    return list(selected.values())


def load_samples(path: str | Path = DEFAULT_SAMPLES_PATH) -> list[dict]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, dict):
        data = data.get("samples", [])
    return [item for item in data if str(item.get("text") or "").strip()]


def evaluate_samples(
    samples: list[dict],
    style: str = "academic",
    lexicon_scope: str = "academic",
) -> list[dict]:
    """Run the rule-only pipeline on fixed samples and record proxy changes.

    This harness is free to run: it does not call the LLM or a paid detector.
    Use it to check whether rule changes reduce known AI features before
    spending money on real detector checks.
    """
    rules = load_builtin_rules(lexicon_scope=lexicon_scope, style=style)
    engine = RuleEngine(rules, load_whitelist(), ReplacementGuard(load_blacklist()))
    options = RewriteOptions(style=style, strength="medium")
    results: list[dict] = []
    for index, sample in enumerate(samples):
        text = str(sample.get("text") or "")
        before = diagnose(text, style)
        rewritten = engine.rewrite(text, options)
        after = diagnose(rewritten, style)
        before_total = float(before.get("total_per_1000") or 0.0)
        after_total = float(after.get("total_per_1000") or 0.0)
        results.append(
            {
                "id": sample.get("id") or f"sample-{index + 1}",
                "chars": before.get("chars", 0),
                "before_total": round(before_total, 2),
                "after_total": round(after_total, 2),
                "drop": round(before_total - after_total, 2),
                "drop_ratio": round(
                    (before_total - after_total) / before_total, 4
                )
                if before_total
                else 0.0,
                "rewritten": rewritten,
            }
        )
    return results


def summarize(results: list[dict]) -> dict:
    count = len(results)
    if not count:
        return {
            "samples": 0,
            "avg_before": 0.0,
            "avg_after": 0.0,
            "avg_drop": 0.0,
            "improved": 0,
            "regressed": 0,
        }
    avg_before = sum(float(item["before_total"]) for item in results) / count
    avg_after = sum(float(item["after_total"]) for item in results) / count
    return {
        "samples": count,
        "avg_before": round(avg_before, 2),
        "avg_after": round(avg_after, 2),
        "avg_drop": round(avg_before - avg_after, 2),
        "improved": sum(
            1 for item in results if item["after_total"] < item["before_total"]
        ),
        "regressed": sum(
            1 for item in results if item["after_total"] > item["before_total"] + 1.5
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Rule-only rewrite evaluation harness")
    parser.add_argument("--samples", default=str(DEFAULT_SAMPLES_PATH))
    parser.add_argument("--style", default="academic")
    parser.add_argument("--lexicon-scope", default="academic")
    parser.add_argument("--json", action="store_true", help="print full JSON")
    args = parser.parse_args()

    samples = load_samples(args.samples)
    results = evaluate_samples(
        samples, style=args.style, lexicon_scope=args.lexicon_scope
    )
    summary = summarize(results)
    if args.json:
        print(json.dumps({"summary": summary, "results": results}, ensure_ascii=False, indent=2))
        return
    print(
        f"samples={summary['samples']} before={summary['avg_before']} "
        f"after={summary['avg_after']} drop={summary['avg_drop']} "
        f"improved={summary['improved']} regressed={summary['regressed']}"
    )
    for item in results:
        print(
            f"{item['id']}: {item['before_total']} -> {item['after_total']} "
            f"({item['drop_ratio']:.0%})"
        )


if __name__ == "__main__":
    main()
