"""Kaggle delivery usable by both the control worker and web UI."""

from __future__ import annotations

import json
import os
import re
import time
import urllib.parse
from pathlib import Path
from typing import Any

import requests

from ultimate_rvc.common import TRAINING_MODELS_DIR
from ultimate_rvc.rvc.train.delivery import (
    atomic_json_dump,
    prepare_delivery_files,
    validate_delivery,
    validate_model_name,
)


KAGGLE_API = "https://www.kaggle.com/api/v1"


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
    username, key = os.environ.get("KAGGLE_USERNAME"), os.environ.get("KAGGLE_KEY")
    if not username or not key:
        return {"errors": ["未配置 KAGGLE_USERNAME/KAGGLE_KEY"]}
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
    auth = (username, key)
    resources = []
    for path in files.values():
        try:
            with path.open("rb") as source:
                response = requests.post(
                    f"{KAGGLE_API}/datasets/new/upload/file?fileName={urllib.parse.quote(path.name)}",
                    files={"file": (path.name, source)}, auth=auth, timeout=600,
                )
            response.raise_for_status()
            resources.append({"token": response.json()["token"]})
        except Exception as error:
            return {"errors": [f"{path.name} 上传失败：{error}"]}
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "rvc-model"
    slug = f"{base[:40]}-{int(time.time())}"
    payload = {
        "ownerSlug": username, "slug": slug, "title": f"RVC {name}",
        "subtitle": "RVC trained voice model", "description": f"RVC {name} pth/index/log",
        "isPrivate": True, "licenseName": "other", "keywords": [],
        "collaborators": [], "sources": [], "resources": resources, "data": resources,
    }
    try:
        response = requests.post(f"{KAGGLE_API}/datasets/create/new", json=payload, auth=auth, timeout=180)
        response.raise_for_status()
    except Exception as error:
        return {"errors": [f"Kaggle Dataset 创建失败：{error}"]}
    urls = {"kaggle": f"https://www.kaggle.com/datasets/{username}/{slug}", "kaggle_slug": f"{username}/{slug}"}
    atomic_json_dump(urls, cached_path)
    return urls
