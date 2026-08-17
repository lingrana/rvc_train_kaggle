"""Shared security boundaries for paths, downloads, archives, and checkpoints."""

from __future__ import annotations

import asyncio
from typing import Any

import ipaddress
import os
import re
import shutil
import socket
import stat
import time
import zipfile
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager, nullcontext
from pathlib import Path, PurePosixPath
from urllib.parse import urljoin, urlsplit

SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
MAX_DOWNLOAD_BYTES = 4 * 1024**3
MAX_ARCHIVE_FILES = 256
MAX_ARCHIVE_BYTES = 4 * 1024**3
MAX_ARCHIVE_MEMBER_BYTES = 2 * 1024**3
TRUSTED_DOWNLOAD_HOSTS = frozenset(
    {
        "github.com",
        "objects.githubusercontent.com",
        "release-assets.githubusercontent.com",
        "huggingface.co",
        "cdn-lfs.hf.co",
        "cas-bridge.xethub.hf.co",
        "pixeldrain.com",
        "drive.google.com",
        "docs.google.com",
        "googleusercontent.com",
    }
)


def validate_safe_name(value: str) -> str:
    """Return a portable path component or reject it."""
    name = value.strip()
    if not SAFE_NAME.fullmatch(name):
        raise ValueError(
            "名称只能包含英文字母、数字、下划线和连字符，且最长 64 个字符"
        )
    return name


def safe_child(root: Path, name: str) -> Path:
    """Resolve a validated direct child of root."""
    root = root.resolve()
    target = (root / validate_safe_name(name)).resolve()
    if not target.is_relative_to(root):
        raise ValueError("路径超出允许目录")
    return target


def _validate_public_host(hostname: str, port: int) -> None:
    try:
        addresses = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
    except socket.gaierror as error:
        raise ValueError(f"无法解析下载地址：{hostname}") from error
    if not addresses:
        raise ValueError(f"无法解析下载地址：{hostname}")
    for address in addresses:
        ip = ipaddress.ip_address(address[4][0].split("%", 1)[0])
        if not ip.is_global:
            raise ValueError("禁止访问本机、内网或特殊用途地址")


def validate_remote_url(url: str) -> str:
    """Require HTTPS and a hostname resolving only to public addresses."""
    parsed = urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username:
        raise ValueError("仅允许不含用户信息的 HTTPS URL")
    if parsed.port not in {None, 443}:
        raise ValueError("下载 URL 仅允许 HTTPS 默认端口")
    hostname = parsed.hostname.lower()
    if not any(
        hostname == trusted or hostname.endswith(f".{trusted}")
        for trusted in TRUSTED_DOWNLOAD_HOSTS
    ):
        raise ValueError("下载域名不在受信列表中")
    _validate_public_host(hostname, 443)
    return url


def download_https(
    url: str,
    destination: Path,
    *,
    max_bytes: int = MAX_DOWNLOAD_BYTES,
    expected_sha256: str | None = None,
) -> Path:
    """Download a bounded HTTPS resource after validating each redirect."""
    import hashlib

    import requests

    current = validate_remote_url(url)
    response = None
    for _ in range(6):
        response = requests.get(
            current,
            stream=True,
            timeout=(10, 60),
            allow_redirects=False,
            headers={"User-Agent": "ultimate-rvc/secure-downloader"},
        )
        if response.is_redirect or response.is_permanent_redirect:
            location = response.headers.get("location")
            response.close()
            if not location:
                raise ValueError("下载重定向缺少 Location")
            current = validate_remote_url(urljoin(current, location))
            continue
        break
    else:
        raise ValueError("下载重定向次数过多")
    assert response is not None
    response.raise_for_status()
    declared = int(response.headers.get("content-length", 0) or 0)
    if declared > max_bytes:
        response.close()
        raise ValueError("下载文件超过大小限制")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".download")
    digest = hashlib.sha256()
    written = 0
    try:
        with temporary.open("wb") as output:
            for chunk in response.iter_content(1024 * 1024):
                if not chunk:
                    continue
                written += len(chunk)
                if written > max_bytes:
                    raise ValueError("下载文件超过大小限制")
                output.write(chunk)
                digest.update(chunk)
            output.flush()
            os.fsync(output.fileno())
        if expected_sha256 and digest.hexdigest() != expected_sha256.lower():
            raise ValueError("下载文件 SHA-256 校验失败")
        Path(temporary).replace(destination)
    finally:
        response.close()
        temporary.unlink(missing_ok=True)
    return destination


