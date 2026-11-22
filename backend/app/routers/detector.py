from __future__ import annotations

import csv
import io
import json
import re
from collections import defaultdict
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse
from sqlmodel import Session, select

from ..db.database import get_session
from ..deps import require_admin, require_user
from ..models.models import DetectorFeedback, RewriteJob, User
from ..schemas import (
    CalibrationOut,
    DetectorClusterOut,
    DetectorFeedbackImport,
    DetectorFeedbackIn,
    DetectorFeedbackOut,
    ImportResult,
)
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


def _records(
    session: Session,
    detector: str | None = None,
    version: str | None = None,
) -> list[dict]:
    query = select(DetectorFeedback).where(DetectorFeedback.job_id.is_not(None))
    if detector:
        query = query.where(DetectorFeedback.detector == detector)
    if version:
        query = query.where(DetectorFeedback.detector_version == version)
    rows = session.exec(query.order_by(DetectorFeedback.id.desc())).all()
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
                "detector": row.detector,
                "detector_version": row.detector_version,
            }
        )
    return records


def _group_report(records: list[dict]) -> dict:
    groups: dict[str, list[dict]] = defaultdict(list)
    for record in records:
        key = f"{record.get('detector') or '未命名'} / {record.get('detector_version') or '未标注版本'}"
        groups[key].append(record)
    group_reports = {key: build_report(rows) for key, rows in groups.items()}
    active_group = ""
    if group_reports:
        active_group = max(group_reports, key=lambda key: group_reports[key]["sample_count"])
    active = group_reports.get(active_group, {})
    overall = build_report(records)
    weights = active.get("weights") or overall.get("weights") or {}
    correlations = active.get("correlations") or overall.get("correlations") or {}
    recommendation = active.get("recommendation") or overall.get("recommendation") or ""
    if active_group:
        recommendation = f"当前按检测器/版本分组，权重取自样本最多的组「{active_group}」。" + recommendation
    return {
        "sample_count": overall.get("sample_count", 0),
        "correlations": correlations,
        "weights": weights,
        "recommendation": recommendation,
        "groups": group_reports,
        "active_group": active_group,
    }


@router.get("/calibration", response_model=CalibrationOut)
def get_calibration(
    detector: str | None = None,
    version: str | None = None,
    _: User = Depends(require_admin),
    session: Session = Depends(get_session),
):
    return CalibrationOut(**_group_report(_records(session, detector, version)))


@router.post("/calibration", response_model=CalibrationOut)
def run_calibration(
    detector: str | None = None,
    version: str | None = None,
    _: User = Depends(require_admin),
    session: Session = Depends(get_session),
):
    report = _group_report(_records(session, detector, version))
    if report["sample_count"] >= 20 and report["weights"]:
        save_weights(report)
        reload_weights()
    return CalibrationOut(**report)


CLUSTER_RULES: list[tuple[str, re.Pattern[str]]] = [
    ("模板连接词", re.compile(r"首先|其次|再次|最后|综上所述|总而言之|由此可见|值得注意的是|需要指出的是")),
    ("不是…而是", re.compile(r"(?:不是|并非)[^。！？]{1,30}[，,]\s*而是")),
    ("不仅…而且", re.compile(r"不仅[^。！？]{1,40}(?:而且|还|更)")),
    ("随着…发展", re.compile(r"随着[^。！？]{2,20}的(?:发展|进步|普及|推进)")),
    ("对…进行", re.compile(r"对[^。！？]{1,12}进行")),
    ("被字句", re.compile(r"被[^。！？]{1,20}")),
    ("三层的字链", re.compile(r"(?:[^，。；！？\s]{1,12}的){3,}")),
    ("长句", re.compile(r"^.{60,}$")),
    ("短句", re.compile(r"^.{0,14}$")),
]


def _cluster_red_sentences(sentences: list[str]) -> list[dict]:
    buckets: dict[str, list[str]] = defaultdict(list)
    for sentence in sentences:
        text = sentence.strip()
        if not text:
            continue
        label = "其他"
        for name, pattern in CLUSTER_RULES:
            if pattern.search(text):
                label = name
                break
        buckets[label].append(text)
    return [
        {"label": label, "count": len(items), "examples": items[:3]}
        for label, items in sorted(buckets.items(), key=lambda pair: len(pair[1]), reverse=True)
    ]


