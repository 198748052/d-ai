from __future__ import annotations

import time

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from ..core.crypto import decrypt, encrypt, mask_key
from ..db.database import get_session
from ..deps import require_admin
from ..models.models import LLMSetting
from ..schemas import (
    LLMSettingIn,
    LLMSettingOut,
    LLMTestIn,
    LLMTestOut,
    LocalModelLoadIn,
    LocalModelStatusOut,
    PerplexityRequest,
    PerplexityResult,
)
from ..services import local_model
from ..services.rewriter.llm_engine import LLMEngine, LLMError

router = APIRouter(
    prefix="/api/settings/llm",
    tags=["llm"],
    dependencies=[Depends(require_admin)],
)


def _get_or_create(session: Session) -> LLMSetting:
    setting = session.get(LLMSetting, 1)
    if setting is None:
        setting = LLMSetting(id=1)
        session.add(setting)
        session.commit()
        session.refresh(setting)
    return setting


def _to_out(setting: LLMSetting) -> LLMSettingOut:
    plain = decrypt(setting.api_key_enc)
    return LLMSettingOut(
        provider=setting.provider,
        base_url=setting.base_url,
        model=setting.model,
        api_key_masked=mask_key(plain),
        has_key=bool(plain),
        temperature=setting.temperature,
        max_tokens=setting.max_tokens,
        concurrency=setting.concurrency,
        timeout=setting.timeout,
        local_enabled=getattr(setting, "local_enabled", False),
        local_model=getattr(setting, "local_model", "uer/gpt2-chinese-cluecorpussmall"),
        local_dtype=getattr(setting, "local_dtype", "float16"),
        ppl_min=float(getattr(setting, "ppl_min", 60.0) or 60.0),
        ppl_retry=int(getattr(setting, "ppl_retry", 2) or 0),
        ppl_severe=float(getattr(setting, "ppl_severe", 25.0) or 25.0),
    )


@router.get("", response_model=LLMSettingOut)
def read_setting(session: Session = Depends(get_session)):
    return _to_out(_get_or_create(session))


@router.put("", response_model=LLMSettingOut)
def update_setting(payload: LLMSettingIn, session: Session = Depends(get_session)):
    setting = _get_or_create(session)
    setting.provider = payload.provider
    setting.base_url = payload.base_url.strip()
    setting.model = payload.model.strip()
    setting.temperature = payload.temperature
    setting.max_tokens = payload.max_tokens
    setting.concurrency = max(1, payload.concurrency)
    setting.timeout = max(5, payload.timeout)
    setting.local_enabled = payload.local_enabled
    setting.local_model = payload.local_model.strip() or "uer/gpt2-chinese-cluecorpussmall"
    setting.local_dtype = payload.local_dtype or "float16"
    setting.ppl_min = max(1.0, payload.ppl_min)
    setting.ppl_retry = max(0, min(5, payload.ppl_retry))
    setting.ppl_severe = max(1.0, min(payload.ppl_min, payload.ppl_severe))
    if payload.api_key is not None and payload.api_key.strip():
        setting.api_key_enc = encrypt(payload.api_key.strip())
    session.add(setting)
    session.commit()
    session.refresh(setting)
    return _to_out(setting)


@router.delete("/key", response_model=LLMSettingOut)
def clear_key(session: Session = Depends(get_session)):
    setting = _get_or_create(session)
    setting.api_key_enc = ""
    session.add(setting)
    session.commit()
    session.refresh(setting)
    return _to_out(setting)


@router.post("/test", response_model=LLMTestOut)
async def test_setting(payload: LLMTestIn, session: Session = Depends(get_session)):
    api_key = payload.api_key.strip() if payload.api_key else ""
    if not api_key:
        setting = _get_or_create(session)
        api_key = decrypt(setting.api_key_enc)
    if not api_key:
        raise HTTPException(status_code=400, detail="请填写 API Key")

    engine = LLMEngine(
        base_url=payload.base_url,
        api_key=api_key,
        model=payload.model,
        temperature=0,
        max_tokens=32,
        timeout=30,
    )
    start = time.perf_counter()
    try:
        await engine.ping()
    except LLMError as exc:
        return LLMTestOut(ok=False, message=str(exc), latency_ms=int((time.perf_counter() - start) * 1000))
    return LLMTestOut(ok=True, message="连接成功", latency_ms=int((time.perf_counter() - start) * 1000))


@router.get("/models")
async def list_models(session: Session = Depends(get_session)):
    setting = _get_or_create(session)
    api_key = decrypt(setting.api_key_enc)
    if not api_key:
        raise HTTPException(status_code=400, detail="请先保存 API Key")
    url = f"{setting.base_url.rstrip('/')}/models"
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(url, headers={"Authorization": f"Bearer {api_key}"})
        if resp.status_code >= 400:
            raise HTTPException(status_code=400, detail=f"获取模型列表失败：{resp.status_code}")
        data = resp.json()
        models = [item.get("id") for item in data.get("data", []) if item.get("id")]
        return {"models": sorted(models)}
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"获取模型列表失败：{exc}") from exc


@router.get("/local/status", response_model=LocalModelStatusOut)
def local_status():
    return local_model.status()


@router.post("/local/load", response_model=LocalModelStatusOut)
def local_load(payload: LocalModelLoadIn, session: Session = Depends(get_session)):
    setting = _get_or_create(session)
    model_name = (payload.model or setting.local_model or "").strip()
    dtype = (payload.dtype or setting.local_dtype or "float32").strip()
    if not model_name:
        raise HTTPException(status_code=400, detail="请填写本地模型名称")
    if dtype == "float32":
        raise HTTPException(
            status_code=400,
            detail="当前环境内存有限，float32 会在加载时被 OOM 杀掉，请改用 float16 或 bfloat16",
        )
    local_model.load_model_async(model_name, dtype)
    return local_model.status()


@router.post("/local/unload", response_model=LocalModelStatusOut)
def local_unload():
    local_model.unload_model()
    return local_model.status()


@router.post("/perplexity", response_model=PerplexityResult)
def perplexity(payload: PerplexityRequest):
    if not payload.text or not payload.text.strip():
        raise HTTPException(status_code=400, detail="请输入需要计算的文本")
    try:
        return local_model.summarize(
            payload.text, max_sentences=max(1, min(payload.max_sentences, 100))
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"本地模型未就绪：{exc}") from exc


@router.get("/local/files")
def local_files(session: Session = Depends(get_session)):
    setting = _get_or_create(session)
    from ..services.local_model import MODEL_DIR, _safe_dir_name

    path = MODEL_DIR / _safe_dir_name(setting.local_model)
    files = list(path.glob("*")) if path.exists() else []
    size = sum(item.stat().st_size for item in files if item.is_file())
    return {
        "path": str(path),
        "exists": (path / "model.safetensors").exists(),
        "size_mb": round(size / 1e6, 1),
        "files": [item.name for item in files],
    }
