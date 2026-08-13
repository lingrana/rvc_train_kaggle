"""Kaggle delivery usable by both the control worker and web UI."""

from __future__ import annotations

import json
import re
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any

from ultimate_rvc.common import TRAINING_MODELS_DIR
from ultimate_rvc.kaggle_auth import kaggle_username
from ultimate_rvc.rvc.train.delivery import (
    atomic_json_dump,
    prepare_delivery_files,
    validate_delivery,
    validate_model_name,
)


def upload_model(model_name: str) -> dict[str, Any]:
    """Validate and upload pth/index/log to a private Kaggle Dataset."""
    name = validate_model_name(model_name)
    model_dir = TRAINING_MODELS_DIR / name
    progress_path = model_dir / "progress.json"
    try:
        if not json.loads(progress_path.read_text("utf-8")).get("done"):
            return {"errors": ["训练未完成"]}
    except (OSError, ValueError, TypeError):
        return {"errors": ["训练未完成"]}
    try:
        files = prepare_delivery_files(model_dir, name)
        validate_delivery(model_dir, name)
    except Exception as error:
        return {"errors": [f"本地推理兼容性校验失败：{error}"]}
    cached_path = model_dir / "kaggle_urls.json"
    try:
        cached = json.loads(cached_path.read_text("utf-8"))
        if cached.get("kaggle"):
            return cached
    except (OSError, ValueError, TypeError):
        pass
    try:
        import kagglehub

        username = kaggle_username(kagglehub)
    except Exception as error:
        return {"errors": [f"Kaggle API Token 无效 ({type(error).__name__})"]}
    if not username:
        return {"errors": ["未配置 KAGGLE_API_TOKEN"]}
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "rvc-model"
    slug = f"rvc-{base[:36]}-{int(time.time())}"
    handle = f"{username}/{slug}"
    try:
        with tempfile.TemporaryDirectory(prefix="rvc-delivery-") as temporary:
            delivery_dir = Path(temporary)
            for path in files.values():
                shutil.copy2(path, delivery_dir / path.name)
            kagglehub.dataset_upload(
                handle,
                str(delivery_dir),
                version_notes=f"RVC {name} trained model",
            )
    except Exception as error:
        return {"errors": [f"Kaggle Dataset 上传失败 ({type(error).__name__})"]}
    urls = {
        "kaggle": f"https://www.kaggle.com/datasets/{handle}",
        "kaggle_slug": handle,
    }
    atomic_json_dump(urls, cached_path)
    return urls
