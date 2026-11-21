from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from ..db.database import get_session
from ..deps import require_admin, require_user
from ..models.models import DetectorFeedback, RewriteJob, User
from ..schemas import CalibrationOut, DetectorFeedbackIn, DetectorFeedbackOut
from ..services.rewriter.calibration import (
    build_report,
    extract_features,
    save_weights,
)
from ..services.rewriter.candidate import reload_weights

router = APIRouter(prefix="/api/detector", tags=["detector"])


def _parse_job_audit(row: RewriteJob) -> dict:
    if not row.result_json:
        return {}
    try:
        payload = json.loads(row.result_json)
    except json.JSONDecodeError:
        return {}
    return (payload.get("audit") or {})


def _feedback_row(row: DetectorFeedback, job: RewriteJob | None) -> dict:
    audit = _parse_job_audit(job) if job is not None else {}
    diagnosis = audit.get("diagnosis") or {}
    features = extract_features(diagnosis)
    try:
        red_sentences = json.loads(row.red_sentences or "[]")
    except json.JSONDecodeError:
        red_sentences = []
    return {
        "id": row.id,
        "created_at": row.created_at.isoformat(),
        "user_id": row.user_id,
        "job_id": row.job_id,
        "detector": row.detector,
        "detector_version": row.detector_version,
        "checked_at": row.checked_at.isoformat() if row.checked_at else None,
        "score_before": row.score_before,
        "score_after": row.score_after,
        "red_sentences": red_sentences,
        "notes": row.notes,
        "proxy_total": diagnosis.get("total_per_1000"),
        "proxy_features": features,
    }


@router.post("/feedback", response_model=DetectorFeedbackOut)
def create_feedback(
    payload: DetectorFeedbackIn,
    user: User = Depends(require_user),
    session: Session = Depends(get_session),
):
    detector = payload.detector.strip()
    if not detector:
        raise HTTPException(status_code=422, detail="请填写检测器名称")
    if not (0 <= payload.score_before <= 100 and 0 <= payload.score_after <= 100):
        raise HTTPException(status_code=422, detail="检测分应在 0-100 之间")
    job = None
    if payload.job_id:
        job = session.get(RewriteJob, payload.job_id)
        if job is None or (not user.is_admin and job.user_id != user.id):
            raise HTTPException(status_code=404, detail="任务不存在")
    checked_at = None
    if payload.checked_at:
        try:
            checked_at = datetime.fromisoformat(payload.checked_at.replace("Z", "+00:00"))
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="送检时间格式不正确") from exc
    row = DetectorFeedback(
        user_id=user.id,
        job_id=payload.job_id,
        detector=detector[:40],
        detector_version=payload.detector_version.strip()[:60],
        checked_at=checked_at,
        score_before=payload.score_before,
        score_after=payload.score_after,
        red_sentences=json.dumps(
            [item.strip() for item in payload.red_sentences if item.strip()][:200],
            ensure_ascii=False,
        ),
        notes=payload.notes.strip()[:2000],
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return _feedback_row(row, job)


@router.get("/feedback", response_model=list[DetectorFeedbackOut])
def list_feedback(
    limit: int = 50,
    _: User = Depends(require_admin),
    session: Session = Depends(get_session),
):
    rows = session.exec(
        select(DetectorFeedback)
        .order_by(DetectorFeedback.id.desc())
        .limit(min(max(limit, 1), 500))
    ).all()
    job_ids = {row.job_id for row in rows if row.job_id}
    jobs = {
        job.id: job
        for job in session.exec(select(RewriteJob).where(RewriteJob.id.in_(job_ids))).all()
    } if job_ids else {}
    return [_feedback_row(row, jobs.get(row.job_id)) for row in rows]


@router.get("/jobs")
def recent_jobs(
    limit: int = 20,
    _: User = Depends(require_admin),
    session: Session = Depends(get_session),
):
    rows = session.exec(
        select(RewriteJob).order_by(RewriteJob.id.desc()).limit(min(max(limit, 1), 100))
    ).all()
    output = []
    for row in rows:
        audit = _parse_job_audit(row)
        diagnosis = audit.get("diagnosis") or {}
        output.append(
            {
                "id": row.id,
                "created_at": row.created_at.isoformat(),
                "status": row.status,
                "preview": (row.original or "")[:80],
                "proxy_total": diagnosis.get("total_per_1000"),
            }
        )
    return output


def _records(session: Session) -> list[dict]:
    rows = session.exec(
        select(DetectorFeedback)
        .where(DetectorFeedback.job_id.is_not(None))
        .order_by(DetectorFeedback.id.desc())
    ).all()
    records: list[dict] = []
    for row in rows:
        job = session.get(RewriteJob, row.job_id) if row.job_id else None
        if job is None:
            continue
        audit = _parse_job_audit(job)
        diagnosis = audit.get("diagnosis") or {}
        records.append(
            {
                "features": extract_features(diagnosis),
                "score_after": row.score_after,
            }
        )
    return records


@router.get("/calibration", response_model=CalibrationOut)
def get_calibration(
    _: User = Depends(require_admin),
    session: Session = Depends(get_session),
):
    return CalibrationOut(**build_report(_records(session)))


@router.post("/calibration", response_model=CalibrationOut)
def run_calibration(
    _: User = Depends(require_admin),
    session: Session = Depends(get_session),
):
    report = build_report(_records(session))
    if report["sample_count"] >= 20:
        save_weights(report)
        reload_weights()
    return CalibrationOut(**report)
