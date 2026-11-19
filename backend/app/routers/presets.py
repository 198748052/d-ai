from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from ..db.database import get_session
from ..models.models import Preset
from ..schemas import PresetIn, PresetOut

router = APIRouter(prefix="/api/presets", tags=["presets"])


def _to_out(row: Preset) -> PresetOut:
    try:
        protect_terms = json.loads(row.protect_terms or "[]")
    except json.JSONDecodeError:
        protect_terms = []
    try:
        banned_words = json.loads(row.banned_words or "[]")
    except json.JSONDecodeError:
        banned_words = []
    return PresetOut(
        id=row.id,
        name=row.name,
        style=row.style,
        lexicon_scope=row.lexicon_scope,
        strength=row.strength,
        person=row.person,
        colloquial=row.colloquial,
        length_ratio_min=row.length_ratio_min,
        length_ratio_max=row.length_ratio_max,
        protect_terms=[str(t) for t in protect_terms],
        banned_words=[str(t) for t in banned_words],
        use_rule_engine=row.use_rule_engine,
        use_llm=row.use_llm,
        max_rounds=row.max_rounds,
        extra_prompt=row.extra_prompt,
        builtin=row.builtin,
    )


@router.get("", response_model=list[PresetOut])
def list_presets(session: Session = Depends(get_session)):
    rows = session.exec(select(Preset).where(Preset.name == "学术论文")).all()
    if not rows:
        rows = session.exec(select(Preset).order_by(Preset.id).limit(1)).all()
    return [_to_out(row) for row in rows]


@router.post("", response_model=PresetOut)
def create_preset(payload: PresetIn, session: Session = Depends(get_session)):
    raise HTTPException(status_code=400, detail="系统只维护「学术论文」预设，请直接编辑该预设")
    row = Preset(
        name=payload.name.strip(),
        style=payload.style,
        lexicon_scope=payload.lexicon_scope,
        strength=payload.strength,
        person=payload.person,
        colloquial=payload.colloquial,
        length_ratio_min=payload.length_ratio_min,
        length_ratio_max=payload.length_ratio_max,
        protect_terms=json.dumps(payload.protect_terms, ensure_ascii=False),
        banned_words=json.dumps(payload.banned_words, ensure_ascii=False),
        use_rule_engine=payload.use_rule_engine,
        use_llm=payload.use_llm,
        max_rounds=payload.max_rounds,
        extra_prompt=payload.extra_prompt,
        builtin=False,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return _to_out(row)


@router.put("/{preset_id}", response_model=PresetOut)
def update_preset(preset_id: int, payload: PresetIn, session: Session = Depends(get_session)):
    row = session.get(Preset, preset_id)
    if not row:
        raise HTTPException(status_code=404, detail="预设不存在")
    row.name = "学术论文"
    row.style = payload.style
    row.lexicon_scope = payload.lexicon_scope
    row.strength = payload.strength
    row.person = payload.person
    row.colloquial = payload.colloquial
    row.length_ratio_min = payload.length_ratio_min
    row.length_ratio_max = payload.length_ratio_max
    row.protect_terms = json.dumps(payload.protect_terms, ensure_ascii=False)
    row.banned_words = json.dumps(payload.banned_words, ensure_ascii=False)
    row.use_rule_engine = payload.use_rule_engine
    row.use_llm = payload.use_llm
    row.max_rounds = payload.max_rounds
    row.extra_prompt = payload.extra_prompt
    session.add(row)
    session.commit()
    session.refresh(row)
    return _to_out(row)


@router.delete("/{preset_id}")
def delete_preset(preset_id: int, session: Session = Depends(get_session)):
    raise HTTPException(status_code=400, detail="「学术论文」预设不可删除")
