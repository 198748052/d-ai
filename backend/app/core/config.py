from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.getenv("APP_DATA_DIR", BASE_DIR.parent / "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

DB_PATH = DATA_DIR / "app.db"
SECRET_KEY_PATH = DATA_DIR / "secret.key"

APP_DIR = BASE_DIR / "app"
LEXICON_DIR = APP_DIR / "data" / "lexicons"
PATTERN_DIR = APP_DIR / "data" / "patterns"

DEFAULT_LLM_BASE_URL = os.getenv("LLM_DEFAULT_BASE_URL", "https://api.openai.com/v1")
DEFAULT_LLM_MODEL = os.getenv("LLM_DEFAULT_MODEL", "gpt-4o-mini")
FIXED_REASONING_EFFORT = "low"

MAX_INPUT_CHARS = int(os.getenv("MAX_INPUT_CHARS", "256000"))

SMTP_HOST = os.getenv("SMTP_HOST", "smtp.qq.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "465"))
SMTP_USER = os.getenv("SMTP_USER", "").strip()
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "").strip()
SMTP_FROM = os.getenv("SMTP_FROM", "").strip() or SMTP_USER
EMAIL_CODE_ECHO = os.getenv("EMAIL_CODE_ECHO", "0").strip() in {"1", "true", "yes"}
ALERT_WEBHOOK_URL = os.getenv("ALERT_WEBHOOK_URL", "").strip()

DEFAULT_LOCAL_MODEL = os.getenv("LOCAL_MODEL", "Qwen/Qwen2.5-1.5B")
DEFAULT_LOCAL_DTYPE = os.getenv("LOCAL_DTYPE", "float16")
DEFAULT_LOCAL_ENABLED = os.getenv("LOCAL_ENABLED", "0").strip() in {"1", "true", "yes"}

CORS_ORIGINS = [
    "http://localhost:18437",
    "http://127.0.0.1:18437",
]
