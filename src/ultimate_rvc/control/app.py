"""FastAPI control plane for stable, reconnectable Kaggle training."""

from __future__ import annotations

from typing import Any

import argparse
import hashlib
import hmac
import json
import os
import re
import secrets
import shutil
import tempfile
import time
import uuid
import zipfile
from collections import defaultdict, deque
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, HTMLResponse
from starlette.background import BackgroundTask

from ultimate_rvc.common import AUDIO_DIR, BASE_DIR, TEMP_DIR, TRAINING_MODELS_DIR
from ultimate_rvc.control.jobs import (
    UPLOADS_DIR,
    create_job,
    list_jobs,
    read_job,
    stop_job,
)
from ultimate_rvc.control.registry import register_dataset
from ultimate_rvc.rvc.train.delivery import atomic_json_dump, delivery_files, validate_model_name
from ultimate_rvc.rvc.train.progress import read_progress
from ultimate_rvc.security import async_directory_lock, directory_lock

COOKIE_NAME = "rvc-control-session"
COOKIE_TTL = 24 * 60 * 60
MAX_UPLOAD_SIZE = 2 * 1024**3
MAX_OPEN_UPLOADS = 4
UPLOAD_TTL = 24 * 60 * 60
LOGIN_WINDOW = 5 * 60
LOGIN_ATTEMPTS = 8
TRAINING_AUDIO_DIR = AUDIO_DIR / "training"
app = FastAPI(title="RVC Training Control", docs_url=None, redoc_url=None)
_login_failures: dict[str, deque[float]] = defaultdict(deque)
_kaggle_setup_complete = False


