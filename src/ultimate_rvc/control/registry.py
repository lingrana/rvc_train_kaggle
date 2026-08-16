"""Persistent, per-dataset training registry for the RVC control plane.

Each confirmed dataset is recorded here together with the progress of the
four pipeline stages (upload / preprocess / extract / train). The registry survives
browser refreshes and control-service restarts, so the UI can always answer
"which stage is each dataset at, and how long did each stage take".
"""

from __future__ import annotations

import time
from typing import Any

from ultimate_rvc.common import TRAINING_MODELS_DIR
from ultimate_rvc.rvc.train.delivery import atomic_json_dump, validate_model_name
from ultimate_rvc.security import directory_lock

REGISTRY_PATH = TRAINING_MODELS_DIR / "registry.json"
STAGE_KEYS = ("upload", "preprocess", "extract", "train")
STAGE_LABELS = {
    "upload": "上传音频",
    "preprocess": "数据预处理",
    "extract": "特征提取",
    "train": "模型训练",
}

_STAGE_DEFAULTS = {"done": False, "finished_at": None, "elapsed_seconds": None}


def _locked():
    """Ensure the registry directory exists, then return the write lock."""
    REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    return directory_lock(REGISTRY_PATH.parent / ".registry.lock", timeout=10, stale_after=300)


def _normalize(entry: dict[str, Any]) -> dict[str, Any]:
    stages = entry.get("stages") or {}
    stages = {
        key: {
            **_STAGE_DEFAULTS,
            **(stages.get(key) if isinstance(stages.get(key), dict) else {}),
        }
        for key in STAGE_KEYS
    }
    return {
        "dataset": str(entry.get("dataset", "")),
        "created_at": float(entry.get("created_at", 0)),
        "updated_at": float(entry.get("updated_at", 0)),
        "last_phase": str(entry.get("last_phase", "")),
        "stages": stages,
    }


def read_registry() -> dict[str, dict[str, Any]]:
    """Return the normalized registry keyed by model/dataset name."""
    try:
        raw = REGISTRY_PATH.read_text("utf-8")
    except OSError:
        return {}
    try:
        data = __import__("json").loads(raw)
    except (ValueError, TypeError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(name): _normalize(entry) for name, entry in data.items() if isinstance(entry, dict)}


def _write_registry(entries: dict[str, dict[str, Any]]) -> None:
    REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    atomic_json_dump(entries, REGISTRY_PATH)


def register_dataset(dataset: str) -> dict[str, Any]:
    """Record a confirmed dataset so it reappears as a selectable model."""
    dataset = validate_model_name(dataset)
    with _locked():
        entries = read_registry()
        entry = entries.get(dataset)
        if entry is None:
            now = time.time()
            entry = _normalize(
                {"dataset": dataset, "created_at": now, "updated_at": now, "stages": {}}
            )
            entries[dataset] = entry
        _write_registry(entries)
    return _normalize(entry)


def reset_stage(model_name: str, stage: str) -> dict[str, Any]:
    """Clear a stage's completion state so a re-run shows live progress again."""
    model_name = validate_model_name(model_name)
    if stage not in STAGE_KEYS:
        raise ValueError(f"未知训练阶段: {stage}")
    with _locked():
        entries = read_registry()
        entry = entries.get(model_name)
        if entry is None:
            return _normalize({"dataset": model_name, "created_at": time.time(), "stages": {}})
        entry["stages"][stage] = dict(_STAGE_DEFAULTS)
        entry["updated_at"] = time.time()
        entries[model_name] = entry
        _write_registry(entries)
        return _normalize(entry)


def mark_stage(model_name: str, stage: str, elapsed_seconds: float | None = None) -> dict[str, Any]:
    """Mark one pipeline stage as finished, recording its duration."""
    model_name = validate_model_name(model_name)
    if stage not in STAGE_KEYS:
        raise ValueError(f"未知训练阶段: {stage}")
    with _locked():
        entries = read_registry()
        entry = entries.get(model_name) or _normalize(
            {"dataset": model_name, "created_at": time.time(), "stages": {}}
        )
        stage_state = _STAGE_DEFAULTS | dict(entry["stages"].get(stage, {}))
        stage_state.update(
            done=True,
            finished_at=time.time(),
            elapsed_seconds=elapsed_seconds if elapsed_seconds is not None else stage_state.get("elapsed_seconds"),
        )
        entry["stages"][stage] = stage_state
        entry["last_phase"] = stage
        entry["updated_at"] = time.time()
        entries[model_name] = entry
        _write_registry(entries)
        return _normalize(entry)


def set_last_phase(model_name: str, phase: str) -> None:
    """Track the current progress.json phase so the UI can show it after restarts."""
    model_name = validate_model_name(model_name)
    with _locked():
        entries = read_registry()
        entry = entries.get(model_name)
        if entry is None:
            return
        entry["last_phase"] = str(phase)
        entry["updated_at"] = time.time()
        entries[model_name] = entry
        _write_registry(entries)
