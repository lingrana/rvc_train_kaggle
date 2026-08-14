"""Atomic, normalized progress reporting for the RVC training pipeline."""

from __future__ import annotations

from typing import Any

import json
import time
from pathlib import Path

from ultimate_rvc.rvc.train.delivery import atomic_json_dump
from ultimate_rvc.security import directory_lock

PHASE_LABELS = {
    "starting": "正在启动训练",
    "preprocessing": "正在预处理",
    "extracting": "正在提取特征",
    "training": "正在训练",
    "indexing": "正在生成索引",
    "validating": "正在验证本地推理兼容性",
    "uploading": "正在上传 Kaggle Dataset",
    "completed": "训练完成，可以下载",
    "stopped": "训练已停止",
    "failed": "训练失败",
}
TERMINAL_PHASES = frozenset({"completed", "stopped", "failed"})


def _number(value: Any, default: float = 0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def read_progress(path: Path) -> dict[str, Any]:
    """Read and normalize progress while accepting the legacy schema."""
    try:
        with path.open("r", encoding="utf-8") as file:
            raw = json.load(file)
        if not isinstance(raw, dict):
            raw = {}
    except (OSError, ValueError, TypeError):
        raw = {}
    total = int(_number(raw.get("total_epochs", raw.get("total", 0))))
    epoch = int(_number(raw.get("epoch", 0)))
    phase = str(raw.get("phase") or ("completed" if raw.get("done") else "training"))
    if phase not in PHASE_LABELS:
        phase = "training"
    raw.update(
        phase=phase,
        phase_label=PHASE_LABELS[phase],
        epoch=epoch,
        total_epochs=total,
        total=total,
        batch=int(_number(raw.get("batch", 0))),
        total_batches=int(_number(raw.get("total_batches", 0))),
        done=bool(raw.get("done", False)) and phase in {"completed", "uploading"},
    )
    raw["percent"] = max(
        0.0,
        min(100.0, _number(raw.get("percent"), epoch * 100 / total if total else 0)),
    )
    raw.setdefault("warning", "")
    raw.setdefault("error", "")
    raw.setdefault("recent_log", [])
    return raw


def update_progress(model_dir: Path, **changes: Any) -> dict[str, Any]:
    """Merge changes into progress.json and refresh its timestamps atomically."""
    path = model_dir / "progress.json"
    with directory_lock(model_dir / ".progress.lock", timeout=10, stale_after=300):
        state = read_progress(path) if path.is_file() else {}
        now = time.time()
        state.update(changes)
        phase = str(state.get("phase", "starting"))
        if phase not in PHASE_LABELS:
            raise ValueError(f"Unknown training phase: {phase}")
        total = int(_number(state.get("total_epochs", state.get("total", 0))))
        epoch = int(_number(state.get("epoch", 0)))
        batch = int(_number(state.get("batch", 0)))
        total_batches = int(_number(state.get("total_batches", 0)))
        if "percent" not in changes:
            partial = batch / total_batches if total_batches else 0
            state["percent"] = min(100.0, ((epoch + partial) / total * 100) if total else 0)
        state.update(
            phase=phase,
            phase_label=PHASE_LABELS[phase],
            total_epochs=total,
            total=total,
            done=bool(state.get("done", False)) and phase in {"completed", "uploading"},
            heartbeat_at=now,
            updated_at=now,
        )
        log = state.get("recent_log", [])
        if isinstance(log, str):
            log = log.splitlines()
        state["recent_log"] = [str(line)[-1000:] for line in list(log)[-20:]]
        atomic_json_dump(state, path)
        return state


def initialize_progress(model_dir: Path, total_epochs: int) -> dict[str, Any]:
    return update_progress(
        model_dir,
        phase="starting",
        epoch=0,
        total_epochs=total_epochs,
        batch=0,
        total_batches=0,
        percent=0,
        elapsed_seconds=0,
        eta_seconds=0,
        warning="",
        error="",
        recent_log=[],
        done=False,
        started_at=time.time(),
    )


def tail_log(path: Path, max_lines: int = 20, max_bytes: int = 32_768) -> list[str]:
    """Read a bounded UTF-8 tail without loading a large training log."""
    try:
        with path.open("rb") as file:
            file.seek(0, 2)
            size = file.tell()
            file.seek(max(0, size - max_bytes))
            data = file.read()
        text = data.decode("utf-8", errors="replace")
        if size > max_bytes and "\n" in text:
            text = text.split("\n", 1)[1]
        return text.splitlines()[-max_lines:]
    except OSError:
        return []


_ERROR_HINTS = (
    "traceback",
    "runtimeerror",
    "exception",
    "cuda",
    "out of memory",
    "oom",
    "failed",
    "nan",
    "nccl",
    "error",
    "rank ",
    "exited with code",
    "segmentation",
    "signal",
    "crash",
)


def tail_log_with_errors(
    path: Path,
    max_lines: int = 30,
    max_hits: int = 20,
    context: int = 2,
    max_bytes: int = 1_048_576,
) -> list[str]:
    """Tail a log but prefer error-like lines when present.

    Error summaries can sit far from the physical end of the log (for example
    a `RuntimeError: One or more training processes failed.` after hundreds of
    lazy-loader warnings), so a plain tail often hides the root cause. Scans a
    bounded tail window for error hints and returns the last hits followed by
    a few lines of context; falls back to a plain tail when nothing matches.
    """
    try:
        with path.open("rb") as file:
            file.seek(0, 2)
            size = file.tell()
            file.seek(max(0, size - max_bytes))
            data = file.read()
        text = data.decode("utf-8", errors="replace")
        lines = text.splitlines()
        if size > max_bytes:
            lines = lines[1:]
        hits = [i for i, line in enumerate(lines) if any(h in line.lower() for h in _ERROR_HINTS)]
        if not hits:
            return lines[-max_lines:]
        seen = set()
        out = []
        for i in hits[-max_hits:]:
            for k in range(i, min(len(lines), i + context + 1)):
                line = lines[k].strip()
                if line and line not in seen:
                    seen.add(line)
                    out.append(line)
        return out[-max_lines:]
    except OSError:
        return []


def mark_failed(model_dir: Path, error: BaseException | str) -> dict[str, Any]:
    return update_progress(model_dir, phase="failed", error=str(error), done=False)


def mark_stopped(model_dir: Path) -> dict[str, Any]:
    return update_progress(model_dir, phase="stopped", done=False)