def _display_path(path: Path) -> str:
    """Display paths relative to the runtime project root when possible."""
    try:
        return path.resolve().relative_to(BASE_DIR.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _remove_temp_file(path: str) -> None:
    Path(path).unlink(missing_ok=True)


def _secret() -> bytes:
    value = os.environ.get("RVC_CONTROL_SECRET", "")
    if len(value) < 32:
        raise RuntimeError("RVC_CONTROL_SECRET 必须至少包含 32 个字符")
    return value.encode()


def _token(username: str, expires: int) -> str:
    payload = f"{username}:{expires}"
    signature = hmac.new(_secret(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}:{signature}"


def _authenticated(request: Request) -> bool:
    token = request.cookies.get(COOKIE_NAME, "")
    try:
        username, expires, signature = token.rsplit(":", 2)
        expected = _token(username, int(expires)).rsplit(":", 1)[1]
        configured_user = os.environ.get("RVC_CONTROL_USER", "rvc")
        return (
            hmac.compare_digest(username, configured_user)
            and int(expires) >= time.time()
            and hmac.compare_digest(signature, expected)
        )
    except (RuntimeError, ValueError, TypeError):
        return False


@app.middleware("http")
async def authentication(request: Request, call_next):
    public = request.url.path in {
        "/",
        "/favicon.ico",
        "/api/v1/auth/login",
        "/api/v1/session",
        "/healthz",
    }
    if not public and not _authenticated(request):
        return Response('{"detail":"Not authenticated"}', status_code=401, media_type="application/json")
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Cache-Control", "no-store")
    return response


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    from ultimate_rvc.control.frontend import HTML

    return HTML


@app.get("/healthz")
def health() -> dict[str, bool]:
    return {"ok": True}


@app.get("/favicon.ico", status_code=204)
def favicon() -> Response:
    return Response(status_code=204)


@app.post("/api/v1/auth/login")
async def login(request: Request, response: Response) -> dict[str, bool]:
    client = request.client.host if request.client else "unknown"
    now = time.time()
    failures = _login_failures[client]
    while failures and failures[0] < now - LOGIN_WINDOW:
        failures.popleft()
    if len(failures) >= LOGIN_ATTEMPTS:
        raise HTTPException(429, "登录尝试过多，请稍后重试")
    body = await request.json()
    username = str(body.get("username", ""))
    password = str(body.get("password", ""))
    expected_user = os.environ.get("RVC_CONTROL_USER", "rvc")
    expected_password = os.environ.get("RVC_CONTROL_PASSWORD", "")
    if not expected_password or not (
        secrets.compare_digest(username, expected_user)
        and secrets.compare_digest(password, expected_password)
    ):
        failures.append(now)
        raise HTTPException(401, "用户名或密码错误")
    try:
        _secret()
    except RuntimeError as error:
        raise HTTPException(503, str(error)) from error
    failures.clear()
    expires = int(time.time()) + COOKIE_TTL
    response.set_cookie(
        COOKIE_NAME, _token(username, expires), max_age=COOKIE_TTL,
        httponly=True, secure=request.url.scheme == "https", samesite="strict", path="/",
    )
    return {"ok": True}


@app.post("/api/v1/auth/logout")
def logout(response: Response) -> dict[str, bool]:
    response.delete_cookie(COOKIE_NAME, path="/")
    return {"ok": True}


@app.get("/api/v1/session")
def session(request: Request) -> dict[str, bool]:
    return {"authenticated": _authenticated(request)}


@app.get("/api/v1/kaggle-auth")
def kaggle_auth_status() -> dict[str, Any]:
    return {
        "setup_required": not _kaggle_setup_complete,
        "configured": bool(os.environ.get("KAGGLE_API_TOKEN")),
        "owner": os.environ.get("RVC_KAGGLE_USERNAME"),
        "resume_dataset": os.environ.get("RVC_RESUME_DATASET") or None,
        "resume_enabled": bool(os.environ.get("RVC_RESUME_ROOT")),
    }


@app.post("/api/v1/kaggle-auth")
async def configure_kaggle_auth(request: Request) -> dict[str, Any]:
    """Validate a token and retain it only in this control-service process."""
    global _kaggle_setup_complete
    body = await request.json()
    token = str(body.get("token", "")).strip()
    has_resume_dataset = "resume_dataset" in body
    resume_dataset = str(body.get("resume_dataset", "")).strip()
    if has_resume_dataset and resume_dataset and not re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9._-]*/[A-Za-z0-9][A-Za-z0-9._-]*",
        resume_dataset,
    ):
        raise HTTPException(400, "恢复 Dataset 必须使用 owner/dataset-slug 格式")
    existing_token = os.environ.get("KAGGLE_API_TOKEN", "")
    if not token and not existing_token:
        os.environ.pop("KAGGLE_API_TOKEN", None)
        os.environ.pop("RVC_KAGGLE_USERNAME", None)
        os.environ.pop("RVC_RESUME_ROOT", None)
        _kaggle_setup_complete = True
        return {
            "configured": False,
            "warning": "未配置 Token：不能上传私有模型、保存跨 Session checkpoint 或恢复私有 Dataset。",
        }
    if token:
        os.environ["KAGGLE_API_TOKEN"] = token
        try:
            import kagglehub

            identity = kagglehub.whoami(verbose=False)
            owner = str(identity.get("username", "")).strip()
            if not owner:
                raise RuntimeError("missing username")
        except Exception as error:
            os.environ.pop("KAGGLE_API_TOKEN", None)
            os.environ.pop("RVC_KAGGLE_USERNAME", None)
            os.environ.pop("RVC_RESUME_ROOT", None)
            raise HTTPException(
                400, f"Kaggle API Token 验证失败 ({type(error).__name__})"
            ) from None
    else:
        owner = str(os.environ.get("RVC_KAGGLE_USERNAME", "")).strip()
    if has_resume_dataset:
        if resume_dataset:
            os.environ["RVC_RESUME_DATASET"] = resume_dataset
        else:
            os.environ.pop("RVC_RESUME_DATASET", None)
            os.environ.pop("RVC_RESUME_ROOT", None)
    os.environ["RVC_KAGGLE_USERNAME"] = owner
    _kaggle_setup_complete = True
    return {
        "configured": True,
        "owner": owner,
        "resume_dataset": os.environ.get("RVC_RESUME_DATASET") or None,
    }


