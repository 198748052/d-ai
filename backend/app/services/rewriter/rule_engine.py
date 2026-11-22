from __future__ import annotations

import hashlib
import random
import re
from dataclasses import dataclass, field

from ..segmenter import split_sentences
from .context_guard import ReplacementGuard, Whitelist, load_whitelist
from .guards import merge_short_runs

SEVERITY_BY_STRENGTH = {
    "light": {"high"},
    "medium": {"high", "medium"},
    "strong": {"high", "medium", "low"},
}

MAX_SENTENCE_LEN = {"light": 95, "medium": 72, "strong": 50}
COMMA_SPLIT_THRESHOLD = {"light": 99, "medium": 4, "strong": 2}

COLLOQUIAL_MARKERS = ["说实话，", "其实，", "说到底，", "有意思的是，", "说白了，"]

_SKIP_MARKER_STARTS = (
    "所以", "因此", "可见", "另外", "同时", "此外", "也就是说", "这样一来",
    "不过", "可是", "但", "而", "其实", "说到底", "说白了", "首先", "其次",
)

_BAD_AFTER_COMMA = (
    "以", "从而", "进而", "因此", "所以", "然而", "但", "以便", "使得", "确保",
    "并且", "而且", "或者", "以及", "及", "和", "与", "为此", "以期", "并",
    "才", "就", "则", "即", "如", "若", "因", "由", "对", "在", "将", "把",
    "成为", "导致", "促进", "推动", "提高", "增加", "降低", "减少", "形成",
    "构成", "体现", "反映", "表明", "显示", "说明", "意味着", "明显", "显著",
    "进一步", "同时", "也", "还", "都", "正", "可", "能", "会", "应", "需",
)

_ZERO_WIDTH = re.compile(r"[\u200b\u200c\u200d\ufeff]")
_BOLD = re.compile(r"\*\*([^*\n]+)\*\*")
_EMOJI = re.compile(
    "[\U0001F1E6-\U0001F1FF\U0001F300-\U0001FAFF\U00002600-\U000027BF"
    "\U0001F900-\U0001F9FF\u2B00-\u2BFF\u2190-\u21FF]"
)
_ASCII_QUOTE = re.compile(r'"([^"\n]{1,40})"')
_LEADING_PUNCT = re.compile(r"^[，,、；;：:\s]+")
_TRAILING_PUNCT = re.compile(r"[，,、；;：:]+$")
_ONLY_PUNCT = re.compile(r"^[。！？；，、\s]+$")

_WHITESPACE_FIX = [
    (re.compile(r"[ \t]+"), " "),
    (re.compile(r"\s+([，。；：！？、）】》])"), r"\1"),
    (re.compile(r"([（【《])\s+"), r"\1"),
    (re.compile(r"([，。；：！？])\1+"), r"\1"),
    (re.compile(r"。{2,}"), "。"),
    (re.compile(r"，{2,}"), "，"),
    (re.compile(r"[，,]\s*。"), "。"),
    (re.compile(r"。\s*[，,]"), "。"),
    (re.compile(r"[，,]\s*；"), "；"),
]


@dataclass
class Rule:
    pattern: str
    replacements: list[str]
    category: str = "lexicon"
    severity: str = "medium"
    replace_mode: str = "all"
    note: str = ""


@dataclass
class RewriteOptions:
    strength: str = "medium"
    style: str = "general"
    person: str = "keep"
    colloquial: int = 20
    deep: bool = False
    extra: dict = field(default_factory=dict)


