from __future__ import annotations

import json
import re

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from ..db.database import get_session
from ..deps import require_admin
from ..models.models import FeatureRule, User
from ..schemas import (
    ImportResult,
    MiningApplyRequest,
    MiningRequest,
    MiningResponse,
)
from ..services.rewriter.rule_mining import mine_rules

router = APIRouter(prefix="/api/mining", tags=["mining"])


@router.post("/analyze", response_model=MiningResponse)
def analyze(
    payload: MiningRequest,
    _: User = Depends(require_admin),
):
    if not payload.high_texts or not payload.low_texts:
        raise HTTPException(status_code=422, detail="请同时提供高 AI 率和低 AI 率文章")
    return MiningResponse(**mine_rules(payload.high_texts, payload.low_texts, payload.top_n))


@router.post("/apply", response_model=ImportResult)
def apply_candidates(
    payload: MiningApplyRequest,
    _: User = Depends(require_admin),
    session: Session = Depends(get_session),
):
    imported = 0
    skipped = 0
    for item in payload.candidates:
        pattern = (item.pattern or "").strip()
        if not pattern or item.kind not in {"lexicon", "regex"}:
            skipped += 1
            continue
        if item.kind == "regex":
            try:
                re.compile(pattern)
            except re.error:
                skipped += 1
                continue
        exists = session.exec(
            select(FeatureRule).where(
                FeatureRule.pattern == pattern,
                FeatureRule.scope == "academic",
                FeatureRule.category == item.kind,
            )
        ).first()
        if exists:
            skipped += 1
            continue
        session.add(
            FeatureRule(
                name=(item.note or pattern)[:80],
                category=item.kind,
                scope="academic",
                pattern=pattern,
                replacements=json.dumps(item.replacements or [], ensure_ascii=False),
                severity=item.severity if item.severity in {"high", "medium", "low"} else "medium",
                enabled=True,
                builtin=False,
                note=item.note or "规则挖掘候选",
            )
        )
        imported += 1
    session.commit()
    return ImportResult(imported=imported, skipped=skipped)
