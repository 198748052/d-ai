from __future__ import annotations

import re

from .content import content_density
from .context_guard import load_whitelist
from .features import structural_issues, structural_metrics
from .leakage import scan as scan_leakage

"""五类味型诊断 + 语体门控 + 结构指标 + 修改计划。

规则来源：
- evidence-based-humanizer/humanizer-zh (Stage 1 诊断, Stage 5 终检)
- AI-Text-Anti-Detection-Framework (C-01..C-18 词汇层, S-01..S-20 句法层)
"""

CONTEXT_LABEL = {
    "academic": "学术论文",
    "official": "公文/规范文书",
    "general": "通用书面语",
    "media": "公众号/观点文",
    "fiction": "叙事",
}

# L1 公文黑话层：学术语境里出现一次就是强信号
BUSINESS_JARGON = [
    "赋能", "抓手", "痛点", "闭环", "生态", "壁垒", "颗粒度", "心智", "势能", "纬度",
    "对标", "对齐", "打通", "下沉", "抢占", "破圈", "出圈", "体感", "触达",
    "链路", "调性", "复盘", "锚点", "底座", "底层逻辑", "顶层设计", "战略高地",
    "第二曲线", "飞轮效应", "深耕", "沉淀", "拉通", "生态位", "躬身入局", "助力",
]

# L2 衔接套话层
CONNECTOR_CLICHES = [
    "综上所述", "总而言之", "总的来说", "由此可见", "不难看出", "不难发现",
    "值得注意的是", "值得一提的是", "需要指出的是", "需要强调的是", "必须强调",
    "毋庸置疑", "无可厚非", "从某种程度上讲", "从某种意义上讲", "在一定程度上",
    "在某种程度上", "换言之", "换句话说", "也就是说", "简而言之", "一言以蔽之",
    "概括起来说", "与此同时", "一方面", "另一方面", "首先", "其次", "再次",
    "最后", "第一", "第二", "第三", "第四", "一是", "二是", "三是", "四是",
]

# L3 意义拔高层
HOLLOW_TERMS = [
    "见证", "塑造", "勾勒", "深刻", "画卷", "新篇章", "谱写新篇章", "未来可期",
    "大有可为", "前景广阔", "任重道远", "指日可待", "必将", "势必", "让我们",
    "拭目以待", "这，就是", "唯有", "方能", "具有重要意义", "具有深远影响",
    "里程碑意义", "不可或缺", "至关重要", "注入新动能", "开辟新路径",
]

# L4 抒情腔层：2026 年默认输出主味，学术语境里属于语体错位
LYRIC_TERMS = [
    "拓扑", "克莱因瓶", "睫毛", "青苔", "赛博", "齿轮", "白衬衫", "瞳仁",
    "伤口", "涟漪", "温柔", "治愈", "星辰", "稳稳地接住", "不躲", "不藏",
    "不绕", "不逃", "岁月", "诗意", "远方", "微光", "烟火气",
]

# C-05 “化”字后缀与 C-06 四字堆叠
HUA_SUFFIX = [
    "系统化", "结构化", "精细化", "可视化", "模块化", "流程化", "标准化",
    "规范化", "常态化", "体系化", "数字化", "智能化", "自动化", "科学化",
    "精准化", "个性化", "定制化", "一体化", "平台化", "生态化", "产业化",
    "规模化", "长效化", "立体化", "纵深化", "场景化",
]
FOUR_CHAR = [
    "全面提升", "深度融合", "深入探讨", "扎实推进", "有机结合", "有效衔接",
    "稳步推进", "持续优化", "不断完善", "进一步加强", "有力保障", "切实做到",
    "统筹兼顾", "协调推进", "通盘考虑", "综合施策", "精准发力", "系统谋划",
    "一目了然", "事半功倍", "相辅相成", "息息相关", "行之有效", "立竿见影",
]
ABSTRACT_NOUNS = ["高度", "角度", "层面", "维度", "方面", "领域", "范畴", "视野", "格局", "站位"]
BALANCE_PHRASES = [
    "需要辩证看待", "一分为二", "既有积极的一面", "不可一概而论",
    "需要具体问题具体分析", "因情况而异",
]
RHETORICAL = [
    "为什么会这样", "问题出在哪里", "原因有三", "这是为什么", "何以至此",
]