@app.post("/api/v1/resume")
async def restore_training_history(request: Request) -> dict[str, Any]:
    """Explicitly download a configured checkpoint before a training job starts."""
    if not os.environ.get("KAGGLE_API_TOKEN"):
        raise HTTPException(400, "请先验证 Kaggle API Token")
    body = await request.json()
    handle = str(body.get("dataset", os.environ.get("RVC_RESUME_DATASET", ""))).strip()
    if not handle:
        raise HTTPException(400, "未配置 RVC_RESUME_DATASET")
    try:
        import kagglehub

        output_dir = TEMP_DIR / "resume_download"
        downloaded = Path(kagglehub.dataset_download(
            handle,
            output_dir=str(output_dir),
            force_download=True,
        )).resolve()
        if not downloaded.is_dir():
            raise FileNotFoundError("下载目录不存在")
        staging = TEMP_DIR / ".resume_download.tmp"
        if staging.exists():
            shutil.rmtree(staging)
        shutil.copytree(downloaded, staging)
        manifest_paths = sorted(staging.rglob("resume_manifest.json"))
        if not manifest_paths:
            shutil.rmtree(staging)
            raise ValueError("Dataset 中没有恢复清单")
        models: list[str] = []
        for manifest_path in manifest_paths:
            manifest = json.loads(manifest_path.read_text("utf-8"))
            model_name = validate_model_name(str(manifest.get("model", "")))
            if model_name not in models:
                models.append(model_name)
        if not models:
            shutil.rmtree(staging)
            raise ValueError("Dataset 中没有可恢复模型")
        if output_dir.exists():
            shutil.rmtree(output_dir)
        os.replace(staging, output_dir)
    except Exception as error:
        os.environ.pop("RVC_RESUME_ROOT", None)
        raise HTTPException(
            400, f"训练历史下载失败 ({type(error).__name__})"
        ) from None
    resume_root = str(output_dir.resolve())
    os.environ["RVC_RESUME_ROOT"] = resume_root
    for model_name in models:
        register_dataset(model_name)
    return {
        "dataset": handle,
        "status": "ready",
        "path": resume_root,
        "models": models,
    }


@app.get("/api/v1/resume/datasets")
def list_resume_datasets() -> dict[str, Any]:
    """List private resume datasets visible to the authenticated Kaggle user."""
    if not os.environ.get("KAGGLE_API_TOKEN"):
        raise HTTPException(400, "请先验证 Kaggle API Token")
    try:
        from kagglehub.clients import build_kaggle_client
        from kagglesdk.datasets.types.dataset_api_service import ApiListDatasetsRequest
        from kagglesdk.datasets.types.dataset_enums import DatasetSelectionGroup

        client = build_kaggle_client()
        request = ApiListDatasetsRequest()
        request.group = DatasetSelectionGroup.DATASET_SELECTION_GROUP_MY_PRIVATE
        request.page_size = 100
        values: list[dict[str, Any]] = []
        while True:
            response = client.datasets.dataset_api_client.list_datasets(request)
            for dataset in response.datasets or []:
                handle = str(getattr(dataset, "ref", "") or "").strip()
                if not handle.lower().endswith("-resume"):
                    continue
                values.append(
                    {
                        "handle": handle,
                        "title": str(getattr(dataset, "title", "") or handle),
                        "description": str(getattr(dataset, "subtitle", "") or ""),
                        "updated": str(getattr(dataset, "last_updated", "") or ""),
                        "private": bool(getattr(dataset, "is_private", True)),
                    }
                )
            token = str(getattr(response, "next_page_token", "") or "")
            if not token:
                break
            request.page_token = token
        values.sort(key=lambda item: item["handle"].casefold())
        return {"datasets": values}
    except Exception as error:
        raise HTTPException(400, f"恢复 Dataset 列表获取失败 ({type(error).__name__})") from None


@app.post("/api/v1/datasets/confirm")
async def confirm_dataset(request: Request) -> dict[str, Any]:
    """Persist a confirmed dataset so it reappears as a selectable model."""
    body = await request.json()
    return _confirm_dataset(body.get("name", ""))


