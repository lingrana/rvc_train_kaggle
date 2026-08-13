"""FastAPI control plane for stable, reconnectable Kaggle training."""

from __future__ import annotations

from typing import Any

import argparse
import hashlib
import hmac
import json
import os
import secrets
import shutil
import time
import uuid
from collections import defaultdict, deque
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, HTMLResponse

from ultimate_rvc.common import AUDIO_DIR, TEMP_DIR, TRAINING_MODELS_DIR
from ultimate_rvc.control.jobs import (
    UPLOADS_DIR,
    create_job,
    list_jobs,
    read_job,
    stop_job,
)
from ultimate_rvc.rvc.train.delivery import delivery_files, validate_model_name
from ultimate_rvc.rvc.train.progress import read_progress
from ultimate_rvc.security import directory_lock

COOKIE_NAME = "rvc-control-session"
COOKIE_TTL = 24 * 60 * 60
PART_SIZE = 8 * 1024 * 1024
MAX_UPLOAD_SIZE = 2 * 1024**3
MAX_OPEN_UPLOADS = 4
UPLOAD_TTL = 24 * 60 * 60
LOGIN_WINDOW = 5 * 60
LOGIN_ATTEMPTS = 8
TRAINING_AUDIO_DIR = AUDIO_DIR / "training"
app = FastAPI(title="RVC Training Control", docs_url=None, redoc_url=None)
_login_failures: dict[str, deque[float]] = defaultdict(deque)
_kaggle_setup_complete = False


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
    if not token:
        os.environ.pop("KAGGLE_API_TOKEN", None)
        os.environ.pop("RVC_KAGGLE_USERNAME", None)
        os.environ.pop("RVC_RESUME_ROOT", None)
        _kaggle_setup_complete = True
        return {
            "configured": False,
            "warning": "未配置 Token：不能上传私有模型、保存跨 Session checkpoint 或恢复私有 Dataset。",
        }
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
    os.environ["RVC_KAGGLE_USERNAME"] = owner
    _kaggle_setup_complete = True
    return {
        "configured": True,
        "owner": owner,
        "resume_dataset": os.environ.get("RVC_RESUME_DATASET") or None,
    }


@app.post("/api/v1/resume")
async def restore_training_history(request: Request) -> dict[str, str]:
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
        downloaded = kagglehub.dataset_download(
            handle,
            output_dir=str(output_dir),
            force_download=True,
        )
    except Exception as error:
        os.environ.pop("RVC_RESUME_ROOT", None)
        raise HTTPException(
            400, f"训练历史下载失败 ({type(error).__name__})"
        ) from None
    os.environ["RVC_RESUME_ROOT"] = str(downloaded)
    return {"dataset": handle, "status": "ready"}


@app.get("/api/v1/options")
def options() -> dict[str, Any]:
    datasets = []
    if TRAINING_AUDIO_DIR.is_dir():
        datasets = sorted(path.name for path in TRAINING_AUDIO_DIR.iterdir() if path.is_dir())
    gpus = _detect_gpus()
    return {"datasets": datasets, "part_size": PART_SIZE, "gpus": gpus}


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
async def upload_audio_file(request: Request) -> dict[str, Any]:
    content_type = request.headers.get("content-type", "")
    if "multipart/form-data" not in content_type:
        raise HTTPException(400, "需要 multipart/form-data")
    form = await request.form()
    dataset_name = form.get("dataset", "")
    audio_file = form.get("file")
    if not audio_file or not hasattr(audio_file, "read"):
        raise HTTPException(400, "缺少文件")
    try:
        dataset_name = validate_model_name(str(dataset_name))
    except ValueError as error:
        raise HTTPException(400, str(error)) from error
    filename = Path(getattr(audio_file, "filename", "")).name
    if not filename or Path(filename).suffix.lower() not in {".wav", ".flac", ".mp3", ".ogg", ".m4a", ".aac"}:
        raise HTTPException(400, "文件名无效或格式不支持")
    data = await audio_file.read()
    size = len(data)
    if size <= 0 or size > MAX_UPLOAD_SIZE:
        raise HTTPException(400, "文件大小无效")
    free = shutil.disk_usage(UPLOADS_DIR.parent).free
    if free < size:
        raise HTTPException(507, "磁盘剩余空间不足")
    dataset_dir = TRAINING_AUDIO_DIR / dataset_name
    dataset_dir.mkdir(parents=True, exist_ok=True)
    destination = dataset_dir / filename
    digest = hashlib.sha256(data)
    destination.write_bytes(data)
    return {"dataset": dataset_name, "filename": filename, "size": size, "sha256": digest.hexdigest()}