TEMPLATE_PATTERNS: list[tuple[str, str, re.Pattern[str]]] = [
    ("P1", "不仅…而且…堆叠", re.compile(r"不仅[^。！？]{1,40}(?:而且|还|更)")),
    ("P2", "不是…而是…", re.compile(r"(?:不是|并非)[^。！？]{1,30}[，,]\s*而是")),
    ("P3", "随着…的发展", re.compile(r"随着[^。！？]{2,20}的(?:发展|进步|普及|推进)")),
    ("P3", "在当今…时代", re.compile(r"在(?:当今|如今|这个)[^。！？]{0,12}(?:时代|今天|背景下)")),
    ("P5", "四字格连缀", re.compile(r"(?:[\u4e00-\u9fff]{4}[、，,]){1,}[\u4e00-\u9fff]{4}")),
    ("P8", "通过…从而…", re.compile(r"通过[^。！？]{2,20}[，,]?\s*从而")),
    ("P8", "在…方面", re.compile(r"在[^。！？]{2,12}方面[，,]")),
    ("P9", "对…进行…", re.compile(r"对[^。！？]{1,12}进行[^。！？]{1,8}")),
    ("P9", "使…得到…", re.compile(r"使[^。！？]{1,12}得到")),
    ("P15", "双刃剑", re.compile(r"双刃剑")),
    ("P16", "不仅X更Y", re.compile(r"不仅[^。！？]{1,15}[，,]?\s*更")),
    ("C-17", "伪总结反问", re.compile(r"(?:为什么会这样|问题出在哪里|原因有三|这是为什么|何以至此)")),
    ("C-18", "顿号堆叠", re.compile(r"(?:[^。！？；，、]{1,16}、){4,}[^。！？；，、]{1,16}")),
]

_CITATION = re.compile(r"\[\d+(?:[,\-]\d+)*\]|（\d{4}）|\(\d{4}\)|（[^）]{1,12}，\s*\d{4}）")
_UNSOURCED = re.compile(r"(?:研究表明|数据显示|专家指出|学者认为|业内人士表示|普遍认为)")

FLAVOR_LABELS = {
    "hollow": "空洞升华",
    "template": "模板句式",
    "high_freq": "高频套话",
    "register": "语体错位",
    "leakage": "思维链泄露",
}

_PLAN_META = {
    "C-04": ("互联网黑话", "删除或换成具体技术动作"),
    "C-06": ("四字格堆叠", "拆成具体行为或数据"),
    "C-14": ("结尾抒情", "删除或改为限定性陈述"),
    "C-05": ("化字后缀", "改回具体动作描述"),
    "C-07": ("抽象名词", "直接陈述具体角度/层面"),
    "C-01": ("万能过渡", "删除套话，让下一句直接承接"),
    "C-02": ("开场定位", "删除背景铺垫，直接进入研究对象"),
    "C-08": ("完美列举", "打散序列，改为自然过渡"),
    "C-16": ("过度平衡", "有立场处删除平衡话术"),
    "C-17": ("伪总结反问", "改为陈述句"),
    "C-18": ("顿号堆叠", "拆成分点或合并为 2-3 项"),
    "P1": ("递进堆叠", "拆成独立判断，保留有证据的一句"),
    "P2": ("防御性对比", "保留最强一处，其余改为直陈"),
    "P3": ("破题套话", "整句删除，从实质句开场"),
    "P5": ("四字格连缀", "密度降到段内不超过 1 组"),
    "P8": ("工具状语壳", "去壳直给，实动词替换名词化结构"),
    "P9": ("名词化空动词", "直接用动词"),
    "P15": ("双刃剑", "删掉陈词，直接写两面影响"),
    "P16": ("不仅X更Y", "拆成两句或只保留一处"),
    "S-01": ("句长均匀", "主动引入长短句差异"),
    "S-02": ("短句群", "合并其中一两句，保留一个短句作强调"),
    "S-03": ("长句嵌套", "在语义切换点断句"),
    "S-04": ("长定语", "拆成动词短语或短句"),
    "S-05": ("被字句过量", "改主动语态或无主语句"),
    "S-08": ("它字指代", "省略主语或复现具体名词"),
    "S-12": ("开头重复", "改变其中两句的开头"),
    "S-15": ("段长均匀", "在关键论点处安排短段"),
    "S-16": ("的字收尾", "改为直接判断"),
    "P14": ("破折号滥用", "按功能判定，删除雷同的总结性破折"),
}