def _confirm_dataset(name: str) -> dict[str, Any]:
    try:
        return register_dataset(str(name))
    except ValueError as error:
        raise HTTPException(400, str(error)) from error


@app.get("/api/v1/options")
def options() -> dict[str, Any]:
    datasets = []
    if TRAINING_AUDIO_DIR.is_dir():
        datasets = sorted(path.name for path in TRAINING_AUDIO_DIR.iterdir() if path.is_dir())
    gpus = _detect_gpus()
    from ultimate_rvc.control.registry import read_registry

    registered = read_registry()
    model_dirs = set()
    models = []
    if TRAINING_MODELS_DIR.is_dir():
        model_dirs = {path.name for path in TRAINING_MODELS_DIR.iterdir() if path.is_dir()}
    for name in sorted(model_dirs | set(registered), key=str.casefold):
        entry = registered.get(name)
        models.append(
            {
                "name": name,
                "dataset": name,
                "stages": (entry or {}).get("stages", {}) if entry else {},
                "last_phase": (entry or {}).get("last_phase", ""),
                "created_at": (entry or {}).get("created_at", 0),
            }
        )
    progress = {}
    for model in models:
        progress_path = TRAINING_MODELS_DIR / model["name"] / "progress.json"
        if progress_path.is_file():
            snapshot = read_progress(progress_path)
            progress[model["name"]] = {
                "phase": snapshot.get("phase", ""),
                "phase_label": snapshot.get("phase_label", ""),
                "percent": snapshot.get("percent", 0),
                "elapsed_seconds": snapshot.get("elapsed_seconds", 0),
                "eta_seconds": snapshot.get("eta_seconds"),
                "epoch": snapshot.get("epoch", 0),
                "total_epochs": snapshot.get("total_epochs", 0),
                "loss_g": snapshot.get("loss_g"),
                "loss_d": snapshot.get("loss_d"),
                "stage_detail": snapshot.get("stage_detail", ""),
                "error": snapshot.get("error", ""),
            }
    return {
        "datasets": datasets,
        "models": models,
        "progress": progress,
        "gpus": gpus,
        "paths": {
            "upload_root": _display_path(TRAINING_AUDIO_DIR),
            "training_root": _display_path(TRAINING_MODELS_DIR),
        },
    }


def _detect_gpus() -> list[dict[str, Any]]:
    gpus: list[dict[str, Any]] = []
    try:
        import subprocess, re
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=index,name,memory.total", "--format=csv,noheader,nounits"],
            timeout=5, text=True, stderr=subprocess.DEVNULL
        )
        for line in out.strip().splitlines():
            parts = [x.strip() for x in line.split(",")]
            if len(parts) >= 3:
                gpus.append({"id": int(parts[0]), "name": parts[1], "memory_mb": int(parts[2])})
    except Exception:
        pass
    return gpus


@app.get("/api/v1/datasets/{name}/files")
def list_dataset_files(name: str) -> dict[str, Any]:
    dataset_dir = TRAINING_AUDIO_DIR / name
    if not dataset_dir.is_dir():
        raise HTTPException(404, "数据集不存在")
    files = sorted(
        {"name": f.name, "size": f.stat().st_size, "ext": f.suffix.lower()}
        for f in dataset_dir.iterdir()
        if f.is_file() and not f.name.startswith(".")
    )
    return {"dataset": name, "files": files}


@app.get("/api/v1/audio/{dataset}/{filename}")
def serve_audio(dataset: str, filename: str):
    from fastapi.responses import FileResponse
    file_path = TRAINING_AUDIO_DIR / dataset / Path(filename).name
    if not file_path.is_file():
        raise HTTPException(404, "文件不存在")
    media_type = {
        ".wav": "audio/wav", ".flac": "audio/flac",
        ".mp3": "audio/mpeg", ".ogg": "audio/ogg",
        ".m4a": "audio/mp4", ".aac": "audio/aac",
    }.get(file_path.suffix.lower(), "application/octet-stream")
    return FileResponse(file_path, media_type=media_type)


