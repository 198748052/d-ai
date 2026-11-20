from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlmodel import Session, select

from ..db.database import engine, get_session
from ..models.models import LLMSetting, RewriteJob
from ..schemas import AuditRequest, AuditResult, RewriteRequest, RewriteResponse
from ..services.rewriter.audit import audit_text
from ..services.rewriter.llm_engine import LLMEngine, LLMError
from ..services.rewriter.jobs import JOBS, get_job, new_job
from ..services.rewriter.orchestrator import (
    build_context,
    load_rules,
    rewrite_document,
)
from ..services.rewriter.rule_engine import RuleEngine
from ..services.segmenter import split_paragraphs

router = APIRouter(prefix="/api", tags=["rewrite"])


def _resolve(session: Session, req: RewriteRequest):
    if not req.text or not req.text.strip():
        raise HTTPException(status_code=400, detail="请输入需要改写的文章")
    if len(req.text) > 200_000:
        raise HTTPException(
            status_code=400,
            detail="文本过长，单次上限 20 万字符，请分段处理",
        )
    ctx = build_context(req, session)
    rules = load_rules(session, ctx.lexicon_scope, ctx.style)
    setting = session.get(LLMSetting, 1)
    llm = LLMEngine.from_setting(setting) if setting else None
    if setting:
        ctx.concurrency = max(1, setting.concurrency)
    return ctx, rules, llm


def _save_job(req: RewriteRequest, ctx, response: RewriteResponse) -> None:
    try:
        with Session(engine) as session:
            session.add(
                RewriteJob(
                    mode=ctx.mode,
                    style=ctx.style,
                    strength=ctx.strength,
                    original=req.text,
                    rewritten=response.rewritten_text,
                    params_json=json.dumps(
                        {
                            "preset_id": req.preset_id,
                            "colloquial": ctx.colloquial,
                            "paragraphs": response.stats.paragraphs,
                            "avg_changed_ratio": response.stats.avg_changed_ratio,
                        },
                        ensure_ascii=False,
                    ),
                )
            )
            session.commit()
    except Exception:  # noqa: BLE001
        pass


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post("/rewrite")
async def rewrite_stream(req: RewriteRequest, session: Session = Depends(get_session)):
    ctx, rules, llm = _resolve(session, req)

    async def event_gen():
        queue: asyncio.Queue = asyncio.Queue()

        async def emit(result):
            await queue.put(("paragraph", result.model_dump()))

        async def runner():
            try:
                response = await rewrite_document(req.text, ctx, rules, llm, emit)
                _save_job(req, ctx, response)
                await queue.put(("done", response.model_dump()))
            except LLMError as exc:
                await queue.put(("error", {"message": str(exc)}))
            except Exception as exc:  # noqa: BLE001
                await queue.put(("error", {"message": f"改写失败：{exc}"}))
            finally:
                await queue.put((None, None))

        task = asyncio.create_task(runner())
        try:
            while True:
                event, data = await queue.get()
                if event is None:
                    break
                yield _sse(event, data)
        finally:
            if not task.done():
                task.cancel()

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/rewrite/sync", response_model=RewriteResponse)
async def rewrite_sync(req: RewriteRequest, session: Session = Depends(get_session)):
    ctx, rules, llm = _resolve(session, req)
    try:
        response = await rewrite_document(req.text, ctx, rules, llm)
    except LLMError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _save_job(req, ctx, response)
    return response


def _update_job_db(db_id: int | None, **fields) -> None:
    if not db_id:
        return
    try:
        with Session(engine) as session:
            row = session.get(RewriteJob, db_id)
            if row is None:
                return
            for key, value in fields.items():
                setattr(row, key, value)
            row.updated_at = datetime.now(timezone.utc)
            session.add(row)
            session.commit()
    except Exception:  # noqa: BLE001
        pass


@router.get("/jobs")
def list_jobs(limit: int = 30, session: Session = Depends(get_session)):
    rows = session.exec(
        select(RewriteJob).order_by(RewriteJob.id.desc()).limit(min(limit, 100))
    ).all()
    return [
        {
            "id": row.id,
            "created_at": row.created_at.isoformat(),
            "updated_at": (row.updated_at or row.created_at).isoformat(),
            "status": row.status,
            "mode": row.mode,
            "style": row.style,
            "strength": row.strength,
            "original_preview": row.original[:120],
            "progress_total": row.progress_total,
            "progress_completed": row.progress_completed,
            "error": row.error,
        }
        for row in rows
    ]


@router.get("/jobs/{job_id}")
def get_job_detail(job_id: int, session: Session = Depends(get_session)):
    row = session.get(RewriteJob, job_id)
    if row is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    result = None
    if row.result_json:
        try:
            result = json.loads(row.result_json)
        except json.JSONDecodeError:
            result = None
    return {
        "id": row.id,
        "created_at": row.created_at.isoformat(),
        "updated_at": (row.updated_at or row.created_at).isoformat(),
        "status": row.status,
        "mode": row.mode,
        "style": row.style,
        "strength": row.strength,
        "original": row.original,
        "rewritten": row.rewritten,
        "progress_total": row.progress_total,
        "progress_completed": row.progress_completed,
        "error": row.error,
        "result": result,
    }



