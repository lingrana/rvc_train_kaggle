"""Atomic, normalized progress reporting for the RVC training pipeline."""

from __future__ import annotations

from typing import Any

import json
import math
import time
from pathlib import Path

from ultimate_rvc.rvc.train.delivery import atomic_json_dump
from ultimate_rvc.security import directory_lock

PHASE_LABELS = {
    "starting": "步骤4 · 准备环境",
    "uploading_file": "步骤1 · 上传音频",
    "upload_validating": "步骤1 · 校验文件",
    "preparing": "步骤2 · 准备环境",
    "preprocessing": "步骤2 · 扫描文件",
    "extracting": "步骤3 · 基频提取",
    "extracting_pitch": "步骤3 · 基频提取",
    "extracting_embed": "步骤3 · 特征提取",
    "extracting_verify": "步骤3 · 特征校验",
    "training": "步骤4 · 准备环境",
    "indexing": "步骤4 · 生成索引",
    "validating": "步骤4 · 验证模型",
    "uploading": "步骤4 · 上传模型",
    "completed": "步骤4 · 训练完成",
    "stopped": "步骤4 · 已经停止",
    "failed": "步骤4 · 执行失败",
}
TERMINAL_PHASES = frozenset({"completed", "stopped", "failed"})


def _number(value: Any, default: float = 0) -> float:
    try:
        number = float(value)
        return number if math.isfinite(number) else default
    except (TypeError, ValueError):
        return default


def phase_label_for(phase: str, percent: float, done: bool = False) -> str:
    """Return the four-character label for a phase/percentage milestone."""
    percent = max(0.0, min(100.0, _number(percent)))
    if phase in {"uploading_file", "upload_validating"}:
        if done or percent >= 100:
            return "步骤1 · 上传完成"
        return "步骤1 · 校验文件" if percent >= 98 else "步骤1 · 上传音频"
    if phase in {"preparing", "preprocessing"}:
        if done or percent >= 100:
            return "步骤2 · 处理完成"
        if percent >= 70:
            return "步骤2 · 写入结果"
        if percent >= 50:
            return "步骤2 · 切片处理"
        if percent >= 30:
            return "步骤2 · 准备切片"
        return "步骤2 · 准备环境" if phase == "preparing" else "步骤2 · 扫描文件"
    if phase in {"extracting", "extracting_pitch", "extracting_embed", "extracting_verify"}:
        if done or percent >= 100:
            return "步骤3 · 提取完成"
        if phase == "extracting_verify" or percent >= 95:
            return "步骤3 · 特征校验"
        if phase in {"extracting_embed"} or percent >= 45:
            return "步骤3 · 特征提取"
        return "步骤3 · 基频提取"
    if phase in {"starting", "training", "indexing", "validating", "uploading", "completed"}:
        if done or phase == "completed" or percent >= 100:
            return "步骤4 · 训练完成"
        if phase == "uploading" or percent >= 98:
            return "步骤4 · 上传模型"
        if phase == "validating" or percent >= 95:
            return "步骤4 · 验证模型"
        if phase == "indexing" or percent >= 90:
            return "步骤4 · 生成索引"
        if phase == "training" and percent >= 5:
            return "步骤4 · 模型训练"
        if phase == "training" and percent >= 2:
            return "步骤4 · 加载模型"
        return "步骤4 · 准备环境"
    return PHASE_LABELS.get(phase, "")


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
    phase_label = str(raw.get("phase_label") or PHASE_LABELS[phase])
    raw.update(
        phase=phase,
        phase_label=phase_label,
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
    raw.setdefault("elapsed_seconds", 0)
    raw.setdefault("eta_seconds", 0)
    raw.setdefault("phase_started_at", 0)
    raw.setdefault("phase_elapsed_seconds", 0)
    raw.setdefault("stage_started_at", raw.get("started_at", 0))
    raw.setdefault("stage_elapsed_seconds", raw.get("elapsed_seconds", 0))
    raw.setdefault("upload_failed", False)
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
        previous_phase = str(state.get("phase", "starting"))
        reset_percent = bool(changes.pop("reset_percent", False))
        state.update(changes)
        phase = str(state.get("phase", "starting"))
        if phase not in PHASE_LABELS:
            raise ValueError(f"Unknown training phase: {phase}")
        if phase != previous_phase:
            state["phase_started_at"] = now
        if not _number(state.get("started_at", 0)):
            state["started_at"] = now
        total = int(_number(state.get("total_epochs", state.get("total", 0))))
        epoch = int(_number(state.get("epoch", 0)))
        batch = int(_number(state.get("batch", 0)))
        total_batches = int(_number(state.get("total_batches", 0)))
        if "percent" not in changes:
            partial = batch / total_batches if total_batches else 0
            raw_percent = ((epoch + partial) / total * 100) if total else 0
            if phase == "training":
                state["percent"] = min(90.0, 5.0 + raw_percent * 0.85)
            elif phase == "indexing":
                state["percent"] = 90.0
            elif phase == "validating":
                state["percent"] = 95.0
            else:
                state["percent"] = min(100.0, raw_percent)
        elif (
            not reset_percent
            and phase == previous_phase
            and phase in {"preprocessing", "extracting", "extracting_pitch", "extracting_embed", "extracting_verify", "uploading_file"}
        ):
            state["percent"] = max(
                _number(state.get("percent"), 0),
                _number(changes.get("percent"), 0),
            )
        if "elapsed_seconds" not in changes:
            started_at = _number(state.get("started_at", 0))
            state["elapsed_seconds"] = round(max(0.0, now - started_at), 1) if started_at else 0
        stage_started_at = _number(state.get("stage_started_at", 0))
        if not stage_started_at:
            stage_started_at = now
            state["stage_started_at"] = stage_started_at
        state["stage_elapsed_seconds"] = round(max(0.0, now - stage_started_at), 1)
        if phase == "completed":
            state["percent"] = 100.0
        phase_started_at = _number(state.get("phase_started_at", 0))
        state["phase_elapsed_seconds"] = (
            round(max(0.0, now - phase_started_at), 1) if phase_started_at else 0
        )
        state.update(
            phase=phase,
            phase_label=phase_label_for(
                phase,
                state.get("percent", 0),
                bool(state.get("done", False)),
            ) or str(state.get("phase_label") or PHASE_LABELS[phase]),
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


def initialize_progress(
    model_dir: Path,
    total_epochs: int,
    started_at: float | None = None,
    stage_started_at: float | None = None,
    phase: str = "starting",
) -> dict[str, Any]:
    effective_started_at = started_at or time.time()
    effective_stage_started_at = stage_started_at or effective_started_at
    initial_elapsed = max(0.0, time.time() - effective_started_at)
    return update_progress(
        model_dir,
        phase=phase,
        epoch=0,
        total_epochs=total_epochs,
        batch=0,
        total_batches=0,
        percent=0,
        elapsed_seconds=initial_elapsed,
        eta_seconds=0,
        warning="",
        error="",
        recent_log=[],
        done=False,
        started_at=effective_started_at,
        stage_started_at=effective_stage_started_at,
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
