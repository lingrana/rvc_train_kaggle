from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from ultimate_rvc.control import kaggle_delivery
from ultimate_rvc.kaggle_auth import kaggle_username
from ultimate_rvc.rvc.train import resume


def load_launcher():
    path = Path(__file__).parents[1] / "tools" / "kaggle_launch.py"
    spec = importlib.util.spec_from_file_location("kaggle_launch_test", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_kaggle_username_uses_new_token_and_whoami(monkeypatch) -> None:
    monkeypatch.setenv("KAGGLE_API_TOKEN", "new-secret-token")
    monkeypatch.delenv("RVC_KAGGLE_USERNAME", raising=False)
    fake = SimpleNamespace(whoami=lambda **kwargs: {"username": "owner"})

    assert kaggle_username(fake) == "owner"
    assert not hasattr(fake, "legacy")


def test_kaggle_username_ignores_legacy_credentials(monkeypatch) -> None:
    monkeypatch.delenv("KAGGLE_API_TOKEN", raising=False)
    monkeypatch.delenv("RVC_KAGGLE_USERNAME", raising=False)
    monkeypatch.setenv("KAGGLE_USERNAME", "legacy-user")
    monkeypatch.setenv("KAGGLE_KEY", "legacy-key")

    assert kaggle_username(SimpleNamespace()) is None


def test_delivery_uploads_three_files_once_and_caches(
    tmp_path: Path, monkeypatch
) -> None:
    model = tmp_path / "voice"
    model.mkdir()
    (model / "progress.json").write_text(json.dumps({"done": True}), "utf-8")
    files = {}
    for suffix in ("pth", "index", "log"):
        path = model / f"voice.{suffix}"
        path.write_bytes(suffix.encode())
        files[suffix] = path
    uploads = []
    fake = SimpleNamespace(
        whoami=lambda **kwargs: {"username": "owner"},
        dataset_upload=lambda *args, **kwargs: uploads.append((args, kwargs)),
    )
    monkeypatch.setenv("KAGGLE_API_TOKEN", "secret")
    monkeypatch.delenv("RVC_KAGGLE_USERNAME", raising=False)
    monkeypatch.setitem(sys.modules, "kagglehub", fake)
    monkeypatch.setattr(kaggle_delivery, "TRAINING_MODELS_DIR", tmp_path)
    monkeypatch.setattr(kaggle_delivery, "prepare_delivery_files", lambda *_: files)
    monkeypatch.setattr(kaggle_delivery, "validate_delivery", lambda *_: {})

    first = kaggle_delivery.upload_model("voice")
    second = kaggle_delivery.upload_model("voice")

    assert first == second
    assert first["kaggle_slug"].startswith("owner/rvc-voice-")
    assert len(uploads) == 1
    uploaded_dir = Path(uploads[0][0][1])
    assert not uploaded_dir.exists()


def test_delivery_failure_keeps_local_result_available(
    tmp_path: Path, monkeypatch
) -> None:
    model = tmp_path / "voice"
    model.mkdir()
    (model / "progress.json").write_text(json.dumps({"done": True}), "utf-8")
    artifact = model / "voice.pth"
    artifact.write_bytes(b"valid")
    fake = SimpleNamespace(
        whoami=lambda **kwargs: {"username": "owner"},
        dataset_upload=lambda *args, **kwargs: (_ for _ in ()).throw(TimeoutError()),
    )
    monkeypatch.setenv("KAGGLE_API_TOKEN", "secret")
    monkeypatch.delenv("RVC_KAGGLE_USERNAME", raising=False)
    monkeypatch.setitem(sys.modules, "kagglehub", fake)
    monkeypatch.setattr(kaggle_delivery, "TRAINING_MODELS_DIR", tmp_path)
    monkeypatch.setattr(kaggle_delivery, "prepare_delivery_files", lambda *_: {"pth": artifact})
    monkeypatch.setattr(kaggle_delivery, "validate_delivery", lambda *_: {})

    result = kaggle_delivery.upload_model("voice")

    assert "上传失败" in result["errors"][0]
    assert artifact.read_bytes() == b"valid"


def test_resume_upload_creates_versions_on_stable_handle(
    tmp_path: Path, monkeypatch
) -> None:
    model = tmp_path / "Voice_01"
    snapshot = model / "resume_state"
    snapshot.mkdir(parents=True)
    (snapshot / "resume_manifest.json").write_text(
        json.dumps({"epoch": 25}), "utf-8"
    )
    uploads = []
    fake = SimpleNamespace(
        whoami=lambda **kwargs: {"username": "owner"},
        dataset_upload=lambda *args, **kwargs: uploads.append((args, kwargs)),
    )
    monkeypatch.setenv("KAGGLE_API_TOKEN", "secret")
    monkeypatch.delenv("RVC_KAGGLE_USERNAME", raising=False)
    monkeypatch.setitem(sys.modules, "kagglehub", fake)

    assert resume.sync_resume_snapshot(model) == "owner/rvc-voice-01-resume"
    assert resume.sync_resume_snapshot(model) == "owner/rvc-voice-01-resume"
    assert [call[0][0] for call in uploads] == [
        "owner/rvc-voice-01-resume",
        "owner/rvc-voice-01-resume",
    ]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("INF https://abc-123.trycloudflare.com ready", "https://abc-123.trycloudflare.com"),
        ("http://localhost:7860", None),
        ("https://example.com", None),
    ],
)
def test_quick_tunnel_url_parser(text: str, expected: str | None) -> None:
    assert load_launcher().parse_tunnel_url([text]) == expected


def test_wait_for_server_accepts_public_health_without_business_auth(monkeypatch) -> None:
    launcher = load_launcher()
    requested: list[str] = []

    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

    class Opener:
        def open(self, url, timeout):
            requested.append(url)
            return Response()

    monkeypatch.setattr(launcher.urllib.request, "build_opener", lambda *_: Opener())
    with patch.object(launcher.urllib.request, "ProxyHandler", return_value=None):
        launcher.wait_for_server(7860)

    assert requested == ["http://127.0.0.1:7860/healthz"]


def test_cloudflared_checksum_mismatch_is_rejected(tmp_path: Path, monkeypatch) -> None:
    launcher = load_launcher()

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def read(self, size):
            if getattr(self, "done", False):
                return b""
            self.done = True
            return b"not-cloudflared"

    monkeypatch.setattr(launcher.urllib.request, "urlopen", lambda *args, **kwargs: Response())
    destination = tmp_path / "cloudflared"

    with pytest.raises(RuntimeError, match="SHA-256"):
        launcher.install_cloudflared(destination)
    assert not destination.exists()
    assert not destination.with_suffix(".download").exists()
