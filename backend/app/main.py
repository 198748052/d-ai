from __future__ import annotations

from contextlib import asynccontextmanager

import traceback

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import Session

from .core.config import CORS_ORIGINS
from .db.database import engine, init_db
from .models.models import LLMSetting
from .routers import (
    admin,
    auth,
    credits,
    detector,
    errors,
    export,
    features,
    lessons,
    llm,
    presets,
    rewrite,
    update,
)
from .services.errors import record_error
from .services import local_model
from .services.seed import seed


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    with Session(engine) as session:
        seed(session)
        setting = session.get(LLMSetting, 1)
        if setting and getattr(setting, "local_enabled", False):
            local_model.load_model_async(setting.local_model, setting.local_dtype)
    yield


app = FastAPI(title="降AI味改写平台", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(rewrite.router)
app.include_router(llm.router)
app.include_router(features.router)
app.include_router(presets.router)
app.include_router(export.router)
app.include_router(lessons.router)
app.include_router(auth.router)
app.include_router(credits.router)
app.include_router(detector.router)
app.include_router(admin.router)
app.include_router(update.router)
app.include_router(update.webhook_router)
app.include_router(errors.router)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    record_error(
        f"未处理异常：{type(exc).__name__}: {exc}",
        detail=traceback.format_exc(),
        source="server",
        path=str(request.url.path),
    )
    return JSONResponse(status_code=500, content={"detail": "服务器内部错误，已记录"})


@app.get("/api/health")
def health():
    return {"status": "ok"}