def _parse_csv(text: str) -> list[dict]:
    reader = csv.DictReader(io.StringIO(text))
    rows: list[dict] = []
    for raw in reader:
        detector = (raw.get("detector") or "").strip()
        if not detector:
            continue
        try:
            score_before = float(raw.get("score_before") or 0)
            score_after = float(raw.get("score_after") or 0)
        except ValueError:
            continue
        if not (0 <= score_before <= 100 and 0 <= score_after <= 100):
            continue
        job_id = None
        if (raw.get("job_id") or "").strip():
            try:
                job_id = int(str(raw.get("job_id")).strip())
            except ValueError:
                job_id = None
        red = (raw.get("red_sentences") or "").replace("；", "|").replace(";", "|")
        rows.append(
            {
                "job_id": job_id,
                "detector": detector[:40],
                "detector_version": (raw.get("detector_version") or "").strip()[:60],
                "checked_at": (raw.get("checked_at") or "").strip(),
                "score_before": score_before,
                "score_after": score_after,
                "red_sentences": [item.strip() for item in red.split("|") if item.strip()],
                "notes": (raw.get("notes") or "").strip()[:2000],
            }
        )
    return rows


@router.post("/feedback/import", response_model=ImportResult)
def import_feedback(
    payload: DetectorFeedbackImport,
    user: User = Depends(require_admin),
    session: Session = Depends(get_session),
):
    if not payload.csv.strip():
        raise HTTPException(status_code=422, detail="CSV 内容为空")
    rows = _parse_csv(payload.csv)
    imported = 0
    skipped = 0
    seen: set[tuple] = set()
    for item in rows:
        key = (
            item["job_id"],
            item["detector"],
            item["detector_version"],
            item["score_after"],
        )
        if key in seen:
            skipped += 1
            continue
        seen.add(key)
        exists = session.exec(
            select(DetectorFeedback).where(
                DetectorFeedback.job_id == item["job_id"],
                DetectorFeedback.detector == item["detector"],
                DetectorFeedback.detector_version == item["detector_version"],
                DetectorFeedback.score_after == item["score_after"],
            )
        ).first()
        if exists:
            skipped += 1
            continue
        checked_at = None
        if item["checked_at"]:
            try:
                checked_at = datetime.fromisoformat(
                    item["checked_at"].replace("Z", "+00:00")
                )
            except ValueError:
                checked_at = None
        session.add(
            DetectorFeedback(
                user_id=user.id,
                job_id=item["job_id"],
                detector=item["detector"],
                detector_version=item["detector_version"],
                checked_at=checked_at,
                score_before=item["score_before"],
                score_after=item["score_after"],
                red_sentences=json.dumps(item["red_sentences"][:200], ensure_ascii=False),
                notes=item["notes"],
            )
        )
        imported += 1
    session.commit()
    return ImportResult(imported=imported, skipped=skipped)


@router.get("/feedback/export")
def export_feedback(
    _: User = Depends(require_admin),
    session: Session = Depends(get_session),
):
    rows = session.exec(select(DetectorFeedback).order_by(DetectorFeedback.id.desc())).all()
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "job_id",
            "detector",
            "detector_version",
            "checked_at",
            "score_before",
            "score_after",
            "red_sentences",
            "notes",
        ]
    )
    for row in rows:
        try:
            red = json.loads(row.red_sentences or "[]")
        except json.JSONDecodeError:
            red = []
        writer.writerow(
            [
                row.job_id or "",
                row.detector,
                row.detector_version,
                row.checked_at.isoformat() if row.checked_at else "",
                row.score_before,
                row.score_after,
                "|".join(str(item) for item in red),
                row.notes,
            ]
        )
    return PlainTextResponse(
        buffer.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="detector-feedback.csv"'},
    )


@router.get("/clusters", response_model=list[DetectorClusterOut])
def red_sentence_clusters(
    detector: str | None = None,
    version: str | None = None,
    _: User = Depends(require_admin),
    session: Session = Depends(get_session),
):
    query = select(DetectorFeedback)
    if detector:
        query = query.where(DetectorFeedback.detector == detector)
    if version:
        query = query.where(DetectorFeedback.detector_version == version)
    rows = session.exec(query.order_by(DetectorFeedback.id.desc()).limit(1000)).all()
    sentences: list[str] = []
    for row in rows:
        try:
            sentences.extend(json.loads(row.red_sentences or "[]"))
        except json.JSONDecodeError:
            continue
    return [DetectorClusterOut(**item) for item in _cluster_red_sentences(sentences)]
