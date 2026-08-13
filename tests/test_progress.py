import json
import time
from pathlib import Path

from ultimate_rvc.rvc.train.progress import (
    initialize_progress,
    mark_failed,
    mark_stopped,
    read_progress,
    tail_log,
    update_progress,
)


def test_progress_lifecycle(tmp_path: Path) -> None:
    state = initialize_progress(tmp_path, 10)
    assert state["phase"] == "starting"
    assert state["done"] is False
    assert state["total_epochs"] == state["total"] == 10

    state = update_progress(
        tmp_path, phase="training", epoch=2, batch=5, total_batches=10
    )
    assert state["percent"] == 25
    assert state["heartbeat_at"] <= time.time()

    for phase in ("indexing", "validating"):
        state = update_progress(tmp_path, phase=phase)
        assert state["done"] is False

    state = update_progress(tmp_path, phase="completed", percent=100, done=True)
    assert state["done"] is True
    assert read_progress(tmp_path / "progress.json")["phase_label"]


def test_upload_phase_preserves_download_ready_state(tmp_path: Path) -> None:
    initialize_progress(tmp_path, 1)
    update_progress(tmp_path, phase="completed", percent=100, done=True)
    update_progress(tmp_path, phase="uploading", done=True)
    assert read_progress(tmp_path / "progress.json")["done"] is True


def test_terminal_helpers_and_legacy_schema(tmp_path: Path) -> None:
    path = tmp_path / "progress.json"
    path.write_text(json.dumps({"epoch": 3, "total": 3, "done": True}), "utf-8")
    assert read_progress(path)["phase"] == "completed"
    assert mark_stopped(tmp_path)["phase"] == "stopped"
    state = mark_failed(tmp_path, "boom")
    assert state["phase"] == "failed"
    assert state["error"] == "boom"
    assert state["done"] is False


def test_log_tail_is_bounded(tmp_path: Path) -> None:
    path = tmp_path / "train.log"
    path.write_text("\n".join(f"line {number}" for number in range(50)), "utf-8")
    assert tail_log(path, max_lines=3) == ["line 47", "line 48", "line 49"]
