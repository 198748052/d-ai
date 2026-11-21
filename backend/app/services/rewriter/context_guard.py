from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from ...core.config import APP_DIR

DATA_DIR = APP_DIR / "data"
WHITELIST_PATH = DATA_DIR / "context_whitelist.json"
BLACKLIST_PATH = DATA_DIR / "replacement_blacklist.json"


@dataclass
class WhitelistEntry:
    id: str
    rule_ids: set[str]
    trigger: str
    literals: list[str]
    matcher: re.Pattern[str] | None
    disposition: str


@dataclass
class Whitelist:
    """Fixed collocations that must survive mechanical replacement."""

    entries: list[WhitelistEntry] = field(default_factory=list)
    literals: list[str] = field(default_factory=list)

    @classmethod
    def load(cls, path: Path | None = None) -> "Whitelist":
        target = path or WHITELIST_PATH
        try:
            data = json.loads(target.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return cls()
        entries: list[WhitelistEntry] = []
        literals: list[str] = []
        for item in data.get("entries", []):
            try:
                matcher = re.compile(item["matcher"]) if item.get("matcher") else None
            except re.error:
                matcher = None
            item_literals = [str(value) for value in item.get("literals", []) if value]
            disposition = str(item.get("disposition", "whitelisted"))
            if disposition == "whitelisted":
                literals.extend(item_literals)
            entries.append(
                WhitelistEntry(
                    id=str(item.get("id", "")),
                    rule_ids={str(value) for value in item.get("rule_ids", [])},
                    trigger=str(item.get("trigger", "")),
                    literals=item_literals,
                    matcher=matcher,
                    disposition=disposition,
                )
            )
        # Longest first so that nested terms are masked before their parents.
        literals = sorted(dict.fromkeys(literals), key=len, reverse=True)
        return cls(entries=entries, literals=literals)

    def protect_terms(self) -> list[str]:
        return list(self.literals)

    def is_protected(self, text: str, start: int, end: int, rule_id: str | None = None) -> bool:
        matched = text[start:end]
        for entry in self.entries:
            if entry.disposition != "whitelisted":
                continue
            if rule_id and entry.rule_ids and rule_id not in entry.rule_ids:
                continue
            if entry.trigger and entry.trigger not in matched:
                continue
            if entry.matcher is None:
                continue
            for context in entry.matcher.finditer(text):
                if context.start() <= start and end <= context.end():
                    return True
        return False

    def review_required(self, text: str, start: int, end: int) -> bool:
        matched = text[start:end]
        for entry in self.entries:
            if entry.disposition != "review" or entry.matcher is None:
                continue
            if entry.trigger and entry.trigger not in matched:
                continue
            for context in entry.matcher.finditer(text):
                if context.start() <= start and end <= context.end():
                    return True
        return False


@dataclass
class ReplacementBlacklist:
    hard_banned: set[str] = field(default_factory=set)
    discouraged: set[str] = field(default_factory=set)
    pools: dict[str, list[str]] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path | None = None) -> "ReplacementBlacklist":
        target = path or BLACKLIST_PATH
        try:
            data = json.loads(target.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return cls()
        discouraged = {
            str(item.get("product", ""))
            for item in data.get("discouraged", [])
            if item.get("product")
        }
        pools: dict[str, list[str]] = {}
        for trigger, pool in (data.get("context_pools") or {}).items():
            values: list[str] = []
            for key, items in pool.items():
                if key == "forbidden":
                    continue
                values.extend(str(value) for value in items if value)
            if values:
                pools[trigger] = list(dict.fromkeys(values))
        return cls(
            hard_banned={str(item) for item in data.get("hard_banned", []) if item},
            discouraged=discouraged,
            pools=pools,
        )

    def is_banned(self, value: str) -> bool:
        # Empty string is a valid deletion replacement, not a banned product.
        text = (value or "").strip()
        if not text:
            return False
        if text in self.hard_banned:
            return True
        return any(item and item in text for item in self.hard_banned)

    def pool_for(self, trigger: str) -> list[str]:
        return list(self.pools.get(trigger, []))


@lru_cache(maxsize=1)
def load_whitelist() -> Whitelist:
    return Whitelist.load()


@lru_cache(maxsize=1)
def load_blacklist() -> ReplacementBlacklist:
    return ReplacementBlacklist.load()


class ReplacementGuard:
    """Chooses replacements that are neither banned nor mechanically repeated."""

    def __init__(self, blacklist: ReplacementBlacklist | None = None, max_reuse: int = 2):
        self.blacklist = blacklist or load_blacklist()
        self.max_reuse = max(1, max_reuse)

    def pick(
        self,
        replacements: list[str],
        used: dict[str, int],
        start_index: int = 0,
    ) -> str | None:
        candidates = [str(item) for item in replacements if isinstance(item, str)]
        if not candidates:
            return None
        for offset in range(len(candidates)):
            value = candidates[(start_index + offset) % len(candidates)]
            if self.blacklist.is_banned(value):
                continue
            if used.get(value, 0) >= self.max_reuse:
                continue
            return value
        # Everything is either banned or overused; keep the least-used safe option.
        safe = [value for value in candidates if not self.blacklist.is_banned(value)]
        if safe:
            return min(safe, key=lambda value: used.get(value, 0))
        return None
