from __future__ import annotations

import asyncio
import logging
import re
import time
from dataclasses import dataclass

import httpx

from ...core.config import FIXED_REASONING_EFFORT
from ...core.crypto import decrypt
from ...models.models import LLMSetting
from .content import fact_lines
from .timing import add_llm

_PREFIX_RE = re.compile(r"^\s*(改写后|改写结果|润色后|输出)[:：]\s*")
_QUOTE_PAIRS = [("“", "”"), ('"', '"'), ("「", "」"), ("『", "』")]
_PLACEHOLDER_RE = re.compile(r"⟦([A-Z]+)⟧")

logger = logging.getLogger(__name__)

REWRITE_AVOID_RULES = [
    "- 不要只替换同义词或近义词，必须改变句法结构。",
    "- 不要使用套话和模板句式，例如“值得注意的是”“综上所述”“由此可见”“首先/其次/最后”“随着……的推进”“在……背景下”。",
    "- 不要堆砌连接词（此外、与此同时、因此、然而），也不要连续使用四字并列短语。",
    "- 不要为了制造节奏把句子拆成缺主语的残句，也不要让连续多句使用相同开头。",
    "- 不要新增或改动原文的事实、数字、引用、案例和结论。",
    "- 不要重复上一句的意思来凑长度。",
]

STYLE_LABEL = {
    "general": "通用书面语",
    "academic": "学术论文语体，正式、严谨、克制",
    "media": "公众号/自媒体语体，自然、有节奏、可略带口语",
    "fiction": "小说叙事语体，具体、有画面感",
    "official": "商务公文语体，规范、简洁",
}

STRENGTH_LABEL = {
    "light": "轻度：只调整明显模板化的词句，尽量保留原句结构",
    "medium": "中度：打散模板句式，替换套话，长短句交错",
    "strong": "重度：大幅重构句式和语序，保留信息点即可",
}


class LLMError(Exception):
    pass


@dataclass
class LLMContext:
    style: str = "general"
    strength: str = "medium"
    person: str = "keep"
    colloquial: int = 20
    length_ratio_min: float = 0.85
    length_ratio_max: float = 1.15
    banned_words: list[str] = None
    extra_prompt: str = ""
    lessons: list[str] = None
    issues: list[str] = None
    plan: list[dict] = None
    content_facts: list[dict] = None
    deep_rewrite: bool = True
    rewrite_headings: bool = False

    def __post_init__(self) -> None:
        if self.banned_words is None:
            self.banned_words = []
        if self.lessons is None:
            self.lessons = []
        if self.issues is None:
            self.issues = []
        if self.plan is None:
            self.plan = []
        if self.content_facts is None:
            self.content_facts = []


