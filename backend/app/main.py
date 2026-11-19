from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import Session

from .core.config import CORS_ORIGINS
from .db.database import engine, init_db
from .models.models import LLMSetting
from .routers import export, features, llm, presets, rewrite
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


@app.get("/api/health")
def health():
    return {"status": "ok"}
