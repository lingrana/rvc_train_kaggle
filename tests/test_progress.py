import json
import time
from pathlib import Path

from ultimate_rvc.rvc.train.progress import (
    initialize_progress,
    mark_failed,
    mark_stopped,
    read_progress,
    tail_log,
    tail_log_with_errors,
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


def test_explicit_started_at_resets_elapsed_clocks(tmp_path: Path) -> None:
    update_progress(tmp_path, phase="preprocessing", percent=50, done=False, started_at=1, phase_started_at=1)
    stale = read_progress(tmp_path / "progress.json")
    assert stale["elapsed_seconds"] > 0
    now = time.time()
    state = update_progress(
        tmp_path, phase="preprocessing", percent=0.1, done=False,
        started_at=now, phase_started_at=now,
    )
    assert state["elapsed_seconds"] < 1
    assert state["phase_elapsed_seconds"] < 1


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


def test_error_tail_prefers_error_lines_over_physical_tail(tmp_path: Path) -> None:
    path = tmp_path / "worker.log"
    path.write_text(
        "\n".join(
            ["epoch 1 ok", "epoch 2 ok", "epoch 3 ok"]
            + ["lazy_loader warning %d" % i for i in range(50)]
            + [
                "Traceback (most recent call last):",
                '  File "train.py", line 42, in run',
                "RuntimeError: CUDA out of memory. Tried to allocate 2.00 GiB",
                "所有训练进程已退出，GPU 资源已清理",
            ]
        ),
        "utf-8",
    )
    got = tail_log_with_errors(path, max_lines=30)
    assert any("CUDA out of memory" in line for line in got)
    assert any("Traceback" in line for line in got)
    assert all("lazy_loader" not in line for line in got)


def test_error_tail_falls_back_to_plain_tail_without_hits(tmp_path: Path) -> None:
    path = tmp_path / "worker.log"
    path.write_text("\n".join(f"line {number}" for number in range(50)), "utf-8")
    got = tail_log_with_errors(path, max_lines=3)
    assert got == ["line 47", "line 48", "line 49"]