class LLMEngine:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        temperature: float = 1.2,
        max_tokens: int = 4096,
        timeout: int = 120,
        reasoning_effort: str = FIXED_REASONING_EFFORT,
    ):
        self.base_url = (base_url or "").rstrip("/")
        self.api_key = api_key or ""
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout
        self.reasoning_effort = (
            reasoning_effort
            if reasoning_effort in {"low", "medium", "high"}
            else FIXED_REASONING_EFFORT
        )
        self._effort_supported = True

    @classmethod
    def from_setting(cls, setting: LLMSetting) -> "LLMEngine":
        return cls(
            base_url=setting.base_url,
            api_key=decrypt(setting.api_key_enc),
            model=setting.model,
            temperature=setting.temperature,
            max_tokens=setting.max_tokens,
            timeout=setting.timeout,
            reasoning_effort=FIXED_REASONING_EFFORT,
        )

    @property
    def configured(self) -> bool:
        return bool(self.api_key and self.base_url and self.model)

    async def _chat(
        self,
        messages: list[dict],
        temperature: float | None = None,
        max_tokens: int | None = None,
        reasoning_effort: str | None = None,
    ) -> str:
        started = time.perf_counter()
        try:
            return await self._chat_impl(
                messages,
                temperature=temperature,
                max_tokens=max_tokens,
                reasoning_effort=reasoning_effort,
            )
        finally:
            add_llm(time.perf_counter() - started)

    async def _chat_impl(
        self,
        messages: list[dict],
        temperature: float | None = None,
        max_tokens: int | None = None,
        reasoning_effort: str | None = None,
    ) -> str:
        if not self.configured:
            raise LLMError("LLM 未配置，请先在设置页填写 Base URL、模型和 API Key")
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        base_temperature = self.temperature if temperature is None else temperature
        budget = max_tokens or self.max_tokens
        last_error: Exception | None = None
        for attempt in range(3):
            payload = {
                "model": self.model,
                "messages": messages,
                "temperature": min(1.6, base_temperature + 0.15 * attempt),
                "max_tokens": budget,
            }
            if self._effort_supported:
                payload["reasoning_effort"] = reasoning_effort or self.reasoning_effort
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    resp = await client.post(url, headers=headers, json=payload)
                    if (
                        resp.status_code == 400
                        and self._effort_supported
                        and "reasoning_effort" in resp.text
                    ):
                        self._effort_supported = False
                        payload.pop("reasoning_effort", None)
                        resp = await client.post(url, headers=headers, json=payload)
                if resp.status_code >= 400:
                    if resp.status_code == 400 and "max_tokens" in resp.text and budget > self.max_tokens:
                        budget = self.max_tokens
                    raise LLMError(f"LLM 返回 {resp.status_code}: {resp.text[:300]}")
                data = resp.json()
                choice = data["choices"][0]
                message = choice.get("message") or {}
                content = message.get("content") or ""
                finish_reason = choice.get("finish_reason")
                if not content.strip():
                    if finish_reason == "length":
                        logger.warning(
                            "LLM output truncated at max_tokens=%s, raising budget",
                            budget,
                        )
                        budget = min(budget * 2, 16384)
                        if max_tokens is None:
                            self.max_tokens = max(self.max_tokens, budget)
                        raise LLMError(
                            f"LLM 输出被截断（finish_reason=length，max_tokens={payload['max_tokens']}）"
                        )
                    raise LLMError("LLM 返回空内容")
                return content
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                logger.warning("LLM attempt %s failed: %s", attempt + 1, str(exc)[:200])
                if attempt < 2:
                    await asyncio.sleep(2 * (attempt + 1))
        raise LLMError(str(last_error) if last_error else "LLM 调用失败")

    async def rewrite_paragraph(
        self,
        masked_text: str,
        ctx: LLMContext,
        round_index: int = 0,
        hits: list[dict] | None = None,
        context: str | None = None,
        temperature: float | None = None,
    ) -> str:
        messages = [
            {
                "role": "system",
                "content": self._build_system_prompt(ctx, round_index, hits, context),
            },
            {"role": "user", "content": masked_text},
        ]
        if temperature is None:
            temperature = 1.3 if ctx.style in {"academic", "official"} else None
        raw = await self._chat(messages, temperature=temperature)
        cleaned = self._postprocess(raw)
        if not cleaned:
            raise LLMError("LLM 返回内容为空")
        return cleaned

    async def rewrite_document(
        self,
        masked_text: str,
        ctx: LLMContext,
        hits: list[dict] | None = None,
        context: str | None = None,
    ) -> str:
        lines = [
            "你是学术论文编辑。下面是一整篇论文，请做整篇改写，降低机器生成特征。",
            "必须遵守：",
            "1. 保持段落数量、顺序、序号和分点层次不变。",
            "2. 事实、数据、术语、变量名、引用、公式、结论保持不变。",
            "3. 原样保留所有形如 ⟦A⟧ ⟦B⟧ 的占位符，编号与位置对应。",
            "4. 只输出正文，段落之间用空行分隔，不要解释、不要编号、不要引号。",
            "5. 允许调整句内信息顺序、主被动和从句边界；不要新增原文没有的事实、数字、案例、引用。",
            "6. 长短句交错，避免连续三句长度接近；保留学术语体。",
            "7. 每一段每一句都要重写，不得原样保留任何一句。",
        ]
        lines.append(
            "- 标题措辞可以改写，但序号和编号格式必须保持不变。"
            if ctx.rewrite_headings
            else "- 标题必须原样保留，不要改动标题措辞。"
        )
        if ctx.deep_rewrite:
            lines.extend(
                [
                    "7. 深度改写：改变信息顺序和句法结构，删除显式因果连接词，让语义自然衔接。",
                ]
            )
        if ctx.content_facts:
            lines.extend(
                [
                    "",
                    "用户补充的事实（只能使用这些，禁止编造）：",
                    fact_lines(ctx.content_facts),
                ]
            )
        if hits:
            lines.extend(
                [
                    "",
                    "全文命中的 AI 特征（必须逐条清除）：",
                    self._format_hits(hits),
                ]
            )
        messages = [
            {"role": "system", "content": "\n".join(lines)},
            {"role": "user", "content": masked_text},
        ]
        raw = await self._chat(messages, temperature=1.2, max_tokens=8192)
        return self._postprocess_document(raw)

    def _postprocess_document(self, raw: str) -> str:
        text = (raw or "").strip()
        text = re.sub(r"^\s*(?:改写后|改写结果|输出)[:：]\s*", "", text)
        text = re.sub(r"\*\*([^*\n]+)\*\*", r"\1", text)
        text = re.sub(r"[\u200b\u200c\u200d\ufeff]", "", text)
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    async def adjust_rhythm(
        self,
        text: str,
        metrics: dict,
        ctx: LLMContext,
        issues: list[str] | None = None,
    ) -> str:
        sentences = [item for item in re.split(r"(?<=[。！？!?；;…])", text) if item.strip()]
        lengths = [len(item) for item in sentences]
        listing = "\n".join(
            f"{index + 1}. [{lengths[index]}字] {sentences[index][:50]}"
            for index in range(len(sentences))
        )
        system = (
            "你是文字编辑。下面这段文字的句子长度过于接近，机器感偏重。\n"
            f"当前句长变异系数 CV={metrics.get('cv')}，目标是落在 0.45 到 0.6 之间。\n"
            "请只调整句子边界和长度，不改事实、顺序、术语、数据、引用和占位符。\n"
            "要求：\n"
            "- 把最长的一句拆成两句；\n"
            "- 把最短的两句合并成一句；\n"
            "- 调整后至少一句超过 40 字，至少一句少于 15 字；\n"
            "- 如果当前 CV 高于 0.6，合并部分短句或拆分过长句，把 CV 降到 0.6 以下；\n"
            "- 如果当前 CV 低于 0.45，拆开长句或合并短句，把 CV 提到 0.45 以上；\n"
            "- 拆分后每句要有完整的主谓结构，避免残句；\n"
            "- 只输出修改后的正文，不要解释、不要换行、不要编号。\n"
            "句子清单：\n"
            f"{listing}"
            + (
                "\n本段还存在以下问题，请一并修正：\n"
                + "\n".join(f"- {item}" for item in issues)
                if issues
                else ""
            )
        )
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": text},
        ]
        raw = await self._chat(messages, temperature=1.1, reasoning_effort="low")
        cleaned = self._postprocess(raw)
        if not cleaned:
            raise LLMError("LLM 返回内容为空")
        return cleaned

    async def correct_paragraph(
        self,
        text: str,
        hits: list[dict],
        ctx: LLMContext,
        context: str | None = None,
    ) -> str:
        messages = [
            {
                "role": "system",
                "content": self._build_correction_prompt(ctx, hits, context),
            },
            {"role": "user", "content": text},
        ]
        raw = await self._chat(messages, temperature=0.9)
        cleaned = self._postprocess(raw)
        if not cleaned:
            raise LLMError("LLM 返回内容为空")
        return cleaned

    async def integrate_facts(
        self,
        text: str,
        facts: list[dict],
        ctx: LLMContext,
    ) -> str:
        lines = [
            "你是审稿编辑。下面这段文字没有使用用户补充的事实。",
            "请把下列事实自然融入正文，保持原有论证顺序、术语、数字、引用和段落结构。",
            "只能使用用户提供的事实，禁止编造新的数字、引用、案例。",
            "只输出修改后的正文，不要解释、不要编号、不要换行。",
            "",
            "用户补充的事实：",
            fact_lines(facts),
        ]
        messages = [
            {"role": "system", "content": "\n".join(lines)},
            {"role": "user", "content": text},
        ]
        raw = await self._chat(messages, temperature=1.0)
        cleaned = self._postprocess(raw)
        if not cleaned:
            raise LLMError("LLM 返回内容为空")
        return cleaned

    async def ping(self) -> int:
        import time

        start = time.perf_counter()
        await self._chat(
            [{"role": "user", "content": "回复两个字：正常"}],
            temperature=0,
            reasoning_effort="low",
        )
        return int((time.perf_counter() - start) * 1000)

    def _build_system_prompt(
        self,
        ctx: LLMContext,
        round_index: int = 0,
        hits: list[dict] | None = None,
        context: str | None = None,
    ) -> str:
        if ctx.style in {"academic", "official"}:
            return self._build_academic_prompt(ctx, round_index, hits, context)
        return self._build_general_prompt(ctx, round_index, hits, context)

    @staticmethod
    def _format_hits(hits: list[dict]) -> str:
        lines: list[str] = []
        for index, hit in enumerate(hits[:20], 1):
            matched = str(hit.get("matched") or hit.get("pattern") or "").strip()
            if hit.get("category") == "lexicon":
                replacements = [str(item) for item in hit.get("replacements", []) if str(item)]
                if replacements:
                    action = "替换为：" + " / ".join(replacements[:3])
                else:
                    action = "删除该表达"
            else:
                action = f"改写该句式，避免同类模板（{hit.get('note') or '模板句式'}）"
            lines.append(f"{index}. 「{matched}」——{action}")
        return "\n".join(lines)

    def _append_constraints(
        self,
        lines: list[str],
        hits: list[dict] | None,
        context: str | None,
    ) -> None:
        if context:
            lines.extend(["", "整段上下文（仅供理解，不要输出）：", context])
        if hits:
            lines.extend(
                [
                    "",
                    "本片段命中的 AI 特征（必须逐条清除，输出中不得再出现）：",
                    self._format_hits(hits),
                    "",
                    "改写完成后自查：上述每一条是否都已消失。",
                ]
            )

    @staticmethod
    def _append_lessons(lines: list[str], ctx: LLMContext) -> None:
        if not ctx.lessons:
            return
        selected: list[str] = []
        total_chars = 0
        for item in ctx.lessons:
            if len(selected) >= 50 or total_chars + len(item) > 5000:
                break
            selected.append(item)
            total_chars += len(item)
        if not selected:
            return
        lines.extend(
            [
                "",
                "以下句式是本地困惑度检测不合格的禁用模板，输出中不得使用这些句式，也不得只替换同义词；必须改变句法结构和信息组织：",
                *[f"- [禁用] {item}" for item in selected],
                "如果某个禁用模板无法避开，必须换用不同的句法结构，而不是换几个词。",
            ]
        )

    @staticmethod
    def _append_diagnosis(lines: list[str], ctx: LLMContext) -> None:
        if ctx.plan:
            lines.extend(["", "本轮修改计划（按优先级，先处理前面的）："])
            for item in ctx.plan[:10]:
                lines.append(
                    f"- [{item.get('code')}] {item.get('label')}：{item.get('action')}"
                )
        if ctx.issues:
            lines.extend(
                [
                    "",
                    "本段诊断出的具体问题：",
                    *[f"- {item}" for item in ctx.issues[:8]],
                ]
            )

    @staticmethod
    def _append_content(lines: list[str], ctx: LLMContext) -> None:
        if not ctx.content_facts:
            return
        lines.extend(
            [
                "",
                "用户补充的事实（只能使用这些，禁止编造新的数字、引用、案例）：",
                fact_lines(ctx.content_facts),
                "",
                "内容注入要求：",
                "- 把用户提供的事实自然写进对应段落，保持原有论证顺序。",
                "- 数字、样本量、实验条件、引用、案例必须与用户提供的内容完全一致。",
                "- 用户没有提供的具体信息，保持原文的概括程度，不要自行补全。",
            ]
        )

    async def rewrite_low_perplexity(
        self,
        text: str,
        flagged: list[dict],
        ctx: LLMContext,
        attempt: int = 0,
        max_attempts: int = 0,
        threshold: float = 45.0,
        severe_threshold: float | None = None,
        previous: list[dict] | None = None,
    ) -> str:
        lines = [
            "你是审稿编辑。系统用本地困惑度模型检测了这段文字，发现部分句子过于可预测，读起来像模板拼出来的。",
            f"触发原因：下列句子的困惑度低于阈值 {threshold:g}，分数越低越像机器生成，需要针对性重写。",
        ]
        if attempt > 0:
            lines.append(
                f"这是第 {attempt + 1} 轮重写（最多 {max_attempts + 1} 轮）。"
                "上一轮改写后这些句子仍然偏可预测，说明只换同义词或小修小补无效，"
                "必须改变句法结构和信息组织方式。"
            )
        else:
            lines.append("这是首次针对性重写。")
        lines.extend(
            [
                "",
                "重写目标：",
                "- 换具体说法、调整语序、拆分或合并句子、补充限定条件或细节，让句子更像真人写的。",
                "- 整段一起重写，重点处理下面列出的低分句；原意、术语、数据、引用、占位符和段落结构保持不变。",
                "- 改写后整段长度与原文接近（±15% 以内），不要扩写，不要新增原文没有的信息。",
                "- 只输出整段正文，不要解释、不要编号、不要换行。",
                "",
                "避雷清单（违反任意一条都算失败）：",
                *REWRITE_AVOID_RULES,
                "- 不要沿用上一轮已经被判定为低困惑度的写法。",
                "",
                "必须重写的低困惑度句子（分数越低越严重）：",
            ]
        )
        for index, item in enumerate(flagged[:10], 1):
            score = item.get("perplexity")
            severe = (
                severe_threshold is not None
                and score is not None
                and float(score) < severe_threshold
            )
            suffix = "，严重偏低" if severe else ""
            lines.append(f"{index}. 「{item['sentence']}」（困惑度 {score}，阈值 {threshold:g}{suffix}）")
        if previous:
            lines.extend(
                [
                    "",
                    "上一轮改写后仍然低困惑度的句子（这些写法无效，必须避开类似结构）：",
                ]
            )
            for item in previous[:10]:
                lines.append(
                    f"- 「{item.get('sentence', '')}」（困惑度 {item.get('perplexity')}）"
                )
        self._append_lessons(lines, ctx)
        messages = [
            {"role": "system", "content": "\n".join(lines)},
            {"role": "user", "content": text},
        ]
        raw = await self._chat(messages, temperature=1.35)
        cleaned = self._postprocess(raw)
        if not cleaned:
            raise LLMError("LLM 返回内容为空")
        return cleaned

    async def rewrite_unchanged(
        self,
        text: str,
        untouched: list[str],
        ctx: LLMContext,
        context: str | None = None,
    ) -> str:
        """Rewrite a paragraph again when some sentences were left untouched."""
        lines = [
            "你是审稿编辑。下面这段文字整体仍偏机器生成，其中一些句子几乎没有改动。",
            "触发原因：这些句子在上一轮改写中几乎原样保留，说明改写力度不足。",
            "请整段重写：每一句都要换一种说法，不得原样保留任何一句。",
            "保持原意、术语、数据、引用、占位符和段落结构不变，不要新增原文没有的信息。",
            "只输出整段正文，不要解释、不要编号、不要换行。",
            "",
            "避雷清单（违反任意一条都算失败）：",
            *REWRITE_AVOID_RULES,
            "",
            "必须改写的句子：",
        ]
        for index, sentence in enumerate(untouched[:10], 1):
            lines.append(f"{index}. 「{sentence}」")
        self._append_lessons(lines, ctx)
        if context:
            lines.extend(["", "整段上下文（仅供理解，不要输出）：", context])
        messages = [
            {"role": "system", "content": "\n".join(lines)},
            {"role": "user", "content": text},
        ]
        raw = await self._chat(messages, temperature=1.45)
        cleaned = self._postprocess(raw)
        if not cleaned:
            raise LLMError("LLM 返回内容为空")
        return cleaned

    def _build_correction_prompt(
        self,
        ctx: LLMContext,
        hits: list[dict],
        context: str | None = None,
    ) -> str:
        lines = [
            "你是审稿编辑。下面这段文字已经改写过，但仍残留以下 AI 特征。",
            "请逐条清除这些残留，保持原意、术语、数据、引用、占位符和段落结构不变。",
            "只输出修改后的正文，不要解释、不要引号、不要换行。",
            "",
            "残留的 AI 特征（必须全部清除）：",
            self._format_hits(hits),
        ]
        if context:
            lines.extend(["", "整段上下文（仅供理解，不要输出）：", context])
        lines.append("")
        lines.append(f"改写强度：{STRENGTH_LABEL.get(ctx.strength, STRENGTH_LABEL['medium'])}")
        return "\n".join(lines)

    def _build_academic_prompt(
        self,
        ctx: LLMContext,
        round_index: int = 0,
        hits: list[dict] | None = None,
        context: str | None = None,
    ) -> str:
        strength = STRENGTH_LABEL.get(ctx.strength, STRENGTH_LABEL["medium"])
        banned = "、".join(ctx.banned_words) if ctx.banned_words else "无"
        header = (
            "你是审稿人。下面这段论文文字已经改过一轮，仍可能残留机器生成特征。请做第二轮修订。"
            if round_index > 0
            else "你是一位有十年论文写作经验的研究者，文字有自己的节奏和判断，不追求完美工整。任务：修改用户给出的论文段落，降低机器生成特征，同时保持原意和段落结构。"
        )
        lines = [
            header,
            "",
            "必须遵守：",
            "- 整段每一句都要重写，不得原样保留任何一句；不要只替换命中清单里的词。",
            "1. 一段进，一段出。不拆分、不合并、不加标题或列表。",
            "2. 事实、数据、术语、变量名、引用、公式、结论保持不变。",
            "3. 原样保留所有形如 ⟦A⟧ ⟦B⟧ 的占位符，编号与位置都要对应。",
            "4. 只输出正文，不要解释、不要引号、不要换行。",
            "5. 保持学术语体，但允许自然的书面口语连接和适度冗余；不要过度润色，不要把所有句子都改成工整的短句。",
            "",
            "结构要求：",
            "- 原文中的序号（第一、第二、1.、2.、（一）（二））和编号格式必须原样保留。",
            "- 保留原文的分点层次和段落内部顺序。",
            "",
            "需要清除的机器特征（按优先级）：",
            "- 硬信号（出现即改）：赋能/抓手/闭环/链路/沉淀/对齐/颗粒度/底层逻辑/范式/组合拳/生态/壁垒/深耕；全面提升/深度融合/扎实推进/持续优化；必将/未来可期/大有可为/任重道远；双刃剑。",
            "- 模板连接词：首先/其次/再次/最后/综上所述/由此可见/值得注意的是/需要指出的是/基于此/在此背景下/与此同时/一方面/另一方面。",
            "- 空泛评价：具有重要意义/发挥重要作用/奠定坚实基础/提供有力支撑/取得显著成效/注入新动能/开辟新路径。",
            "- 抽象名词：高度/角度/层面/维度/方面/领域/范畴/视野/格局/站位；系统化/精细化/可视化/常态化/体系化。",
            "- 名词化堆叠：对…进行…/进行…/做出…/给予…/开展…/实现…的提升/使…得到…。",
            "- 长定语名词串：…的…的…的…；一句连缀两个以上四字词；连续四个以上顿号并列。",
            "- 流水线动宾：研究了X，明确了Y，揭示了Z。",
            "- 对称句式：不仅…而且…/不仅X更Y/既…又…/一方面…另一方面…/不是…而是…。",
            "- 主语缺失：连续多句无主语；连续用“它”指代；连续句子以“…的”收尾。",
            "- 语体错位：抒情腔（星辰/温柔/治愈/涟漪/瞳仁/稳稳地接住）、意义拔高、无引注的“研究表明/数据显示”。",
            "- 过程痕迹：让我想想/等等/已深度思考（用时X秒）/我现在将/接下来我来/任务清单 checkbox/Mermaid 自用图/讨好型元话语。",
            "",
            "句法结构层（词汇清完后再处理）：",
            "- 句长过于均匀：主动制造长短差异，但不要周期性长短交替。",
            "- 连续三句都是 12 字以内短句：合并其中一两句，保留一个短句作强调。",
            "- 单句超过 60 字且逗号分句超过 5 个：在语义切换点断句。",
            "- 三层以上“的”字定语链：拆成动词短语或短句。",
            "- 被字句过多：改主动语态或无主语句。",
            "- 段落开头连续三段同一种句式：改变其中两段。",
            "",
            "弱信号处理原则：",
            "- 对比复句、递进复句、排比、破折号是汉语规范修辞，人类也用；罪在过密不在使用。",
            "- 同一弱信号在一段里出现两次以上才处理；保留最有信息量的一处，改写其余，不要清零。",
            "- 打破默认不等于替换默认：禁止把“删排比”做成“逢三拆二”，把“删套话”做成“逢句插口语词”。",
            "",
            "反过拟合红线：",
            "- 不要为了制造人味而连续堆短句，也不要把每句都改成口语。",
            "- 不要每段都用同一种“具体化”套路；改写动作本身会引入新的 AI 味。",
            "- 不新增原文没有的事实、数字、案例、引用；需要具体细节时只能把原文已有的信息写实。",
            "- 禁用替换产物：不只仅/另先看/再往下/到这里/协作体系环境/完整流程的响应机制/提升者。",
            "",
            "全局禁用表达（输出中不得出现）：首先、其次、再次、最后、综上所述、总而言之、由此可见、值得注意的是、需要指出的是、基于此、在此背景下、赋能、抓手、闭环、链路、沉淀、对齐、颗粒度、底层逻辑、范式、维度、组合拳、具有重要意义、发挥重要作用、奠定坚实基础、提供有力支撑、注入新动能、开辟新路径",
            "",
            "改写方法：",
            "- 句子长度要有明显差异：允许保留较长的复句，短句只在合适的地方出现，避免每句都压成短句。",
            "- 主动句、被动句、把字句交替；每段至少改变两处语序。",
            "- 拆名词串：把多层“的”拆成短句，或改用“对/关于/在…中”。",
            "- 补主语：适当使用“本文/本研究/笔者/该模型/这一过程”。",
            "- 因果倒装：因为A所以B → B，其原因在于A。",
            "- 条件/让步转换：如果A就B → 当A时，B；虽然A但B → A，但B。",
            "- 判断句转换：X是Y的重要体现 → X体现了Y。",
            "- 增加限定语：在…条件下/就…而言/在一定程度上（每段1-2处）。",
            "- 保持克制：不使用“非常/特别/极其”等口语强调。",
            "",
            *(
                [
                    "",
                    "深度改写要求（本轮启用）：",
                    "- 改变信息顺序：把结论前置或后置，调整从句顺序，避免只做同义替换。",
                    "- 主动句、被动句、把字句、无主句交替，避免连续同一种句式。",
                    "- 删除显式逻辑连接词：因此/然而/此外/同时/从而/进而，让语义自然衔接。",
                    "- 长句在语义切换点断开，短句只在强调处出现。",
                    "- 改写后句子结构要变，信息点、数字、引用和术语保持不变。",
                ]
                if ctx.deep_rewrite
                else []
            ),
            "",
            "写作节奏要求（最重要）：",
            "- 句长必须有明显差异：同一段里至少有一句超过 40 字；允许出现 15 字以内的短句，但短句必须承载新的信息或判断。",
            "- 连续三句长度接近时，必须拆开或合并其中一句。",
            "- 主动句、被动句、把字句交替使用。",
            "- 允许长复句，允许插入补充说明和括号内容。",
            "- 不要每句都用完整的主谓宾结构，允许省略主语。",
            "- 拆分句子时，确保每句有完整的主谓结构，避免出现只有状语或宾语的残句。",
            "- 禁止为了制造节奏而添加重复上句意思的短句，例如“利润承压。”“原因并不单一。”这类原地重复。",
            "- 连续两句不要用相同的开头（例如都从“从…”或“在…”开始）；连续三句开头相同时，改掉其中两句。",
            "- 每段至少有一处限定表述：可能、在一定程度上、从现有数据看、在…范围内、倾向于。",
            "",
            "信息密度要求：",
            "- 有的地方写细：补充具体条件、范围、数据、案例、异常情况。",
            "- 有的地方写简：概括性内容可以一笔带过。",
            "- 不要匀速输出，避免每句信息量接近。",
            "",
            "限定与思辨：",
            "- 把绝对化表述改成有限定条件的表述：在…范围内、在…条件下、可能、倾向于、从现有数据看。",
            "- 适当加入对局限、反例、争议的说明。",
            "",
            "人性化要求：",
            "- 允许适度冗余、补充说明和重复强调，接近真人写作习惯。",
            "- 可以使用自然的书面连接：不过、然后、还要、其实、主要是由于、从…角度来说、就…而言。",
            "- 不要使用排比、对仗和过度对称的句式。",
            "- 不要追求每句都精确简洁，保留作者原有的表达节奏。",
            "",
            "示例：",
            "原文：第一，从并购动因来看，A是内外因素共同作用的结果。",
            "改写：第一，从并购动因的角度来说，A是内外部因素一起作用的结果。",
            "原文：首先，值得注意的是，随着数字经济的发展，农村电商在促进农产品销售方面发挥着越来越重要的作用。",
            "改写：数字经济发展之后，农村电商对农产品销售的带动作用有所增强。近年的交易数据也能支持这一判断。",
            "原文：本文旨在研究A对B的影响，分析了C，明确了D，揭示了E。",
            "改写：本文关注A对B的影响。围绕C展开分析后，D得到明确，E也在这一过程中显现出来。",
            "原文：研究表明，该方法具有显著优势。",
            "改写：已有研究显示，该方法在多数测试条件下表现更好。不过样本规模有限，结论还需要更多数据支撑。",
            "原文：并购后盈利能力先升后降，2021年达到峰值，2024年受市场变化影响净利润下降64%。",
            "改写：并购后的盈利能力先升后降，2021年冲到峰值。到了2024年，市场环境变了，新业务的培育成本也上来了，净利润同比下降约64%。这个降幅不算小。",
            "原文：从财务绩效看，……。从战略协同看，……。从风险管理看，……。",
            "改写：财务绩效上，……。战略协同方面，……。至于风险管理，……。",
            "",
            f"改写强度：{strength}",
            f"改写后字数控制在原文的 {ctx.length_ratio_min:.2f} 到 {ctx.length_ratio_max:.2f} 之间",
            f"禁止出现的词或表达：{banned}",
        ]
        if ctx.rewrite_headings:
            lines.append("- 小标题措辞可以改写，但序号和编号格式必须保持不变。")
        else:
            lines.append("- 小标题必须原样保留，不要改动标题措辞。")
        if round_index > 0:
            lines.extend(
                [
                    "",
                    "第二轮检查清单：",
                    "- 是否还有模板连接词、空泛评价、抽象大词；有则删除或换成具体说法。",
                    "- 是否连续三句长度接近；有则拆开其中一句。",
                    "- 是否有多层“的”名词串；有则拆成短句。",
                    "- 是否连续多句无主语；有则补“本文/本研究/该模型/这一过程”。",
                    "- 是否有过度断言；有则改为有限定条件的表述。",
                ]
            )
        if ctx.extra_prompt:
            lines.append(f"额外要求：{ctx.extra_prompt}")
        self._append_content(lines, ctx)
        self._append_diagnosis(lines, ctx)
        self._append_lessons(lines, ctx)
        self._append_constraints(lines, hits, context)
        return "\n".join(lines)

    def _build_general_prompt(
        self,
        ctx: LLMContext,
        round_index: int = 0,
        hits: list[dict] | None = None,
        context: str | None = None,
    ) -> str:
        style = STYLE_LABEL.get(ctx.style, STYLE_LABEL["general"])
        strength = STRENGTH_LABEL.get(ctx.strength, STRENGTH_LABEL["medium"])
        banned = "、".join(ctx.banned_words) if ctx.banned_words else "无"
        person = {
            "keep": "保持原文人称不变",
            "first": "统一使用第一人称（我）",
            "third": "使用第三人称或客观表述",
        }.get(ctx.person, "保持原文人称不变")

        header = (
            "你是审稿人。下面这段文字已经改过一轮，仍可能残留 AI 痕迹。请做第二轮修订。"
            if round_index > 0
            else "你是一名中文写作编辑。任务：改写用户给出的段落，让它读起来像一个具体的人在写，同时完整保留原意和段落结构。"
        )

        lines = [
            header,
            "",
            "必须遵守：",
            "- 整段每一句都要重写，不得原样保留任何一句；不要只替换命中清单里的词。",
            "1. 一段进，一段出。不拆分、不合并、不加标题或列表。",
            "2. 事实、观点、逻辑关系、因果、条件、结论、数据含义保持不变。",
            "3. 原样保留所有形如 ⟦A⟧ ⟦B⟧ 的占位符，编号与位置都要对应，不要删除、不要翻译、不要改动括号和字母。",
            "4. 专有名词、人名、机构名、专业术语保持不变。",
            "5. 只输出改写后的正文，不要解释、不要引号、不要“改写如下”之类的提示。",
            "6. 输出中不要包含换行符。",
            "",
            "需要清除的 AI 痕迹（按优先级）：",
            "- 模板连接词：首先/其次/最后/此外/综上所述/总而言之/由此可见/值得注意的是/需要指出的是",
            "- 空洞评价：具有重要意义/发挥重要作用/奠定坚实基础/注入新动能/提供有力支撑/不可或缺",
            "- 抽象大词：赋能/抓手/闭环/链路/沉淀/对齐/颗粒度/底层逻辑/范式/维度/组合拳",
            "- 对称句式：不是…而是…/不仅…而且…/既…又…/一方面…另一方面…/无论是…还是…",
            "- 名词化动词：对…进行…/进行…/做出…/给予…/开展…",
            "- 拔高意义：标志着…的关键时刻/开启了…新篇章/成为…的重要载体/具有里程碑意义",
            "- 破折号、引号强调、markdown 粗体、emoji",
            "- 通用积极结尾：未来可期/前景广阔/拭目以待/相信在不久的将来",
            "",
            "全局禁用表达（输出中不得出现）：首先、其次、再次、最后、综上所述、总而言之、由此可见、值得注意的是、需要指出的是、基于此、在此背景下、赋能、抓手、闭环、链路、沉淀、对齐、颗粒度、底层逻辑、范式、维度、组合拳、具有重要意义、发挥重要作用、奠定坚实基础、提供有力支撑",
            "",
            "过程痕迹（命中即删）：让我想想/等等/已深度思考（用时X秒）/我现在将/接下来我来/任务清单 checkbox/Mermaid 自用图/讨好型元话语/希望你有所帮助。",
            "反过拟合：不要连续堆短句，不要每句都口语化，不要新增原文没有的事实、数字和案例。",
            "",
            "改写方法：",
            "- 长短句交错：把过长的句子拆开，把零碎的短句并起来，避免连续三句长度接近。",
            "- 每段开头换一种句式，不要都用“随着…”“在…背景下”“…是…的重要…”。",
            "- 把抽象表述换成具体动作、场景或后果。",
            "- 允许少量口语连接词（学术语体除外），例如 其实、说白了、说到底。",
            "- 信息点数量保持不变，不新增原文没有的事实。",
            "",
            "示例：",
            "原文：首先，值得注意的是，该方案具有重要意义。",
            "改写：这个方案确实有用，至少在眼下这几个场景里是这样。",
            "原文：不仅提升了效率，而且降低了成本。",
            "改写：效率上去了，成本也降了下来。",
            "原文：随着数字化转型的不断推进，企业面临着新的挑战。",
            "改写：数字化改造往前走，企业遇到的麻烦也跟着变了。",
            "",
            f"语体：{style}",
            f"改写强度：{strength}",
            f"人称：{person}",
            f"口语化程度：{ctx.colloquial}/100（0 为完全书面，100 为高度口语）",
            f"改写后字数控制在原文的 {ctx.length_ratio_min:.2f} 到 {ctx.length_ratio_max:.2f} 之间",
            f"禁止出现的词或表达：{banned}",
        ]
        if round_index > 0:
            lines.extend(
                [
                    "",
                    "第二轮额外检查：",
                    "- 连续三句长度接近时，拆开其中一句。",
                    "- 段落开头如果和上一段句式相同，换一种写法。",
                    "- 仍有模板词或空洞评价时，直接删掉或换成具体说法。",
                ]
            )
        if ctx.extra_prompt:
            lines.append(f"额外要求：{ctx.extra_prompt}")
        self._append_content(lines, ctx)
        self._append_diagnosis(lines, ctx)
        self._append_lessons(lines, ctx)
        self._append_constraints(lines, hits, context)
        return "\n".join(lines)

    def _postprocess(self, raw: str) -> str:
        text = raw.strip()
        text = re.sub(r"\*\*([^*\n]+)\*\*", r"\1", text)
        text = _PREFIX_RE.sub("", text)
        text = re.sub(r"[\u200b\u200c\u200d\ufeff]", "", text)
        for left, right in _QUOTE_PAIRS:
            if len(text) >= 2 and text.startswith(left) and text.endswith(right):
                text = text[len(left) : -len(right)].strip()
                break
        # A paragraph must stay a single paragraph.
        if "\n" in text:
            parts = [p.strip() for p in text.split("\n") if p.strip()]
            joiner = "" if self._is_cjk(text) else " "
            text = joiner.join(parts)
        return text.strip()

    @staticmethod
    def _is_cjk(text: str) -> bool:
        cjk = len(re.findall(r"[\u4e00-\u9fff]", text))
        return cjk >= max(1, len(text) // 4)

    @staticmethod
    def placeholders(text: str) -> set[str]:
        return {m.group(1) for m in _PLACEHOLDER_RE.finditer(text)}

    @classmethod
    def placeholders_intact(cls, original: str, rewritten: str) -> bool:
        return cls.placeholders(original) <= cls.placeholders(rewritten)
