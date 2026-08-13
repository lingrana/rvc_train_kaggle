"""Shared helpers for Kaggle access-token authentication."""

from __future__ import annotations

import os
from typing import Any


def kaggle_username(kagglehub: Any | None = None) -> str | None:
    """Return the verified token owner, never falling back to legacy credentials."""
    if not os.environ.get("KAGGLE_API_TOKEN"):
        return None
    if cached := os.environ.get("RVC_KAGGLE_USERNAME"):
        return cached
    if kagglehub is None:
        import kagglehub as kagglehub_module

        kagglehub = kagglehub_module
    identity = kagglehub.whoami(verbose=False)
    username = str(identity.get("username", "")).strip()
    if not username:
        raise RuntimeError("Kaggle API Token 未返回用户名")
    os.environ["RVC_KAGGLE_USERNAME"] = username
    return username
