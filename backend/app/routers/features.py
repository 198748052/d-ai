from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from ..db.database import get_session
from ..deps import require_admin
from ..models.models import FeatureRule
from ..schemas import FeatureRuleIn, FeatureRuleOut, ImportResult

router = APIRouter(prefix="/api/features", tags=["features"])


def _to_out(row: FeatureRule) -> FeatureRuleOut:
    try:
        replacements = json.loads(row.replacements or "[]")
    except json.JSONDecodeError:
        replacements = []
    return FeatureRuleOut(
        id=row.id,
        name=row.name,
        category=row.category,
        scope=row.scope,
        pattern=row.pattern,
        replacements=[str(r) for r in replacements],
        severity=row.severity,
        replace_mode=getattr(row, "replace_mode", "all") or "all",
        enabled=row.enabled,
        builtin=row.builtin,
        note=row.note,
    )


@router.get("", response_model=list[FeatureRuleOut])
def list_rules(
    scope: str | None = None,
    category: str | None = None,
    session: Session = Depends(get_session),
):
    query = select(FeatureRule)
    if scope:
        query = query.where(FeatureRule.scope == scope)
    if category:
        query = query.where(FeatureRule.category == category)
    rows = session.exec(query.order_by(FeatureRule.scope, FeatureRule.category, FeatureRule.id)).all()
    return [_to_out(row) for row in rows]


@router.post("", response_model=FeatureRuleOut)
def create_rule(
    payload: FeatureRuleIn,
    _: object = Depends(require_admin),
    session: Session = Depends(get_session),
):
    if not payload.pattern.strip():
        raise HTTPException(status_code=400, detail="匹配内容不能为空")
    row = FeatureRule(
        name=payload.name or payload.pattern[:30],
        category=payload.category,
        scope=payload.scope,
        pattern=payload.pattern,
        replacements=json.dumps(payload.replacements, ensure_ascii=False),
        severity=payload.severity,
        replace_mode=payload.replace_mode,
        enabled=payload.enabled,
        note=payload.note,
        builtin=False,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return _to_out(row)


@router.put("/{rule_id}", response_model=FeatureRuleOut)
def update_rule(
    rule_id: int,
    payload: FeatureRuleIn,
    _: object = Depends(require_admin),
    session: Session = Depends(get_session),
):
    row = session.get(FeatureRule, rule_id)
    if not row:
        raise HTTPException(status_code=404, detail="规则不存在")
    row.name = payload.name or payload.pattern[:30]
    row.category = payload.category
    row.scope = payload.scope
    row.pattern = payload.pattern
    row.replacements = json.dumps(payload.replacements, ensure_ascii=False)
    row.severity = payload.severity
    row.replace_mode = payload.replace_mode
    row.enabled = payload.enabled
    row.note = payload.note
    session.add(row)
    session.commit()
    session.refresh(row)
    return _to_out(row)


@router.delete("/{rule_id}")
def delete_rule(
    rule_id: int,
    _: object = Depends(require_admin),
    session: Session = Depends(get_session),
):
    row = session.get(FeatureRule, rule_id)
    if not row:
        raise HTTPException(status_code=404, detail="规则不存在")
    session.delete(row)
    session.commit()
    return {"message": "已删除"}


@router.get("/export")
def export_rules(session: Session = Depends(get_session)):
    rows = session.exec(select(FeatureRule)).all()
    return [_to_out(row).model_dump() for row in rows]


@router.post("/import", response_model=ImportResult)
def import_rules(
    payload: list[FeatureRuleIn],
    _: object = Depends(require_admin),
    session: Session = Depends(get_session),
):
    imported = 0
    skipped = 0
    for item in payload:
        if not item.pattern.strip():
            skipped += 1
            continue
        exists = session.exec(
            select(FeatureRule).where(
                FeatureRule.pattern == item.pattern,
                FeatureRule.scope == item.scope,
            )
        ).first()
        if exists:
            skipped += 1
            continue
        session.add(
            FeatureRule(
                name=item.name or item.pattern[:30],
                category=item.category,
                scope=item.scope,
                pattern=item.pattern,
                replacements=json.dumps(item.replacements, ensure_ascii=False),
                severity=item.severity,
                enabled=item.enabled,
                note=item.note,
                builtin=False,
            )
        )
        imported += 1
    session.commit()
    return ImportResult(imported=imported, skipped=skipped)