def _mask_whitelist(text: str) -> str:
    """Blank fixed collocations so 生态/闭环 inside them are not counted as jargon."""
    masked = text
    for term in load_whitelist().protect_terms():
        if term and term in masked:
            masked = masked.replace(term, " " * len(term))
    return masked


def _count_terms(text: str, terms: list[str]) -> tuple[int, list[str]]:
    hits: list[str] = []
    total = 0
    for term in terms:
        count = text.count(term)
        if count:
            total += count
            hits.append(term)
    return total, hits


def _count_patterns(text: str) -> tuple[int, list[str]]:
    total = 0
    codes: list[str] = []
    for code, _label, pattern in TEMPLATE_PATTERNS:
        matches = pattern.findall(text)
        if matches:
            total += len(matches)
            codes.append(code)
    return total, codes


def _unsourced_count(text: str) -> int:
    total = 0
    for match in _UNSOURCED.finditer(text):
        window = text[max(0, match.start() - 20) : match.end() + 20]
        if _CITATION.search(window):
            continue
        total += 1
    return total


def _flavor(count: int, chars: int, terms: list[str] | None = None) -> dict:
    return {
        "count": count,
        "per_1000": round(count * 1000 / chars, 2) if chars else 0.0,
        "terms": (terms or [])[:12],
    }


def diagnose(text: str, context: str = "academic") -> dict:
    """Score five AI-flavor classes per 1000 chars and build a rewrite plan."""
    if not text:
        return {
            "context": context,
            "context_label": CONTEXT_LABEL.get(context, context),
            "chars": 0,
            "flavors": {},
            "dominant": "",
            "dominant_label": "",
            "total_per_1000": 0.0,
            "structure": {},
            "issues": [],
            "leakage": [],
            "plan": [],
        }

    chars = max(1, len(re.sub(r"\s+", "", text)))
    masked = _mask_whitelist(text)
    business, business_hits = _count_terms(masked, BUSINESS_JARGON)
    connectors, connector_hits = _count_terms(masked, CONNECTOR_CLICHES)
    hollow, hollow_hits = _count_terms(masked, HOLLOW_TERMS)
    lyric, lyric_hits = _count_terms(masked, LYRIC_TERMS)
    hua, hua_hits = _count_terms(masked, HUA_SUFFIX)
    four, four_hits = _count_terms(masked, FOUR_CHAR)
    abstract, abstract_hits = _count_terms(masked, ABSTRACT_NOUNS)
    balance, balance_hits = _count_terms(masked, BALANCE_PHRASES)
    rhetorical, rhetorical_hits = _count_terms(masked, RHETORICAL)
    template_count, template_codes = _count_patterns(masked)
    unsourced = _unsourced_count(masked)

    structure = structural_metrics(text)
    structure_issues = structural_issues(structure)
    leakage_hits = scan_leakage(text)

    # 句式类规则是弱信号：单次出现不计，≥2 次或密度 ≥2/千字才计分。
    template_hits = template_count + len(structure_issues)
    if template_count == 1 and chars >= 800 and template_count * 1000 / chars < 2:
        template_hits -= 1
    template_hits += connectors + four + balance + rhetorical

    high_freq = business + hua + abstract
    # 语体错位：学术语体不该出现的黑话、抒情腔、意义拔高与无源权威。
    register = business + lyric + hollow + unsourced
    leakage_count = sum(item["count"] for item in leakage_hits)

    flavors = {
        "hollow": _flavor(hollow, chars, hollow_hits),
        "template": _flavor(template_hits, chars, connector_hits + four_hits + balance_hits),
        "high_freq": _flavor(high_freq, chars, business_hits + hua_hits + abstract_hits),
        "register": _flavor(register, chars, business_hits + lyric_hits + hollow_hits),
        "leakage": _flavor(leakage_count, chars, [item["category"] for item in leakage_hits]),
    }
    dominant = max(flavors, key=lambda key: flavors[key]["per_1000"])
    # 语体错位是派生指标，避免与黑话/拔高重复计数；抒情腔和无源权威单独计入。
    lyric_per_1000 = round(lyric * 1000 / chars, 2) if chars else 0.0
    unsourced_per_1000 = round(unsourced * 1000 / chars, 2) if chars else 0.0
    total_per_1000 = round(
        flavors["hollow"]["per_1000"]
        + flavors["template"]["per_1000"]
        + flavors["high_freq"]["per_1000"]
        + flavors["leakage"]["per_1000"]
        + lyric_per_1000
        + unsourced_per_1000,
        2,
    )

    plan = _build_plan(
        business_hits,
        hua_hits,
        abstract_hits,
        connector_hits,
        hollow_hits,
        template_codes,
        structure_issues,
        leakage_hits,
        business,
        hua,
        hollow,
    )

    issues: list[str] = []
    if business and context in {"academic", "official"}:
        issues.append(f"学术语体出现互联网黑话 {business} 处，属硬信号")
    if lyric:
        issues.append(f"出现抒情腔词 {lyric} 处，与学术语体错位")
    if hollow:
        issues.append(f"意义拔高表达 {hollow} 处，删后信息量不损失")
    if unsourced:
        issues.append(f"无源权威表述 {unsourced} 处，需要补引注或改为限定表述")
    if structure_issues:
        issues.append("结构问题：" + "、".join(item["label"] for item in structure_issues[:4]))
    if leakage_hits:
        issues.append("发现过程痕迹：" + "、".join(item["category"] for item in leakage_hits))
    if structure.get("sentences", 0) >= 4 and structure.get("cv", 1) >= 0.32:
        pass
    else:
        if structure.get("sentences", 0) >= 4:
            issues.append("句长变异系数偏低，缺少长短句差异")

    return {
        "context": context,
        "context_label": CONTEXT_LABEL.get(context, context),
        "chars": chars,
        "flavors": flavors,
        "dominant": dominant,
        "dominant_label": FLAVOR_LABELS.get(dominant, dominant),
        "total_per_1000": total_per_1000,
        "structure": structure,
        "issues": issues,
        "leakage": leakage_hits,
        "content_density": content_density(text),
        "plan": plan,
    }


