"""Disk-backed process jobs which survive browser and web-service reconnects."""

from __future__ import annotations

from typing import Any

import json
import os
import signal
import subprocess
import sys
import time
import uuid
from pathlib import Path

from ultimate_rvc.common import TEMP_DIR, TRAINING_MODELS_DIR
from ultimate_rvc.rvc.train.delivery import atomic_json_dump, validate_model_name
from ultimate_rvc.rvc.train.progress import read_progress
from ultimate_rvc.security import directory_lock

CONTROL_DIR = TEMP_DIR / "control"
JOBS_DIR = CONTROL_DIR / "jobs"
UPLOADS_DIR = CONTROL_DIR / "uploads"
ACTIVE_PHASES = frozenset({"queued", "running", "stopping"})
JOB_TYPES = frozenset({"preprocess", "extract", "train", "pipeline"})


def validate_job_params(kind: str, params: dict[str, Any]) -> None:
    """Reject malformed resource settings before occupying the single job slot."""
    if kind in {"preprocess", "pipeline"}:
        dataset = Path(str(params.get("dataset", "")))
        if not dataset.is_dir():
            raise ValueError("数据集不存在，请先上传音频或选择现有数据集")
        if int(params.get("sample_rate", 48000)) not in {32000, 40000, 48000}:
            raise ValueError("不支持的训练采样率")
    if kind in {"train", "pipeline"}:
        epochs = int(params.get("epochs", 300))
        batch_size = int(params.get("batch_size", 8))
        save_interval = int(params.get("save_interval", 25))
        if not 1 <= epochs <= 1000 or not 1 <= batch_size <= 64:
            raise ValueError("训练轮数或批次大小超出范围")
        if not 1 <= save_interval <= 100:
            raise ValueError("保存间隔超出范围")
    for key in ("extraction_gpu_ids", "training_gpu_ids", "gpu_ids"):
        if any(not isinstance(value, int) or value < 0 for value in params.get(key, [])):
            raise ValueError("GPU ID 必须是非负整数")


def _job_path(job_id: str) -> Path:
    try:
        uuid.UUID(job_id)
    except ValueError as error:
        raise ValueError("无效任务 ID") from error
    return JOBS_DIR / job_id / "job.json"


def pid_alive(pid: Any) -> bool:
    try:
        os.kill(int(pid), 0)
        return True
    except (OSError, TypeError, ValueError):
        return False


def read_job(job_id: str) -> dict[str, Any]:
    path = _job_path(job_id)
    try:
        data = json.loads(path.read_text("utf-8"))
    except (OSError, ValueError, TypeError) as error:
        raise FileNotFoundError("任务不存在") from error
    return refresh_job(data)


def refresh_job(job: dict[str, Any]) -> dict[str, Any]:
    phase = job.get("phase")
    alive = pid_alive(job.get("pid"))
    result_path = JOBS_DIR / str(job["id"]) / "result.json"
    result_exists = result_path.is_file()
    if phase in ACTIVE_PHASES and job.get("pid") and alive and not result_exists and os.name != "nt":
        try:
            waited, _ = os.waitpid(int(job["pid"]), os.WNOHANG)
            if waited:
                alive = False
        except (ChildProcessError, OSError, ValueError):
            pass
    if phase in ACTIVE_PHASES and job.get("pid") and (result_exists or not alive):
        try:
            result = json.loads(result_path.read_text("utf-8"))
        except (OSError, ValueError, TypeError):
            result = {"ok": False, "error": "任务进程已退出，未留下完成状态"}
        job.update(
            phase="completed" if result.get("ok") else "failed",
            error=str(result.get("error", "")),
            result=result.get("result"),
            finished_at=result.get("finished_at", time.time()),
            updated_at=time.time(),
        )
        atomic_json_dump(job, _job_path(str(job["id"])))
        if job["phase"] == "failed":
            log_path = JOBS_DIR / str(job["id"]) / "worker.log"
            try:
                from ultimate_rvc.rvc.train.progress import tail_log_with_errors

                job["log_tail"] = tail_log_with_errors(log_path)
            except Exception:
                try:
                    job["log_tail"] = log_path.read_text("utf-8", errors="replace").splitlines()[-30:]
                except OSError:
                    job["log_tail"] = []
    model_name = job.get("params", {}).get("model_name")
    if model_name:
        progress_path = TRAINING_MODELS_DIR / str(model_name) / "progress.json"
        if progress_path.is_file():
            job["progress"] = read_progress(progress_path)
        try:
            from ultimate_rvc.control.registry import read_registry

            registry_entry = read_registry().get(str(model_name))
            if registry_entry:
                job["stages"] = registry_entry.get("stages")
        except Exception:
            pass
        if job.get("phase") == "completed":
            try:
                from ultimate_rvc.rvc.train.delivery import delivery_files

                files = delivery_files(TRAINING_MODELS_DIR / str(model_name), str(model_name))
                job["files"] = {kind: path.is_file() for kind, path in files.items()}
            except Exception:
                pass
            try:
                cached_urls = json.loads(
                    (TRAINING_MODELS_DIR / str(model_name) / "kaggle_urls.json").read_text("utf-8")
                )
                if cached_urls.get("kaggle"):
                    job["kaggle_url"] = str(cached_urls["kaggle"])
            except (OSError, ValueError, TypeError):
                pass
    job["alive"] = alive
    return job


