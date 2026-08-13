from __future__ import annotations

import json
from pathlib import Path

import pytest

from ultimate_rvc.rvc.train.delivery import (
    delivery_files,
    prepare_delivery_files,
    validate_model_name,
)
from ultimate_rvc.rvc.train.resume import (
    create_resume_snapshot,
    restore_resume_snapshot,
)


@pytest.mark.parametrize("name", ["voice", "voice_01", "voice-name"])
def test_validate_model_name_accepts_portable_names(name: str) -> None:
    assert validate_model_name(name) == name


@pytest.mark.parametrize("name", ["../voice", "voice/name", "voice name", "中文"])
def test_validate_model_name_rejects_unsafe_names(name: str) -> None:
    with pytest.raises(ValueError):
        validate_model_name(name)


def test_prepare_delivery_files_creates_only_three_named_artifacts(tmp_path: Path) -> None:
    name = "voice"
    (tmp_path / f"{name}_best.pth").write_bytes(b"pth")
    (tmp_path / f"{name}.index").write_bytes(b"index")
    (tmp_path / "train.log").write_text("log", encoding="utf-8")

    files = prepare_delivery_files(tmp_path, name)

    assert set(files) == {"pth", "index", "log"}
    assert files == delivery_files(tmp_path, name)
    assert files["pth"].read_bytes() == b"pth"
    assert files["index"].read_bytes() == b"index"
    assert files["log"].read_text("utf-8") == "log"


def test_resume_snapshot_round_trip_clears_stale_pids(tmp_path: Path) -> None:
    source = tmp_path / "voice"
    source.mkdir()
    (source / "G_2333333.pth").write_bytes(b"generator")
    (source / "D_2333333.pth").write_bytes(b"discriminator")
    (source / "config.json").write_text(
        json.dumps({"process_pids": [1234], "train": {"seed": 1}}), "utf-8"
    )
    (source / "progress.json").write_text(json.dumps({"epoch": 25}), "utf-8")
    snapshot = create_resume_snapshot(source)

    target = tmp_path / "restored" / "voice"
    epoch = restore_resume_snapshot(snapshot, target)

    assert epoch == 25
    assert (target / "G_2333333.pth").read_bytes() == b"generator"
    assert "process_pids" not in json.loads((target / "config.json").read_text("utf-8"))


def test_resume_snapshot_rejects_corruption(tmp_path: Path) -> None:
    source = tmp_path / "voice"
    source.mkdir()
    (source / "G_2333333.pth").write_bytes(b"generator")
    (source / "D_2333333.pth").write_bytes(b"discriminator")
    snapshot = create_resume_snapshot(source)
    (snapshot / "G_2333333.pth").write_bytes(b"corrupted")

    with pytest.raises(ValueError, match="损坏"):
        restore_resume_snapshot(snapshot, tmp_path / "other" / "voice")
