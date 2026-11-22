from __future__ import annotations

import json
import math
from pathlib import Path

from ...core.config import DATA_DIR

"""评估层：用真实检测器反馈校准代理指标与候选选择权重。"""

WEIGHTS_PATH = DATA_DIR / "calibration.json"

FEATURE_KEYS = [
    "proxy_total",
    "template_per_1000",
    "high_freq_per_1000",
    "register_per_1000",
    "hollow_per_1000",
    "cv",
    "short_run",
    "long_nested",
]


def extract_features(diagnosis: dict | None) -> dict:
    diagnosis = diagnosis or {}
    flavors = diagnosis.get("flavors") or {}
    structure = diagnosis.get("structure") or {}
    return {
        "proxy_total": float(diagnosis.get("total_per_1000") or 0.0),
        "template_per_1000": float((flavors.get("template") or {}).get("per_1000") or 0.0),
        "high_freq_per_1000": float((flavors.get("high_freq") or {}).get("per_1000") or 0.0),
        "register_per_1000": float((flavors.get("register") or {}).get("per_1000") or 0.0),
        "hollow_per_1000": float((flavors.get("hollow") or {}).get("per_1000") or 0.0),
        "cv": float(structure.get("cv") or 0.0),
        "short_run": float(structure.get("short_run") or 0.0),
        "long_nested": float(structure.get("long_nested") or 0.0),
    }


def pearson(xs: list[float], ys: list[float]) -> float:
    if len(xs) < 3 or len(xs) != len(ys):
        return 0.0
    mean_x = sum(xs) / len(xs)
    mean_y = sum(ys) / len(ys)
    numerator = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    denominator = math.sqrt(
        sum((x - mean_x) ** 2 for x in xs) * sum((y - mean_y) ** 2 for y in ys)
    )
    return round(numerator / denominator, 4) if denominator else 0.0


def _solve(matrix: list[list[float]], vector: list[float]) -> list[float] | None:
    size = len(vector)
    augmented = [row[:] + [vector[index]] for index, row in enumerate(matrix)]
    for column in range(size):
        pivot = max(range(column, size), key=lambda row: abs(augmented[row][column]))
        if abs(augmented[pivot][column]) < 1e-9:
            return None
        augmented[column], augmented[pivot] = augmented[pivot], augmented[column]
        divisor = augmented[column][column]
        augmented[column] = [value / divisor for value in augmented[column]]
        for row in range(size):
            if row == column:
                continue
            factor = augmented[row][column]
            if factor == 0:
                continue
            augmented[row] = [
                augmented[row][index] - factor * augmented[column][index]
                for index in range(size + 1)
            ]
    return [augmented[row][size] for row in range(size)]


def fit_linear(records: list[dict], feature_keys: list[str]) -> dict:
    if len(records) < len(feature_keys) + 2:
        return {}
    design = [[1.0] + [float(record["features"].get(key, 0.0)) for key in feature_keys] for record in records]
    target = [float(record["score_after"]) for record in records]
    size = len(feature_keys) + 1
    matrix = [[0.0] * size for _ in range(size)]
    vector = [0.0] * size
    for row, y in zip(design, target):
        for i in range(size):
            vector[i] += row[i] * y
            for j in range(size):
                matrix[i][j] += row[i] * row[j]
    # 轻微岭正则，避免特征共线时矩阵奇异。
    for index in range(size):
        matrix[index][index] += 1e-3
    solution = _solve(matrix, vector)
    if solution is None:
        return {}
    return {
        "intercept": round(solution[0], 4),
        "coefficients": {
            key: round(value, 4) for key, value in zip(feature_keys, solution[1:])
        },
    }


def build_report(records: list[dict]) -> dict:
    """records: [{"features": {...}, "score_after": float}]"""
    if not records:
        return {
            "sample_count": 0,
            "correlations": {},
            "weights": {},
            "recommendation": "还没有检测器反馈，先积累 20 段以上的真实送检结果。",
        }
    scores = [float(record["score_after"]) for record in records]
    correlations = {
        key: pearson([float(record["features"].get(key, 0.0)) for record in records], scores)
        for key in FEATURE_KEYS
    }
    weights = fit_linear(records, FEATURE_KEYS)
    strongest = max(correlations.items(), key=lambda item: abs(item[1])) if correlations else ("", 0)
    if len(records) < 20:
        recommendation = (
            f"当前只有 {len(records)} 条反馈，相关性只能做方向参考；"
            "建议先积累到 20 条以上再保存权重。"
        )
    else:
        recommendation = (
            f"与检测分相关性最强的代理指标是 {strongest[0]}（r={strongest[1]}）。"
            "保存权重后，候选选择器会优先选择预测检测分更低的版本。"
        )
    return {
        "sample_count": len(records),
        "correlations": correlations,
        "weights": weights,
        "recommendation": recommendation,
    }


def save_weights(report: dict) -> None:
    weights = report.get("weights") or {}
    coefficients = weights.get("coefficients") or {}
    if not coefficients:
        return
    # 把回归系数转换成候选选择器的相对权重，保持总和为 1。
    proxy_keys = ["proxy_total", "template_per_1000", "high_freq_per_1000", "register_per_1000"]
    proxy_mass = sum(abs(float(coefficients.get(key, 0.0))) for key in proxy_keys)
    selector = {
        "proxy": min(0.7, max(0.2, proxy_mass / 100 if proxy_mass else 0.45)),
        "semantic": 0.2,
        "natural": 0.2,
        "content": 0.15,
    }
    total = sum(selector.values()) or 1.0
    selector = {key: round(value / total, 4) for key, value in selector.items()}
    payload = {
        "updated_at": None,
        "sample_count": report.get("sample_count", 0),
        "correlations": report.get("correlations", {}),
        "groups": report.get("groups", {}),
        "active_group": report.get("active_group", ""),
        "regression": weights,
        "selector_weights": selector,
    }
    WEIGHTS_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def load_calibration() -> dict:
    try:
        return json.loads(WEIGHTS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