def update_job(job_id: str, **changes: Any) -> dict[str, Any]:
    job = read_job(job_id)
    job.pop("progress", None)
    job.pop("alive", None)
    job.pop("stages", None)
    job.update(changes, updated_at=time.time())
    atomic_json_dump(job, _job_path(job_id))
    return job


def list_jobs() -> list[dict[str, Any]]:
    JOBS_DIR.mkdir(parents=True, exist_ok=True)
    jobs = []
    for path in JOBS_DIR.glob("*/job.json"):
        try:
            jobs.append(refresh_job(json.loads(path.read_text("utf-8"))))
        except (OSError, ValueError, TypeError):
            continue
    return sorted(jobs, key=lambda item: float(item.get("created_at", 0)), reverse=True)


def active_job() -> dict[str, Any] | None:
    return next((job for job in list_jobs() if job.get("phase") in ACTIVE_PHASES), None)


def create_job(kind: str, params: dict[str, Any], idempotency_key: str = "") -> tuple[dict[str, Any], bool]:
    if kind not in JOB_TYPES:
        raise ValueError("不支持的任务类型")
    model_name = validate_model_name(str(params.get("model_name", "")))
    params["model_name"] = model_name
    validate_job_params(kind, params)
    with directory_lock(CONTROL_DIR / "scheduler.lock", timeout=5):
        for existing in list_jobs():
            if idempotency_key and existing.get("idempotency_key") == idempotency_key:
                return existing, False
        running = active_job()
        if running:
            return running, False
        job_id = str(uuid.uuid4())
        job_dir = JOBS_DIR / job_id
        job_dir.mkdir(parents=True)
        now = time.time()
        job = {
            "id": job_id,
            "type": kind,
            "phase": "queued",
            "params": params,
            "idempotency_key": idempotency_key,
            "pid": None,
            "created_at": now,
            "updated_at": now,
            "error": "",
        }
        atomic_json_dump(job, job_dir / "job.json")
        environment = os.environ.copy()
        # Serialize CUDA kernels so a segfaulting op surfaces in the Python
        # stack (faulthandler) instead of dying in a driver background thread.
        environment.setdefault("CUDA_LAUNCH_BLOCKING", "1")
        # Prevent numba and jax from initializing their own CUDA contexts,
        # which conflict with PyTorch's CUDA context and cause segfaults.
        environment["NUMBA_DISABLE_CUDA"] = "1"
        environment["JAX_PLATFORMS"] = "cpu"
        # Disable torch.compile / dynamo — its lazy import of triton segfaults
        # on Kaggle due to incompatible triton C extensions.
        environment["TORCHDYNAMO_DISABLE"] = "1"
        command = [sys.executable, "-m", "ultimate_rvc.control.worker", job_id]
        log = (job_dir / "worker.log").open("a", encoding="utf-8")
        flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) if os.name == "nt" else 0
        try:
            process = subprocess.Popen(
                command,
                cwd=Path.cwd(),
                env=environment,
                stdout=log,
                stderr=subprocess.STDOUT,
                start_new_session=os.name != "nt",
                creationflags=flags,
            )
        finally:
            log.close()
        job.update(pid=process.pid, phase="running", updated_at=time.time())
        atomic_json_dump(job, job_dir / "job.json")
        return job, True


def stop_job(job_id: str) -> dict[str, Any]:
    job = read_job(job_id)
    if job.get("phase") not in ACTIVE_PHASES:
        return job
    job.update(phase="stopping", updated_at=time.time())
    atomic_json_dump(job, _job_path(job_id))
    model_name = str(job.get("params", {}).get("model_name", ""))
    if model_name:
        try:
            from ultimate_rvc.core.train.train import stop_training

            stop_training(model_name)
        except Exception as error:
            job.update(error=f"停止训练子进程失败：{error}")
    pid = int(job.get("pid") or 0)
    if pid_alive(pid):
        try:
            if os.name == "nt":
                os.kill(pid, signal.CTRL_BREAK_EVENT)
            else:
                os.killpg(pid, signal.SIGTERM)
        except OSError as error:
            job.update(error=f"发送停止信号失败：{error}")
    deadline = time.monotonic() + 5
    while pid_alive(pid) and time.monotonic() < deadline:
        time.sleep(0.1)
    phase = "failed" if pid_alive(pid) else "stopped"
    if phase == "failed" and not job.get("error"):
        job["error"] = "训练进程未在超时前退出"
    job.update(phase=phase, finished_at=time.time(), updated_at=time.time())
    atomic_json_dump(job, _job_path(job_id))
    return job