def _upload_path(upload_id: str) -> Path:
    try:
        uuid.UUID(upload_id)
    except ValueError as error:
        raise HTTPException(400, "无效上传 ID") from error
    return UPLOADS_DIR / upload_id


def _upload_manifest_lock(upload_id: str) -> Path:
    """Return the short-lived lock used for manifest updates."""
    return UPLOADS_DIR / f".{upload_id}.manifest.lock"


def _manifest(upload_id: str) -> dict[str, Any]:
    try:
        return json.loads((_upload_path(upload_id) / "manifest.json").read_text("utf-8"))
    except (OSError, ValueError, TypeError) as error:
        raise HTTPException(404, "上传任务不存在") from error


def _cleanup_uploads() -> int:
    """Remove abandoned upload state and return the number removed."""
    removed = 0
    if not UPLOADS_DIR.is_dir():
        return removed
    cutoff = time.time() - UPLOAD_TTL
    for directory in UPLOADS_DIR.iterdir():
        try:
            if (
                directory.is_dir()
                and not directory.name.startswith(".")
                and directory.stat().st_mtime < cutoff
            ):
                shutil.rmtree(directory)
                removed += 1
        except OSError:
            continue
    return removed


@app.post("/api/v1/uploads/direct", status_code=201)
async def begin_direct_upload(request: Request) -> dict[str, Any]:
    """Create a tracked single-request upload; no file chunking is used."""
    _cleanup_uploads()
    body = await request.json()
    try:
        dataset = validate_model_name(str(body.get("dataset", "")))
    except ValueError as error:
        raise HTTPException(400, str(error)) from error
    filename = Path(str(body.get("filename", ""))).name
    size = int(body.get("size", 0))
    if not filename or size <= 0 or Path(filename).suffix.lower() not in {".wav", ".flac", ".mp3", ".ogg", ".m4a", ".aac"}:
        raise HTTPException(400, "文件名或大小无效")
    if size > MAX_UPLOAD_SIZE:
        raise HTTPException(413, "上传文件超过 2 GiB 限制")
    with directory_lock(UPLOADS_DIR.parent / "uploads.lock", timeout=5):
        UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
        open_uploads = 0
        for path in UPLOADS_DIR.iterdir():
            if not path.is_dir() or path.name.startswith("."):
                continue
            try:
                if json.loads((path / "manifest.json").read_text("utf-8")).get("status") == "uploading":
                    open_uploads += 1
            except (OSError, ValueError, TypeError):
                continue
        if open_uploads >= MAX_OPEN_UPLOADS:
            raise HTTPException(429, "未完成上传任务过多")
        free = shutil.disk_usage(UPLOADS_DIR.parent).free
        if free < size:
            raise HTTPException(507, "磁盘剩余空间不足")
        upload_id = str(uuid.uuid4())
        directory = _upload_path(upload_id)
        directory.mkdir(parents=True)
        manifest = {
            "id": upload_id,
            "dataset": dataset,
            "filename": filename,
            "size": size,
            "received": 0,
            "status": "uploading",
            "created_at": time.time(),
            "updated_at": time.time(),
        }
        atomic_json_dump(manifest, directory / "manifest.json")
    return manifest


@app.get("/api/v1/uploads/{upload_id}")
def upload_status(upload_id: str) -> dict[str, Any]:
    manifest = _manifest(upload_id)
    _upload_path(upload_id).touch()
    return manifest