@app.post("/api/v1/uploads", status_code=201)
async def begin_upload(request: Request) -> dict[str, Any]:
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
        open_uploads = sum(
            1
            for path in UPLOADS_DIR.iterdir()
            if path.is_dir() and not path.name.startswith(".")
        )
        if open_uploads >= MAX_OPEN_UPLOADS:
            raise HTTPException(429, "未完成上传任务过多")
        free = shutil.disk_usage(UPLOADS_DIR.parent).free
        if free < size + PART_SIZE:
            raise HTTPException(507, "磁盘剩余空间不足")
        upload_id = str(uuid.uuid4())
        directory = _upload_path(upload_id)
        (directory / "parts").mkdir(parents=True)
        manifest = {"id": upload_id, "dataset": dataset, "filename": filename, "size": size, "part_size": PART_SIZE, "sha256": str(body.get("sha256", "")), "created_at": time.time()}
        from ultimate_rvc.rvc.train.delivery import atomic_json_dump
        atomic_json_dump(manifest, directory / "manifest.json")
    return {**manifest, "completed_parts": []}


@app.get("/api/v1/uploads/{upload_id}")
def upload_status(upload_id: str) -> dict[str, Any]:
    manifest = _manifest(upload_id)
    _upload_path(upload_id).touch()
    parts = sorted(int(path.name) for path in (_upload_path(upload_id) / "parts").iterdir() if path.name.isdigit())
    return {**manifest, "completed_parts": parts}


@app.put("/api/v1/uploads/{upload_id}/parts/{number}")
async def upload_part(upload_id: str, number: int, request: Request) -> dict[str, Any]:
    manifest = _manifest(upload_id)
    total_parts = (int(manifest["size"]) + PART_SIZE - 1) // PART_SIZE
    if number < 0 or number >= total_parts:
        raise HTTPException(400, "分片编号超出范围")
    expected = min(PART_SIZE, int(manifest["size"]) - number * PART_SIZE)
    data = await request.body()
    if len(data) != expected:
        raise HTTPException(400, f"分片大小错误，应为 {expected} 字节")
    digest = hashlib.sha256(data).hexdigest()
    supplied = request.headers.get("X-Part-SHA256", "")
    if supplied and not hmac.compare_digest(digest, supplied.lower()):
        raise HTTPException(400, "分片 SHA-256 校验失败")
    directory = _upload_path(upload_id)
    destination = directory / "parts" / str(number)
    with directory_lock(UPLOADS_DIR / f".{upload_id}.lock", timeout=10):
        temporary = destination.with_suffix(f".{uuid.uuid4().hex}.tmp")
        try:
            temporary.write_bytes(data)
            Path(temporary).replace(destination)
            directory.touch()
        finally:
            temporary.unlink(missing_ok=True)
    return {"number": number, "sha256": digest}


@app.post("/api/v1/uploads/{upload_id}/complete")
def complete_upload(upload_id: str) -> dict[str, str]:
    with directory_lock(UPLOADS_DIR / f".{upload_id}.lock", timeout=10):
        manifest = _manifest(upload_id)
        directory = _upload_path(upload_id)
        total_parts = (int(manifest["size"]) + PART_SIZE - 1) // PART_SIZE
        missing = [number for number in range(total_parts) if not (directory / "parts" / str(number)).is_file()]
        if missing:
            raise HTTPException(409, {"missing_parts": missing})
        dataset_dir = TRAINING_AUDIO_DIR / manifest["dataset"]
        dataset_dir.mkdir(parents=True, exist_ok=True)
        destination = dataset_dir / manifest["filename"]
        temporary = destination.with_suffix(destination.suffix + ".upload")
        digest = hashlib.sha256()
        with temporary.open("wb") as output:
            for number in range(total_parts):
                data = (directory / "parts" / str(number)).read_bytes()
                output.write(data)
                digest.update(data)
        if temporary.stat().st_size != int(manifest["size"]) or (manifest.get("sha256") and digest.hexdigest() != manifest["sha256"]):
            temporary.unlink(missing_ok=True)
            raise HTTPException(400, "完整文件校验失败")
        Path(temporary).replace(destination)
        shutil.rmtree(directory)
    return {"dataset": str(dataset_dir), "filename": destination.name, "sha256": digest.hexdigest()}


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