class RuleEngine:
    def __init__(
        self,
        rules: list[Rule],
        whitelist: Whitelist | None = None,
        guard: ReplacementGuard | None = None,
    ):
        self.rules = rules
        self.whitelist = whitelist or load_whitelist()
        self.guard = guard or ReplacementGuard()
        self.lexicon_rules = sorted(
            [r for r in rules if r.category == "lexicon"],
            key=lambda r: len(r.pattern),
            reverse=True,
        )
        # “对…进行…”必须先于单独的“进行…”执行，否则后者会先吃掉动词。
        self.regex_rules = sorted(
            [r for r in rules if r.category == "regex"],
            key=lambda r: (
                0 if r.pattern.startswith("对(") and "进行" in r.pattern else 1,
                -len(r.pattern),
            ),
        )

    def rewrite(self, text: str, options: RewriteOptions) -> str:
        allowed = SEVERITY_BY_STRENGTH.get(options.strength, {"high", "medium", "low"})
        # 用稳定哈希，避免 Python 进程级哈希随机化导致同样输入结果不同。
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        rng = random.Random(int.from_bytes(digest[:8], "big"))
        max_len = MAX_SENTENCE_LEN.get(options.strength, 75)
        comma_threshold = COMMA_SPLIT_THRESHOLD.get(options.strength, 5)

        result = self._strip_formatting(text)
        for _ in range(3):
            previous = result
            result = self._apply_regex(result, allowed)
            result = self._apply_lexicon(result, allowed, rng)
            result = self._apply_regex(result, allowed)
            result = self._normalize_punctuation(result)
            if result == previous:
                break

        if options.style in {"academic", "official"}:
            academic_len = {"light": 100, "medium": 75, "strong": 60}.get(options.strength, 75)
            result = self._split_long_sentences(result, academic_len, comma_threshold=99)
            if options.deep:
                result = self._split_at_connectives(result)
                result = self._thin_connectives(result)
            result = self._optimize_rhythm(result, target_cv=0.35, max_iter=3)
            # S-02: 降重工具式连续短句在学术语体里是硬信号，合并回正常长度。
            result = merge_short_runs(result)
        else:
            result = self._split_long_sentences(result, max_len, comma_threshold)
            if options.strength == "strong":
                result = self._merge_short_sentences(result)
                result = self._optimize_rhythm(result, target_cv=0.5)
            elif options.strength == "medium":
                result = self._optimize_rhythm(result, target_cv=0.4)
        result = self._apply_person(result, options.person)
        result = self._inject_colloquial(result, options, rng)
        return result.strip()

    def audit(self, text: str, options: RewriteOptions) -> str:
        """Light second pass used after an LLM rewrite."""
        result = self._strip_formatting(text)
        result = self._apply_regex(result, {"high"})
        result = self._normalize_punctuation(result)
        return result.strip()

    def _strip_formatting(self, text: str) -> str:
        text = _ZERO_WIDTH.sub("", text)
        text = _BOLD.sub(r"\1", text)
        text = _EMOJI.sub("", text)
        text = _ASCII_QUOTE.sub(r"“\1”", text)
        if text.count("——") >= 2:
            text = text.replace("——", "，")
        return text

    def _apply_lexicon(self, text: str, allowed: set[str], rng: random.Random) -> str:
        rules = [
            rule
            for rule in self.lexicon_rules
            if rule.severity in allowed and rule.pattern and rule.replacements
        ]
        if not rules:
            return text

        mapping: dict[str, Rule] = {}
        for rule in rules:
            mapping.setdefault(rule.pattern, rule)

        patterns = sorted(mapping.keys(), key=len, reverse=True)
        combined = re.compile("|".join(re.escape(pattern) for pattern in patterns))
        cursors = {
            pattern: rng.randrange(len(mapping[pattern].replacements))
            for pattern in patterns
        }
        hits = {pattern: 0 for pattern in patterns}
        used: dict[str, int] = {}

        def repl(match: re.Match[str]) -> str:
            pattern = match.group(0)
            rule = mapping[pattern]
            index = hits[pattern]
            hits[pattern] += 1
            mode = rule.replace_mode or "all"
            if mode == "first" and index > 0:
                return pattern
            if mode == "alternate" and index % 2 == 1:
                return pattern
            if self.whitelist.is_protected(
                text, match.start(), match.end()
            ) or self.whitelist.review_required(text, match.start(), match.end()):
                # 固定搭配整体保护；需要人工/LLM 判断的语境不做机械替换。
                return pattern
            replacements = rule.replacements
            value = self.guard.pick(replacements, used, cursors[pattern])
            cursors[pattern] += 1
            if value is None:
                return pattern
            used[value] = used.get(value, 0) + 1
            return value

        return combined.sub(repl, text)

    def _apply_regex(self, text: str, allowed: set[str]) -> str:
        for rule in self.regex_rules:
            if rule.severity not in allowed:
                continue
            if not rule.pattern:
                continue
            replacement = rule.replacements[0] if rule.replacements else ""
            try:
                if rule.pattern.startswith("^"):
                    sentences = split_sentences(text)
                    sentences = [
                        self._safe_sub(rule.pattern, replacement, sentence)
                        for sentence in sentences
                    ]
                    text = "".join(sentences)
                else:
                    text = self._safe_sub(
                        rule.pattern, replacement, text, flags=re.MULTILINE
                    )
            except re.error:
                continue
        return text

    def _safe_sub(
        self,
        pattern: str,
        replacement: str,
        text: str,
        flags: int = 0,
    ) -> str:
        def repl(match: re.Match[str]) -> str:
            if self.whitelist.is_protected(
                text, match.start(), match.end()
            ) or self.whitelist.review_required(text, match.start(), match.end()):
                return match.group(0)
            try:
                return match.expand(replacement)
            except (re.error, IndexError):
                return match.group(0)

        return re.sub(pattern, repl, text, flags=flags)

    def _normalize_punctuation(self, text: str) -> str:
        for pattern, repl in _WHITESPACE_FIX:
            text = pattern.sub(repl, text)
        text = _LEADING_PUNCT.sub("", text)
        text = _TRAILING_PUNCT.sub("。", text)
        text = text.strip()
        if _ONLY_PUNCT.match(text):
            return ""
        if text and text[-1] not in "。！？!?":
            text += "。"
        return text

    def _split_long_sentences(self, text: str, max_len: int, comma_threshold: int = 99) -> str:
        if max_len <= 0:
            return text
        sentences = split_sentences(text)
        output: list[str] = []
        for sentence in sentences:
            if len(sentence) > 40 and sentence.count("，") >= comma_threshold:
                output.extend(self._split_one(sentence, min(max_len, 45), depth=0))
            else:
                output.extend(self._split_one(sentence, max_len, depth=0))
        return "".join(output)

    def _split_one(self, sentence: str, max_len: int, depth: int) -> list[str]:
        if depth >= 3 or len(sentence) <= max_len:
            return [sentence]
        candidates = [i for i, ch in enumerate(sentence) if ch in "；;，,"]
        valid: list[int] = []
        for position in candidates:
            if not (12 <= position <= len(sentence) - 12):
                continue
            after = sentence[position + 1 :].lstrip()
            if any(after.startswith(token) for token in _BAD_AFTER_COMMA):
                continue
            valid.append(position)
        if not valid:
            return [sentence]
        target = int(max_len * 0.6)
        pos = min(valid, key=lambda i: abs(i - target))
        left = sentence[:pos] + "。"
        right = sentence[pos + 1 :].lstrip()
        if not right:
            return [sentence]
        return [left] + self._split_one(right, max_len, depth + 1)

    _CONNECTIVE_SPLIT = re.compile(
        r"[，,](?=(?:因此|所以|然而|但是|不过|从而|进而))"
    )
    _LEADING_CONNECTIVE = re.compile(
        r"^(?:因此|所以|然而|但是|不过|从而|进而)(?:[，,、]\s*)?"
    )

    def _split_at_connectives(self, text: str) -> str:
        """把长句里的显式逻辑连接词前置为独立句，改善句长分布。"""
        return self._CONNECTIVE_SPLIT.sub("。", text)

    def _thin_connectives(self, text: str, keep: int = 1) -> str:
        """保留前 keep 个句首连接词，其余删掉，让逻辑从上下文推导。"""
        sentences = [sentence for sentence in split_sentences(text) if sentence.strip()]
        seen = 0
        output: list[str] = []
        for sentence in sentences:
            match = self._LEADING_CONNECTIVE.match(sentence)
            if match:
                if seen < keep:
                    seen += 1
                else:
                    sentence = sentence[match.end() :]
            output.append(sentence)
        return "".join(output)

    def _merge_short_sentences(self, text: str, max_merges: int = 2) -> str:
        sentences = split_sentences(text)
        if len(sentences) < 3:
            return text
        output: list[str] = []
        merges = 0
        index = 0
        while index < len(sentences):
            current = sentences[index]
            if (
                merges < max_merges
                and index + 1 < len(sentences)
                and len(current) <= 14
                and len(sentences[index + 1]) <= 22
                and current.endswith("。")
            ):
                output.append(current[:-1] + "，" + sentences[index + 1])
                merges += 1
                index += 2
            else:
                output.append(current)
                index += 1
        return "".join(output)

    def _rhythm_cv(self, sentences: list[str]) -> float:
        lengths = [len(s) for s in sentences if s.strip()]
        if len(lengths) < 2:
            return 1.0
        mean = sum(lengths) / len(lengths)
        if mean == 0:
            return 1.0
        variance = sum((value - mean) ** 2 for value in lengths) / len(lengths)
        return (variance**0.5) / mean

    def _optimize_rhythm(self, text: str, target_cv: float = 0.45, max_iter: int = 6) -> str:
        sentences = [s for s in split_sentences(text) if s.strip()]
        if len(sentences) < 3:
            return text
        for _ in range(max_iter):
            if self._rhythm_cv(sentences) >= target_cv:
                break
            lengths = [len(s) for s in sentences]
            order = sorted(range(len(sentences)), key=lambda i: lengths[i], reverse=True)
            split_done = False
            for index in order:
                if lengths[index] < 28:
                    break
                parts = self._split_one(sentences[index], max(24, int(lengths[index] * 0.55)), 0)
                if len(parts) > 1:
                    sentences[index : index + 1] = parts
                    split_done = True
                    break
            if not split_done:
                break
        return "".join(sentences)

    def _safe_split(self, sentence: str, target: int) -> tuple[str, str] | None:
        positions = [i for i, ch in enumerate(sentence) if ch in "；;，,"]
        valid: list[int] = []
        for position in positions:
            if not (10 <= position <= len(sentence) - 10):
                continue
            after = sentence[position + 1 :].lstrip()
            if any(after.startswith(token) for token in _BAD_AFTER_COMMA):
                continue
            valid.append(position)
        if not valid:
            return None
        position = min(valid, key=lambda i: abs(i - target))
        left = sentence[:position] + "。"
        right = sentence[position + 1 :].lstrip()
        if not left.strip() or not right.strip():
            return None
        return left, right

    def post_rhythm(self, text: str, target_cv: float = 0.5, max_iter: int = 8) -> str:
        """Greedy rhythm optimizer: pick the split/merge that raises CV the most."""
        sentences = [sentence for sentence in split_sentences(text) if sentence.strip()]
        if len(sentences) < 3:
            return text

        for _ in range(max_iter):
            current_cv = self._rhythm_cv(sentences)
            if current_cv >= target_cv:
                break

            candidates: list[list[str]] = []

            for index in range(len(sentences) - 1):
                if len(sentences[index]) + len(sentences[index + 1]) <= 60:
                    joined = sentences[index][:-1] + "，" + sentences[index + 1]
                    candidates.append(
                        sentences[:index] + [joined] + sentences[index + 2 :]
                    )

            longest = max(range(len(sentences)), key=lambda i: len(sentences[i]))
            length = len(sentences[longest])
            if length >= 30:
                for ratio in (0.3, 0.7):
                    parts = self._safe_split(sentences[longest], int(length * ratio))
                    if parts is not None:
                        candidates.append(
                            sentences[:longest] + list(parts) + sentences[longest + 1 :]
                        )

            if not candidates:
                break

            best = max(candidates, key=self._rhythm_cv)
            best_cv = self._rhythm_cv(best)
            if best_cv <= current_cv + 0.01:
                break
            sentences = best

        return "".join(sentences)

    def _apply_person(self, text: str, person: str) -> str:
        if person == "first":
            return text.replace("我们", "我")
        if person == "third":
            return text.replace("我们", "人们")
        return text

    def _inject_colloquial(self, text: str, options: RewriteOptions, rng: random.Random) -> str:
        if options.colloquial < 50:
            return text
        if options.style not in {"media", "general"}:
            return text
        sentences = split_sentences(text)
        if len(sentences) < 4:
            return text
        indexes = list(range(1, len(sentences)))
        rng.shuffle(indexes)
        count = min(2, max(1, len(sentences) // 5))
        for idx in indexes[:count]:
            sentence = sentences[idx]
            if not sentence or sentence.startswith(tuple(COLLOQUIAL_MARKERS)):
                continue
            if sentence.startswith(_SKIP_MARKER_STARTS):
                continue
            marker = COLLOQUIAL_MARKERS[rng.randrange(len(COLLOQUIAL_MARKERS))]
            sentences[idx] = marker + sentence
        return "".join(sentences)
