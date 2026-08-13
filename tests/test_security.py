from __future__ import annotations

import os
import sys
import types
import zipfile
from pathlib import Path

import pytest

from ultimate_rvc.security import (
    load_torch_checkpoint,
    safe_child,
    safe_extract_zip,
    validate_remote_url,
)


def test_safe_child_rejects_path_traversal(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        safe_child(tmp_path, "../outside")
    with pytest.raises(ValueError):
        safe_child(tmp_path, str(tmp_path.parent / "outside"))


def test_safe_extract_rejects_traversal(tmp_path: Path) -> None:
    archive_path = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("../outside.txt", "unsafe")
    with zipfile.ZipFile(archive_path) as archive, pytest.raises(ValueError):
        safe_extract_zip(archive, tmp_path / "output")
    assert not (tmp_path / "outside.txt").exists()


def test_safe_extract_rejects_symbolic_link(tmp_path: Path) -> None:
    archive_path = tmp_path / "link.zip"
    info = zipfile.ZipInfo("link")
    info.external_attr = (0o120777 << 16)
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr(info, "target")
    with zipfile.ZipFile(archive_path) as archive, pytest.raises(ValueError):
        safe_extract_zip(archive, tmp_path / "output")


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com/model.zip",
        "https://127.0.0.1/model.zip",
        "https://localhost/model.zip",
        "https://user@example.com/model.zip",
        "https://example.com/model.zip",
    ],
)
def test_remote_url_rejects_unsafe_targets(url: str) -> None:
    with pytest.raises(ValueError):
        validate_remote_url(url)


def test_torch_loader_blocks_pickle_code(tmp_path: Path) -> None:
    torch = pytest.importorskip("torch")
    marker = tmp_path / "executed"

    class Payload:
        def __reduce__(self):
            return os.system, (f'echo unsafe > "{marker}"',)

    path = tmp_path / "malicious.pth"
    torch.save(Payload(), path)
    with pytest.raises(Exception):
        load_torch_checkpoint(path)
    assert not marker.exists()


def test_torch_loader_always_enables_weights_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, object] = {}

    def fake_load(path: Path, **kwargs: object) -> dict[str, object]:
        captured.update(kwargs)
        return {}

    monkeypatch.setitem(sys.modules, "torch", types.SimpleNamespace(load=fake_load))
    load_torch_checkpoint(tmp_path / "model.pth")
    assert captured["weights_only"] is True
    assert captured["map_location"] == "cpu"