@app.put("/api/v1/uploads/direct/{upload_id}")
async def upload_direct(upload_id: str, request: Request) -> dict[str, Any]:
    """Stream one whole file to disk while publishing byte-level progress."""
    directory = _upload_path(upload_id)
    temporary = directory / ".uploading"
    stream_lock = UPLOADS_DIR / f".{upload_id}.lock"
    manifest_lock = _upload_manifest_lock(upload_id)
    # Keep the stream lock for the lifetime of this PUT, but never hold it
    # while progress requests update the manifest.
    async with async_directory_lock(stream_lock, timeout=10, stale_after=UPLOAD_TTL):
        async with async_directory_lock(manifest_lock, timeout=5):
            manifest = _manifest(upload_id)
            if manifest.get("status") != "uploading":
                raise HTTPException(409, "上传任务已结束")
            expected_size = int(manifest["size"])

        received = 0
        digest = hashlib.sha256()
        last_manifest_write = 0.0
        try:
            with temporary.open("wb") as output:
                async for data in request.stream():
                    received += len(data)
                    if received > expected_size:
                        raise HTTPException(400, "上传文件超过声明大小")
                    output.write(data)
                    digest.update(data)
                    now = time.time()
                    if received >= expected_size or now - last_manifest_write >= 0.5:
                        async with async_directory_lock(manifest_lock, timeout=3):
                            current = _manifest(upload_id)
                            if current.get("status") != "uploading":
                                raise HTTPException(409, "上传任务已结束")
                            current.update(
                                received=max(int(current.get("received", 0)), received),
                                updated_at=now,
                            )
                            atomic_json_dump(current, directory / "manifest.json")
                        last_manifest_write = now
            if received != expected_size:
                raise HTTPException(400, "上传文件大小不匹配")
            async with async_directory_lock(manifest_lock, timeout=5):
                manifest = _manifest(upload_id)
                dataset_dir = TRAINING_AUDIO_DIR / manifest["dataset"]
                dataset_dir.mkdir(parents=True, exist_ok=True)
                destination = dataset_dir / manifest["filename"]
                os.replace(temporary, destination)
                manifest.update(received=received, status="completed", updated_at=time.time())
                atomic_json_dump(manifest, directory / "manifest.json")
                try:
                    from ultimate_rvc.control.registry import mark_stage

                    upload_elapsed = time.time() - float(manifest.get("created_at", time.time()))
                    mark_stage(manifest["dataset"], "upload", upload_elapsed)
                except Exception:
                    pass
                result = {
                    "dataset": str(dataset_dir),
                    "filename": destination.name,
                    "sha256": digest.hexdigest(),
                }
            return result
        except Exception:
            try:
                async with async_directory_lock(manifest_lock, timeout=5):
                    manifest = _manifest(upload_id)
                    manifest.update(status="failed", updated_at=time.time())
                    atomic_json_dump(manifest, directory / "manifest.json")
            except (OSError, TimeoutError, HTTPException):
                pass
            temporary.unlink(missing_ok=True)
            raise


@app.post("/api/v1/uploads/direct/{upload_id}/progress")
async def upload_progress(upload_id: str, request: Request) -> dict[str, Any]:
    """Accept client-reported byte progress so notebooks can track uploads
    even when a reverse proxy buffers the entire request body."""
    directory = _upload_path(upload_id)
    body = await request.json()
    manifest = _manifest(upload_id)
    if manifest.get("status") != "uploading":
        return manifest
    reported = min(int(body.get("received", 0)), int(manifest["size"]))
    if reported <= int(manifest.get("received", 0)):
        return manifest
    try:
        async with async_directory_lock(_upload_manifest_lock(upload_id), timeout=3):
            manifest = _manifest(upload_id)
            if manifest.get("status") != "uploading":
                return manifest
            manifest.update(received=reported, updated_at=time.time())
            atomic_json_dump(manifest, directory / "manifest.json")
    except TimeoutError:
        pass
    return manifest


@app.post("/api/v1/jobs/{kind}")
async def submit_job(kind: str, request: Request, response: Response) -> dict[str, Any]:
    body = await request.json()
    if body.get("dataset_name"):
        try:
            dataset_name = validate_model_name(str(body["dataset_name"]))
        except ValueError as error:
            raise HTTPException(400, str(error)) from error
        body["dataset"] = str(TRAINING_AUDIO_DIR / dataset_name)
    key = request.headers.get("Idempotency-Key", "")
    try:
        job, created = create_job(kind, dict(body), key)
    except ValueError as error:
        raise HTTPException(400, str(error)) from error
    response.status_code = 201 if created else (200 if key and job.get("idempotency_key") == key else 409)
    return job