def safe_extract_zip(archive: zipfile.ZipFile, destination: Path) -> None:
    """Extract a bounded ZIP without links or escaping members."""
    destination = destination.resolve()
    infos = archive.infolist()
    if len(infos) > MAX_ARCHIVE_FILES:
        raise ValueError("压缩包文件数量超过限制")
    if sum(info.file_size for info in infos) > MAX_ARCHIVE_BYTES:
        raise ValueError("压缩包展开大小超过限制")
    for info in infos:
        member = PurePosixPath(info.filename.replace("\\", "/"))
        mode = info.external_attr >> 16
        if (
            member.is_absolute()
            or ".." in member.parts
            or info.file_size > MAX_ARCHIVE_MEMBER_BYTES
            or stat.S_ISLNK(mode)
            or stat.S_ISCHR(mode)
            or stat.S_ISBLK(mode)
            or stat.S_ISFIFO(mode)
        ):
            raise ValueError(f"压缩包包含不安全成员：{info.filename}")
        target = (destination / Path(*member.parts)).resolve()
        if not target.is_relative_to(destination):
            raise ValueError(f"压缩包成员越界：{info.filename}")
    for info in infos:
        member = PurePosixPath(info.filename.replace("\\", "/"))
        target = destination / Path(*member.parts)
        if info.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        with archive.open(info) as source, target.open("wb") as output:
            shutil.copyfileobj(source, output, length=1024 * 1024)


def load_torch_checkpoint(path: os.PathLike[str] | str, *, map_location: Any = "cpu") -> Any:
    """Load tensor state without permitting arbitrary Pickle globals."""
    import torch

    from ultimate_rvc.typing_extra import RVCVersion, Vocoder

    serialization = getattr(torch, "serialization", None)
    safe_globals = getattr(serialization, "safe_globals", None)
    context = safe_globals([RVCVersion, Vocoder]) if safe_globals else nullcontext()
    with context:
        return torch.load(path, map_location=map_location, weights_only=True)


@contextmanager
def directory_lock(
    path: Path, *, timeout: float = 10, stale_after: float = 3600
) -> Iterator[None]:
    """Provide a dependency-free cross-process lock via atomic mkdir."""
    deadline = time.monotonic() + timeout
    while True:
        try:
            path.mkdir(parents=True)
            (path / "owner").write_text(f"{os.getpid()}\n{time.time()}\n", "ascii")
            break
        except FileExistsError:
            try:
                if time.time() - path.stat().st_mtime > stale_after:
                    for child in path.iterdir():
                        child.unlink(missing_ok=True)
                    path.rmdir()
                    continue
            except OSError:
                pass
            if time.monotonic() >= deadline:
                raise TimeoutError(f"Timed out waiting for lock: {path}")
            time.sleep(0.05)
    try:
        yield
    finally:
        try:
            for child in path.iterdir():
                child.unlink(missing_ok=True)
            path.rmdir()
        except OSError:
            pass


@asynccontextmanager
async def async_directory_lock(
    path: Path, *, timeout: float = 10, stale_after: float = 3600
) -> AsyncIterator[None]:
    """Acquire a directory lock without blocking an async event loop."""
    deadline = time.monotonic() + timeout
    while True:
        try:
            path.mkdir(parents=True)
            (path / "owner").write_text(f"{os.getpid()}\n{time.time()}\n", "ascii")
            break
        except FileExistsError:
            try:
                if time.time() - path.stat().st_mtime > stale_after:
                    for child in path.iterdir():
                        child.unlink(missing_ok=True)
                    path.rmdir()
                    continue
            except OSError:
                pass
            if time.monotonic() >= deadline:
                raise TimeoutError(f"Timed out waiting for lock: {path}")
            await asyncio.sleep(0.05)
    try:
        yield
    finally:
        try:
            for child in path.iterdir():
                child.unlink(missing_ok=True)
            path.rmdir()
        except OSError:
            pass