def _build_plan(
    business_hits: list[str],
    hua_hits: list[str],
    abstract_hits: list[str],
    connector_hits: list[str],
    hollow_hits: list[str],
    template_codes: list[str],
    structure_issues: list[dict],
    leakage_hits: list[dict],
    business: int,
    hua: int,
    hollow: int,
) -> list[dict]:
    items: list[dict] = []

    def add(priority: int, code: str, label: str, action: str, count: int = 1) -> None:
        items.append(
            {
                "priority": priority,
                "code": code,
                "label": label,
                "action": action,
                "count": count,
            }
        )

    if leakage_hits:
        add(0, "X", "过程痕迹", "先清洗思维链、界面残留和 agent 独白", len(leakage_hits))
    if business_hits:
        add(1, "C-04", "互联网黑话", _PLAN_META["C-04"][1], business)
    if hollow_hits:
        add(1, "C-14", "意义拔高/结尾抒情", _PLAN_META["C-14"][1], hollow)
    if connector_hits:
        add(2, "C-01", "万能过渡", _PLAN_META["C-01"][1], len(connector_hits))
    if template_codes:
        for code in dict.fromkeys(template_codes):
            label, action = _PLAN_META.get(code, (code, "改写该句式"))
            add(2, code, label, action)
    if hua_hits:
        add(3, "C-05", "化字后缀", _PLAN_META["C-05"][1], hua)
    if abstract_hits:
        add(3, "C-07", "抽象名词", _PLAN_META["C-07"][1], len(abstract_hits))
    for issue in structure_issues:
        code = issue["code"]
        label, action = _PLAN_META.get(code, (issue["label"], issue["detail"]))
        add(4, code, label, action)
    if not items:
        add(5, "R", "常规复检", "保持原意，只处理残余模板词与句长节奏")
    return sorted(items, key=lambda item: (item["priority"], item["code"]))[:12]


def compare(before: dict, after: dict) -> dict:
    """Before/after report used by the final audit (Stage 5)."""
    before_total = float(before.get("total_per_1000") or 0.0)
    after_total = float(after.get("total_per_1000") or 0.0)
    drop = round(before_total - after_total, 2)
    ratio = round(drop / before_total, 4) if before_total else 0.0
    before_dominant = before.get("dominant") or ""
    after_dominant = after.get("dominant") or ""
    return {
        "before_total": before_total,
        "after_total": after_total,
        "drop": drop,
        "drop_ratio": ratio,
        "before_dominant": before_dominant,
        "before_dominant_label": FLAVOR_LABELS.get(before_dominant, before_dominant),
        "after_dominant": after_dominant,
        "after_dominant_label": FLAVOR_LABELS.get(after_dominant, after_dominant),
        "improved": after_total < before_total,
        "reached_target": after_total <= 4.0,
    }