def _find_job_by_db_id(db_id: int):
    for job in JOBS.values():
        if job.db_id == db_id:
            return job
    return None


@router.post("/jobs/{job_id}/pause")
def pause_job(job_id: int):
    job = _find_job_by_db_id(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="任务不在运行中")
    job.pause_event.clear()
    _update_job_db(job_id, status="paused")
    return {"status": "paused"}


@router.post("/jobs/{job_id}/resume")
def resume_job(job_id: int):
    job = _find_job_by_db_id(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="任务不在运行中")
    job.pause_event.set()
    _update_job_db(job_id, status="running")
    return {"status": "running"}


@router.post("/jobs/{job_id}/rerun")
async def rerun_job(job_id: int, session: Session = Depends(get_session)):
    row = session.get(RewriteJob, job_id)
    if row is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    if not row.original.strip():
        raise HTTPException(status_code=400, detail="任务没有原文，无法重新执行")
    return await create_rewrite_job(RewriteRequest(text=row.original), session)


async def _run_job(job, req: RewriteRequest, ctx, rules, llm) -> None:
    try:

        async def emit(result):
            job.paragraphs[result.index] = result.model_dump()
            job.completed = len(job.paragraphs)
            partial = {
                "paragraphs": [job.paragraphs[key] for key in sorted(job.paragraphs)],
                "stats": None,
                "audit": None,
                "warnings": [],
                "ppl_issues": [],
            }
            _update_job_db(
                job.db_id,
                progress_completed=job.completed,
                result_json=json.dumps(partial, ensure_ascii=False),
            )

        response = await rewrite_document(
            req.text, ctx, rules, llm, emit, pause_event=job.pause_event
        )
        job.paragraphs = {p.index: p.model_dump() for p in response.paragraphs}
        job.completed = len(job.paragraphs)
        job.stats = response.stats.model_dump()
        job.audit = response.audit.model_dump() if response.audit else None
        job.warnings = list(response.warnings)
        job.ppl_issues = [item.model_dump() for item in response.ppl_issues]
        job.status = "done"
        payload = {
            "paragraphs": [p.model_dump() for p in response.paragraphs],
            "stats": response.stats.model_dump(),
            "audit": response.audit.model_dump() if response.audit else None,
            "warnings": response.warnings,
            "ppl_issues": [item.model_dump() for item in response.ppl_issues],
        }
        _update_job_db(
            job.db_id,
            status="done",
            rewritten=response.rewritten_text,
            result_json=json.dumps(payload, ensure_ascii=False),
            progress_completed=job.completed,
        )
    except LLMError as exc:
        job.status = "error"
        job.error = str(exc)
        _update_job_db(job.db_id, status="error", error=job.error)
    except Exception as exc:  # noqa: BLE001
        job.status = "error"
        job.error = f"改写失败：{exc}"
        _update_job_db(job.db_id, status="error", error=job.error)


@router.post("/rewrite/jobs")
async def create_rewrite_job(req: RewriteRequest, session: Session = Depends(get_session)):
    ctx, rules, llm = _resolve(session, req)
    paragraphs = split_paragraphs(req.text)
    if not paragraphs:
        raise HTTPException(status_code=400, detail="没有解析到任何段落，请检查输入内容")

    db_job = RewriteJob(
        status="running",
        mode=ctx.mode,
        style=ctx.style,
        strength=ctx.strength,
        original=req.text,
        params_json=json.dumps({"preset_id": req.preset_id}, ensure_ascii=False),
        progress_total=len(paragraphs),
        progress_completed=0,
    )
    session.add(db_job)
    session.commit()
    session.refresh(db_job)

    job = new_job(len(paragraphs))
    job.db_id = db_job.id
    job.task = asyncio.create_task(_run_job(job, req, ctx, rules, llm))
    return {"job_id": job.id, "db_id": db_job.id, "total": job.total}


@router.get("/rewrite/jobs/{job_id}")
def get_rewrite_job(job_id: str):
    job = get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="任务不存在或已过期")
    return {
        "job_id": job.id,
        "db_id": job.db_id,
        "status": job.status,
        "total": job.total,
        "completed": job.completed,
        "paragraphs": [job.paragraphs[key] for key in sorted(job.paragraphs)],
        "stats": job.stats,
        "audit": job.audit,
        "warnings": job.warnings,
        "ppl_issues": job.ppl_issues,
        "error": job.error,
    }


@router.post("/audit", response_model=AuditResult)
def audit(req: AuditRequest, session: Session = Depends(get_session)):
    if not req.text or not req.text.strip():
        raise HTTPException(status_code=400, detail="请输入需要验证的文本")
    rewrite_req = RewriteRequest(
        text=req.text,
        preset_id=req.preset_id,
        style=req.style,
        lexicon_scope=req.lexicon_scope,
        mode="rule",
    )
    ctx = build_context(rewrite_req, session)
    rules = load_rules(session, ctx.lexicon_scope, ctx.style)
    return audit_text(req.text, RuleEngine(rules), use_local=ctx.use_local_model)
