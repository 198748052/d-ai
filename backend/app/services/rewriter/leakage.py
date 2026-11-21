from __future__ import annotations

import re
from dataclasses import dataclass

"""Stage 4: chain-of-thought, UI residue and agent trace scrubbing.

过程痕迹对读者信息量为零，命中即清。规则来源：
- evidence-based-humanizer/humanizer-zh/assets/zh-thinking-leakage.md (X1-X8)
- AI-Text-Anti-Detection-Framework 的 AFTER 二次扫描要求
"""


@dataclass(frozen=True)
class LeakageRule:
    id: str
    category: str
    pattern: re.Pattern[str]
    note: str


RULES: list[LeakageRule] = [
    LeakageRule(
        "X1",
        "推理自我修正",
        re.compile(
            r"(?i)(?:^|[。！？；\s])(?:wait|hmm)[，,。!！]\s*"
            r"|等等[，,]\s*让我"
            r"|让我(?:再)?想(?:一)?想"
            r"|我重新(?:看|审视)了一下"
            r"|刚才(?:说的|讲得?)(?:不对|有误)"
            r"|让我重新组织"
            r"|aha moment"
        ),
        "推理过程中的自我修正混入正文",
    ),
    LeakageRule(
        "X2",
        "UI 残留",
        re.compile(
            r"已深度思考[（(]用时[^）)]{1,16}[）)]"
            r"|(?:深度)?思考用时[^。！？\n]{0,12}"
            r"|已思考[（(][^）)]{0,16}[）)]"
            r"|思考完毕"
            r"|(?i:thought for \d+(?:\.\d+)?\s*(?:seconds?|s))"
        ),
        "产品界面上的思考摘要被复制进正文",
    ),
    LeakageRule(
        "X3",
        "agent 过程独白",
        re.compile(
            r"我现在(?:将|开始|来)"
            r"|接下来我将"
            r"|让我(?:们)?(?:先|来|一步步)"
            r"|接下来(?:我们)?(?:来|将)"
            r"|我(?:首先|然后|最后)(?:来|将|做)"
        ),
        "会话式过程叙述写进交付正文",
    ),
    LeakageRule(
        "X4",
        "任务清单残留",
        re.compile(r"(?m)^\s*[-*+]\s*\[[ xX]\]\s*"),
        "agent 的 checkbox 工作记忆混入正文",
    ),
    LeakageRule(
        "X5",
        "自用图表",
        re.compile(r"(?is)```mermaid[\s\S]*?```"),
        "给自己组织思路用的 Mermaid 图被当成插图",
    ),
    LeakageRule(
        "X7",
        "讨好型元话语",
        re.compile(
            r"好的[，,]\s*下面是"
            r"|当然可以[，,。]"
            r"|这是一个(?:非常)?好(?:的)?问题"
            r"|你刚刚那句话"
            r"|我帮你轻轻(?:拧|改)一下"
            r"|希望(?:这|以上内容)?(?:对|能对)(?:您|你)(?:有所)?帮助"
        ),
        "对话中的讨好与预告残留",
    ),
    LeakageRule(
        "X8",
        "内心戏残留",
        re.compile(
            r"我先去吃饭了"
            r"|蓝色大肥鱼"
            r"|偷偷(?:给|和)(?:用户|你)(?:取|起)(?:了)?(?:个)?外号"
        ),
        "模型草稿纸式内心戏被当成正文",
    ),
]

_CODE_FENCE = re.compile(r"(?is)```.*?```")
_NARRATIVE_COMMENT = re.compile(
    r"(?m)^(\s*(?://|#)\s*)(?:现在|接下来|这里我们|我们先|首先|如前所述|上次|修复了|改了)[^\n]*$"
)


def scan(text: str) -> list[dict]:
    hits: list[dict] = []
    if not text:
        return hits
    for rule in RULES:
        matches = list(rule.pattern.finditer(text))
        if not matches:
            continue
        hits.append(
            {
                "id": rule.id,
                "category": rule.category,
                "count": len(matches),
                "matched": matches[0].group(0).strip()[:40],
                "note": rule.note,
            }
        )
    return hits


def _clean_code_comments(text: str) -> str:
    def repl(match: re.Match[str]) -> str:
        block = match.group(0)
        return _NARRATIVE_COMMENT.sub("", block)

    return _CODE_FENCE.sub(repl, text)


def clean(text: str) -> tuple[str, list[dict]]:
    """Remove process traces. Returns (cleaned_text, hits)."""
    if not text:
        return text, []
    hits = scan(text)
    if not hits:
        return text, []

    result = text
    for rule in RULES:
        result = rule.pattern.sub("", result)
    result = _clean_code_comments(result)
    result = re.sub(r"[ \t]{2,}", " ", result)
    result = re.sub(r"\n{3,}", "\n\n", result)
    return result.strip(), hits
