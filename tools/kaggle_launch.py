"""Launch the RVC control console behind a supervised Cloudflare tunnel."""

from __future__ import annotations

import atexit
import hashlib
import os
import re
import secrets
import signal
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLOUDFLARED_VERSION = "2026.7.3"
CLOUDFLARED_URL = (
    "https://github.com/cloudflare/cloudflared/releases/download/"
    f"{CLOUDFLARED_VERSION}/cloudflared-linux-amd64"
)
CLOUDFLARED_SHA256 = "9d71c677db00134c1bd4144b7783486b654ad281b1ea62b4972098d19f770f17"
TUNNEL_URL_PATTERN = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")
processes: list[subprocess.Popen[str]] = []
shutting_down = False


def secret_value(name: str) -> str | None:
    try:
        from kaggle_secrets import UserSecretsClient

        return UserSecretsClient().get_secret(name)
    except Exception:
        return os.environ.get(name)


def stop_processes(*_: object) -> None:
    global shutting_down
    shutting_down = True
    for process in reversed(processes):
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                process.kill()


def stream(process: subprocess.Popen[str], lines: list[str]) -> None:
    assert process.stdout is not None
    for line in process.stdout:
        clean = line.rstrip()
        lines.append(clean)
        print(clean, flush=True)


def wait_for_server(port: int = 7860) -> None:
    """Block until the public health endpoint confirms the console is ready."""
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    for _ in range(60):
        try:
            with opener.open(f"http://127.0.0.1:{port}/healthz", timeout=3) as response:
                if response.status == 200:
                    return
        except Exception:
            pass
        time.sleep(1)
    raise RuntimeError("RVC control console did not become ready within 60 seconds")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def install_cloudflared(destination: Path) -> Path:
    """Download the pinned binary and verify Cloudflare's published digest."""
    if destination.is_file() and sha256_file(destination) == CLOUDFLARED_SHA256:
        return destination
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".download")
    temporary.unlink(missing_ok=True)
    request = urllib.request.Request(CLOUDFLARED_URL, headers={"User-Agent": "rvc-kaggle"})
    try:
        with urllib.request.urlopen(request, timeout=60) as response, temporary.open("wb") as target:
            total = 0
            while chunk := response.read(1024 * 1024):
                total += len(chunk)
                if total > 100 * 1024 * 1024:
                    raise RuntimeError("cloudflared 下载超过 100 MiB 限制")
                target.write(chunk)
        actual = sha256_file(temporary)
        if not secrets.compare_digest(actual, CLOUDFLARED_SHA256):
            raise RuntimeError("cloudflared SHA-256 校验失败")
        os.replace(temporary, destination)
        destination.chmod(0o755)
        return destination
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def parse_tunnel_url(lines: list[str]) -> str | None:
    match = TUNNEL_URL_PATTERN.search("\n".join(lines[-80:]))
    return match.group(0) if match else None


def start_tunnel(binary: Path) -> tuple[subprocess.Popen[str], list[str]]:
    process = subprocess.Popen(
        [str(binary), "tunnel", "--no-autoupdate", "--url", "http://127.0.0.1:7860"],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    processes.append(process)
    lines: list[str] = []
    threading.Thread(target=stream, args=(process, lines), daemon=True).start()
    return process, lines


def wait_for_tunnel_url(process: subprocess.Popen[str], lines: list[str]) -> str:
    for _ in range(60):
        if url := parse_tunnel_url(lines):
            return url
        if process.poll() is not None:
            break
        time.sleep(1)
    raise RuntimeError("Cloudflare Quick Tunnel 未提供公网地址")


def print_access(url: str, password: str) -> None:
    print("\n" + "=" * 60)
    print(f"训练控制台: {url}")
    print("用户名: rvc")
    print(f"密码: {password}")
    print("=" * 60 + "\n", flush=True)


def main() -> None:
    password = secret_value("RVC_WEB_PASSWORD") or secrets.token_urlsafe(12)
    resume_dataset = secret_value("RVC_RESUME_DATASET")
    if resume_dataset:
        os.environ["RVC_RESUME_DATASET"] = resume_dataset

    environment = os.environ.copy()
    environment["PYTHONNOUSERSITE"] = "1"
    environment["PYTHONUNBUFFERED"] = "1"
    environment["PYTHONPATH"] = str(ROOT / "src") + os.pathsep + environment.get("PYTHONPATH", "")
    environment["RVC_CONTROL_USER"] = "rvc"
    environment["RVC_CONTROL_PASSWORD"] = password
    control_secret = secret_value("RVC_CONTROL_SECRET")
    if not control_secret:
        secret_path = ROOT / "temp" / "control" / "session_secret"
        secret_path.parent.mkdir(parents=True, exist_ok=True)
        if secret_path.is_file():
            control_secret = secret_path.read_text("utf-8").strip()
        else:
            control_secret = secrets.token_urlsafe(32)
            secret_path.write_text(control_secret, encoding="utf-8")
            try:
                secret_path.chmod(0o600)
            except OSError:
                pass
    environment["RVC_CONTROL_SECRET"] = control_secret
    control_command = [
        sys.executable, "-u", "-m", "ultimate_rvc.control.app",
        "--host", "127.0.0.1", "--port", "7860",
    ]

    def start_control() -> subprocess.Popen[str]:
        process = subprocess.Popen(
            control_command,
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env=environment,
        )
        processes.append(process)
        threading.Thread(target=stream, args=(process, []), daemon=True).start()
        return process

    binary = install_cloudflared(ROOT / "temp" / "bin" / "cloudflared")
    control = start_control()
    wait_for_server()
    tunnel, tunnel_lines = start_tunnel(binary)
    print_access(wait_for_tunnel_url(tunnel, tunnel_lines), password)

    while not shutting_down:
        if control.poll() is not None:
            print(f"[RVC] 控制服务退出 ({control.returncode})，2 秒后自动恢复", flush=True)
            time.sleep(2)
            control = start_control()
            wait_for_server()
        if tunnel.poll() is not None:
            print(f"[RVC] Quick Tunnel 退出 ({tunnel.returncode})，2 秒后自动恢复", flush=True)
            time.sleep(2)
            tunnel, tunnel_lines = start_tunnel(binary)
            print_access(wait_for_tunnel_url(tunnel, tunnel_lines), password)
        time.sleep(1)


atexit.register(stop_processes)
signal.signal(signal.SIGTERM, stop_processes)
signal.signal(signal.SIGINT, stop_processes)

if __name__ == "__main__":
    main()
