from __future__ import annotations

import gc
import math
import re
import os
import threading
import time
from pathlib import Path

from .rewriter.timing import add_ppl

os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")

_lock = threading.Lock()
_model = None
_tokenizer = None
_loaded_name: str | None = None
_loaded_dtype: str | None = None
_loading = False
_load_error: str | None = None
_progress: str = ""

MODELSCOPE_FILES = [
    "config.json",
    "generation_config.json",
    "merges.txt",
    "model.safetensors",
    "tokenizer.json",
    "tokenizer_config.json",
    "vocab.json",
]

DATA_DIR = Path(os.getenv("APP_DATA_DIR", Path(__file__).resolve().parents[3] / "data"))
MODEL_DIR = DATA_DIR / "models"


def _resolve_dtype(name: str):
    import torch

    if name == "float16":
        return torch.float16
    if name == "bfloat16":
        return torch.bfloat16
    return torch.float32


def _safe_dir_name(model_name: str) -> str:
    return model_name.replace("/", "__").replace("\\", "__")


def _download_modelscope(model_name: str, target: Path) -> Path:
    global _progress
    import httpx

    target.mkdir(parents=True, exist_ok=True)
    base = f"https://www.modelscope.cn/api/v1/models/{model_name}/repo"
    for filename in MODELSCOPE_FILES:
        destination = target / filename
        if destination.exists() and destination.stat().st_size > 0:
            continue
        _progress = f"下载 {filename}"
        url = f"{base}?Revision=master&FilePath={filename}"
        with httpx.stream("GET", url, timeout=300, follow_redirects=True) as response:
            response.raise_for_status()
            total = int(response.headers.get("content-length") or 0)
            downloaded = 0
            with open(destination, "wb") as handle:
                for chunk in response.iter_bytes(1024 * 1024):
                    handle.write(chunk)
                    downloaded += len(chunk)
                    if total:
                        _progress = f"下载 {filename} {downloaded / 1e6:.1f}/{total / 1e6:.1f} MB"
        _progress = f"已下载 {filename}"
    return target


def _ensure_local_model(model_name: str) -> Path:
    path = Path(model_name)
    if path.exists():
        return path
    target = MODEL_DIR / _safe_dir_name(model_name)
    if (target / "config.json").exists() and (target / "model.safetensors").exists():
        return target
    return _download_modelscope(model_name, target)


def status() -> dict:
    return {
        "loaded": _model is not None,
        "loading": _loading,
        "model": _loaded_name,
        "dtype": _loaded_dtype,
        "error": _load_error,
        "progress": _progress,
    }


def load_model(model_name: str, dtype: str = "float16") -> dict:
    global _model, _tokenizer, _loaded_name, _loaded_dtype, _load_error, _progress

    with _lock:
        if _model is not None and _loaded_name == model_name and _loaded_dtype == dtype:
            return status()
        if _model is not None:
            # Free the old weights before loading, otherwise peak memory doubles and the process gets OOM-killed.
            _model = None
            _tokenizer = None
            _loaded_name = None
            _loaded_dtype = None
            gc.collect()
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        _progress = "准备下载/加载模型"
        local_dir = _ensure_local_model(model_name)
        _progress = "加载分词器"
        tokenizer = AutoTokenizer.from_pretrained(str(local_dir), trust_remote_code=True)
        _progress = "加载模型权重"
        kwargs = {
            "low_cpu_mem_usage": True,
            "trust_remote_code": True,
        }
        dtype_value = _resolve_dtype(dtype)
        try:
            model = AutoModelForCausalLM.from_pretrained(
                str(local_dir), torch_dtype=dtype_value, **kwargs
            )
        except TypeError:
            model = AutoModelForCausalLM.from_pretrained(
                str(local_dir), dtype=dtype_value, **kwargs
            )
        model.eval()

        _model = model
        _tokenizer = tokenizer
        _loaded_name = model_name
        _loaded_dtype = dtype
        _load_error = None
        _progress = "已加载"
        return status()


def load_model_async(model_name: str, dtype: str = "float16") -> None:
    global _loading, _load_error, _progress

    if _model is not None and _loaded_name == model_name and _loaded_dtype == dtype:
        _progress = "已加载"
        return
    if _loading:
        return

    def _worker() -> None:
        global _loading, _load_error
        try:
            load_model(model_name, dtype)
        except Exception as exc:  # noqa: BLE001
            _load_error = f"{type(exc).__name__}: {exc}"
            _progress = "加载失败"
        finally:
            _loading = False

    _loading = True
    _load_error = None
    _progress = "排队中"
    threading.Thread(target=_worker, daemon=True).start()


def unload_model() -> None:
    global _model, _tokenizer, _loaded_name, _loaded_dtype, _load_error, _progress

    with _lock:
        _model = None
        _tokenizer = None
        _loaded_name = None
        _loaded_dtype = None
        _load_error = None
        _progress = ""
    import gc

    gc.collect()


def _score(texts: list[str]) -> list[dict]:
    started = time.perf_counter()
    try:
        return _score_impl(texts)
    finally:
        add_ppl(time.perf_counter() - started)


def _score_impl(texts: list[str]) -> list[dict]:
    if _model is None or _tokenizer is None:
        raise RuntimeError("本地模型尚未加载")

    import torch

    results: list[dict] = []
    with _lock:
        with torch.no_grad():
            for text in texts:
                inputs = _tokenizer(
                    text,
                    return_tensors="pt",
                    truncation=True,
                    max_length=256,
                )
                if inputs["input_ids"].shape[1] < 4:
                    continue
                outputs = _model(**inputs, labels=inputs["input_ids"])
                loss = float(outputs.loss.item())
                perplexity = math.exp(min(loss, 20))
                results.append(
                    {
                        "sentence": text,
                        "perplexity": round(perplexity, 2),
                        "tokens": int(inputs["input_ids"].shape[1]),
                    }
                )
    return results


def sentence_perplexities(text: str, max_sentences: int = 40) -> list[dict]:
    from .segmenter import split_sentences

    sentences = [item for item in split_sentences(text) if item.strip()][:max_sentences]
    return _score(sentences)


_CLAUSE_BOUNDARY = re.compile(r"(?<=[，,；;：:])")


def clause_perplexities(text: str, max_clauses: int = 20, min_chars: int = 10) -> list[dict]:
    clauses = [item.strip() for item in _CLAUSE_BOUNDARY.split(text or "") if item.strip()]
    clauses = [item for item in clauses if len(item) >= min_chars][:max_clauses]
    if not clauses:
        return []
    return _score(clauses)


def summarize(text: str, max_sentences: int = 40, low_threshold: float = 50.0) -> dict:
    items = sentence_perplexities(text, max_sentences=max_sentences)
    if not items:
        return {"average": 0.0, "min": 0.0, "max": 0.0, "low_count": 0, "sentences": []}
    values = [item["perplexity"] for item in items]
    return {
        "average": round(sum(values) / len(values), 2),
        "min": round(min(values), 2),
        "max": round(max(values), 2),
        "low_count": sum(1 for value in values if value < low_threshold),
        "sentences": items,
    }
