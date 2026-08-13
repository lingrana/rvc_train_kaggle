"""Launch the public control console, private Gradio fallback, and tunnel."""

from __future__ import annotations

import atexit
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


def wait_for_server(port: int, name: str) -> None:
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    for _ in range(60):
        try:
            with opener.open(f"http://127.0.0.1:{port}/healthz" if port == 7860 else f"http://127.0.0.1:{port}/", timeout=3) as response:
                if response.status == 200:
                    return
        except Exception:
            time.sleep(1)
    raise RuntimeError(f"{name} did not become ready within 60 seconds")


def main() -> None:
    username = "rvc"
    password = secret_value("RVC_WEB_PASSWORD") or secrets.token_urlsafe(12)
    kaggle_username = secret_value("KAGGLE_USERNAME")
    kaggle_key = secret_value("KAGGLE_KEY")
    resume_dataset = secret_value("RVC_RESUME_DATASET")
    if kaggle_username and kaggle_key:
        os.environ["KAGGLE_USERNAME"] = kaggle_username
        os.environ["KAGGLE_KEY"] = kaggle_key
    if resume_dataset:
        import kagglehub

        os.environ["RVC_RESUME_ROOT"] = kagglehub.dataset_download(resume_dataset)
        print(f"[RVC] 已下载恢复数据集：{resume_dataset}")

    environment = os.environ.copy()
    environment["PYTHONNOUSERSITE"] = "1"
    environment["PYTHONUNBUFFERED"] = "1"
    environment["PYTHONPATH"] = str(ROOT / "src") + os.pathsep + environment.get(
        "PYTHONPATH", ""
    )
    environment["RVC_CONTROL_USER"] = username
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
    control_command = [sys.executable, "-u", "-m", "ultimate_rvc.control.app", "--host", "127.0.0.1", "--port", "7860"]

    def start_control() -> subprocess.Popen[str]:
        process = subprocess.Popen(
            control_command, cwd=ROOT, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True, bufsize=1, env=environment,
        )
        processes.append(process)
        threading.Thread(target=stream, args=(process, []), daemon=True).start()
        return process

    control = start_control()
    wait_for_server(7860, "RVC control console")

    # Gradio 备用界面已禁用（保留代码，恢复时取消以下注释）
    # gradio = subprocess.Popen(
    #     [
    #         sys.executable,
    #         "-u",
    #         "src/ultimate_rvc/web/main.py",
    #         "--listen",
    #         "--listen-host",
    #         "127.0.0.1",
    #         "--listen-port",
    #         "7861",
    #         "--auth-user",
    #         username,
    #         "--auth-password",
    #         password,
    #     ],
    #     cwd=ROOT,
    #     stdout=subprocess.PIPE,
    #     stderr=subprocess.STDOUT,
    #     text=True,
    #     bufsize=1,
    #     env=environment,
    # )
    # processes.append(gradio)
    # threading.Thread(target=stream, args=(gradio, []), daemon=True).start()
    # wait_for_server(7861, "RVC Gradio fallback")

    cloudflared = ROOT / "cloudflared-linux-amd64"
    if not cloudflared.exists():
        print("[RVC] 下载 cloudflared...", flush=True)
        import urllib.request
        url = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64"
        try:
            urllib.request.urlretrieve(url, str(cloudflared))
            cloudflared.chmod(0o755)
            print("[RVC] cloudflared 下载完成", flush=True)
        except Exception as e:
            print(f"[RVC] cloudflared 下载失败: {e}", flush=True)
            print("[RVC] 跳过隧道，直接访问 http://127.0.0.1:7860", flush=True)
            cloudflared = None

    if cloudflared and cloudflared.exists():
        tunnel = subprocess.Popen(
            [str(cloudflared), "tunnel", "--url", "http://127.0.0.1:7860"],
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        processes.append(tunnel)
        lines: list[str] = []
        threading.Thread(target=stream, args=(tunnel, lines), daemon=True).start()
        url = None
        for _ in range(60):
            url_match = re.search(r"https://[\w.-]+\.trycloudflare\.com", "\n".join(lines[-30:]))
            if url_match:
                url = url_match.group(0)
                break
            if tunnel.poll() is not None:
                break
            time.sleep(1)
        if not url:
            raise RuntimeError("Cloudflare tunnel failed to provide a URL")
        print("\n" + "=" * 60)
        print(f"训练控制台: {url}")
        print(f"用户名: {username}")
        print(f"密码: {password}")
        print("=" * 60 + "\n")
    else:
        print("\n" + "=" * 60)
        print(f"训练控制台: http://127.0.0.1:7860")
        print(f"用户名: {username}")
        print(f"密码: {password}")
        print("=" * 60 + "\n")
    while not shutting_down:
        exit_code = control.wait()
        if shutting_down:
            break
        print(f"[RVC] 控制服务退出 ({exit_code})，2 秒后自动恢复", flush=True)
        time.sleep(2)
        control = start_control()
        wait_for_server(7860, "RVC control console")


atexit.register(stop_processes)
signal.signal(signal.SIGTERM, stop_processes)
signal.signal(signal.SIGINT, stop_processes)

if __name__ == "__main__":
    main()