def _jobs_etag(jobs: list[dict[str, Any]]) -> str:
    values = [(job.get("id"), job.get("phase"), job.get("updated_at"), job.get("progress", {}).get("updated_at")) for job in jobs]
    return '"' + hashlib.sha256(json.dumps(values).encode()).hexdigest() + '"'


@app.get("/api/v1/jobs")
def jobs(request: Request, response: Response):
    values = list_jobs()
    etag = _jobs_etag(values)
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers={"ETag": etag})
    response.headers["ETag"] = etag
    return {"jobs": values}


@app.get("/api/progress")
def legacy_progress() -> dict[str, Any]:
    """Compatibility view for older frontends during the transition."""
    values = list_jobs()
    active = next((item for item in values if item.get("phase") in {"queued", "running", "stopping"}), values[0] if values else None)
    progress = dict(active.get("progress", {})) if active else {}
    model_name = str(active.get("params", {}).get("model_name", "")) if active else ""
    if model_name:
        progress["model_name"] = model_name
    return {"active": model_name or None, "active_training": bool(active and active.get("phase") in {"queued", "running", "stopping"}), "models": {model_name: progress} if model_name else {}, "history": [item.get("progress", {}) | {"model_name": item.get("params", {}).get("model_name", "")} for item in values]}


@app.get("/api/v1/jobs/{job_id}")
def job(job_id: str) -> dict[str, Any]:
    try:
        return read_job(job_id)
    except (ValueError, FileNotFoundError) as error:
        raise HTTPException(404, str(error)) from error


@app.post("/api/v1/jobs/{job_id}/stop")
def stop(job_id: str) -> dict[str, Any]:
    try:
        return stop_job(job_id)
    except (ValueError, FileNotFoundError) as error:
        raise HTTPException(404, str(error)) from error


@app.get("/api/v1/models")
def models() -> dict[str, Any]:
    values = []
    if TRAINING_MODELS_DIR.is_dir():
        for directory in TRAINING_MODELS_DIR.iterdir():
            progress_path = directory / "progress.json"
            if directory.is_dir() and progress_path.is_file():
                progress = read_progress(progress_path)
                files = delivery_files(directory, directory.name)
                values.append({"name": directory.name, "progress": progress, "files": {kind: path.is_file() for kind, path in files.items()}})
    return {"models": sorted(values, key=lambda item: float(item["progress"].get("updated_at", 0)), reverse=True)}


@app.get("/api/v1/models/{model_name}/files/{kind}")
def download(model_name: str, kind: str) -> FileResponse:
    try:
        model_name = validate_model_name(model_name)
    except ValueError as error:
        raise HTTPException(400, str(error)) from error
    if kind not in {"pth", "index", "log"}:
        raise HTTPException(404, "不支持的文件类型")
    path = delivery_files(TRAINING_MODELS_DIR / model_name, model_name)[kind]
    if not path.is_file():
        raise HTTPException(404, "文件不存在")
    return FileResponse(path, filename=path.name, media_type="application/octet-stream")


@app.get("/api/v1/models/{model_name}/zip")
def download_zip(model_name: str) -> FileResponse:
    """Build a temporary delivery archive containing the three public files."""
    try:
        model_name = validate_model_name(model_name)
    except ValueError as error:
        raise HTTPException(400, str(error)) from error
    model_dir = TRAINING_MODELS_DIR / model_name
    files = delivery_files(model_dir, model_name)
    missing = [path.name for path in files.values() if not path.is_file()]
    if missing:
        raise HTTPException(404, f"缺少可下载文件：{', '.join(missing)}")

    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(
        prefix=f"{model_name}-", suffix=".zip", dir=TEMP_DIR,
    )
    os.close(fd)
    try:
        with zipfile.ZipFile(temporary_name, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in files.values():
                archive.write(path, arcname=path.name)
    except Exception:
        Path(temporary_name).unlink(missing_ok=True)
        raise
    return FileResponse(
        temporary_name,
        filename=f"{model_name}.zip",
        media_type="application/zip",
        background=BackgroundTask(_remove_temp_file, temporary_name),
    )


def main() -> None:
    _secret()
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=7860)
    args = parser.parse_args()
    import uvicorn
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
