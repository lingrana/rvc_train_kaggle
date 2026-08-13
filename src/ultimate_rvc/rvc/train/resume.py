"""Create and restore small cross-session RVC training state snapshots."""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

from ultimate_rvc.kaggle_auth import kaggle_username
from ultimate_rvc.rvc.train.delivery import atomic_json_dump, sha256_file


STATE_FILES = (
    "G_2333333.pth",
    "D_2333333.pth",
    "config.json",
    "filelist.txt",
    "progress.json",
    "model_info.json",
    "train.log",
)


def create_resume_snapshot(model_dir: Path) -> Path:
    """Atomically refresh a compact snapshot directory after checkpoint saves."""
    destination = model_dir / "resume_state"
    temporary = model_dir / ".resume_state.tmp"
    if temporary.exists():
        shutil.rmtree(temporary)
    temporary.mkdir(parents=True)
    files: dict[str, dict[str, int | str]] = {}
    for name in STATE_FILES:
        source = model_dir / name
        if not source.is_file():
            continue
        target = temporary / name
        shutil.copy2(source, target)
        files[name] = {"size": target.stat().st_size, "sha256": sha256_file(target)}
    if not {"G_2333333.pth", "D_2333333.pth"}.issubset(files):
        shutil.rmtree(temporary)
        raise FileNotFoundError("最新 G/D checkpoint 尚未同时生成")
    progress = {}
    progress_path = model_dir / "progress.json"
    if progress_path.is_file():
        progress = json.loads(progress_path.read_text("utf-8"))
    atomic_json_dump(
        {"model": model_dir.name, "epoch": progress.get("epoch", 0), "files": files},
        temporary / "resume_manifest.json",
    )
    old = model_dir / ".resume_state.old"
    if old.exists():
        shutil.rmtree(old)
    if destination.exists():
        os.replace(destination, old)
    os.replace(temporary, destination)
    if old.exists():
        shutil.rmtree(old)
    return destination


def restore_resume_snapshot(snapshot_dir: Path, model_dir: Path) -> int:
    """Verify and restore a snapshot into an already extracted training model."""
    manifest_path = snapshot_dir / "resume_manifest.json"
    manifest = json.loads(manifest_path.read_text("utf-8"))
    if manifest.get("model") != model_dir.name:
        raise ValueError("恢复状态的模型名称与目标模型不一致")
    for name, metadata in manifest.get("files", {}).items():
        source = snapshot_dir / name
        if not source.is_file() or sha256_file(source) != metadata.get("sha256"):
            raise ValueError(f"恢复状态文件损坏：{name}")
    model_dir.mkdir(parents=True, exist_ok=True)
    for name in manifest["files"]:
        source = snapshot_dir / name
        temporary = model_dir / f".{name}.restore.tmp"
        if name == "config.json":
            config = json.loads(source.read_text("utf-8"))
            config.pop("process_pids", None)
            atomic_json_dump(config, temporary)
        else:
            shutil.copy2(source, temporary)
        os.replace(temporary, model_dir / name)
    return int(manifest.get("epoch", 0))


def sync_resume_snapshot(model_dir: Path) -> str | None:
    """Publish the compact snapshot as a stable private Kaggle Dataset version."""
    import kagglehub

    username = kaggle_username(kagglehub)
    if not username:
        return None
    snapshot = model_dir / "resume_state"
    manifest = json.loads((snapshot / "resume_manifest.json").read_text("utf-8"))
    slug_base = "rvc-" + "".join(
        char.lower() if char.isalnum() else "-" for char in model_dir.name
    ).strip("-")
    slug = f"{slug_base[:42]}-resume"
    handle = f"{username}/{slug}"
    try:
        kagglehub.dataset_upload(
            handle,
            str(snapshot),
            version_notes=f"epoch {manifest.get('epoch', 0)}",
        )
    except Exception as error:
        raise RuntimeError(
            f"Kaggle resume upload failed ({type(error).__name__})"
        ) from None
    return handle
