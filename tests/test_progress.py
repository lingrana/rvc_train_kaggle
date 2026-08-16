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
    assert state["percent"] == 26.25
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


def test_training_percent_tracks_epochs_not_elapsed(tmp_path: Path) -> None:
    initialize_progress(tmp_path, 100, started_at=time.time() - 30)
    state = update_progress(
        tmp_path,
        phase="training",
        epoch=5,
        batch=0,
        total_batches=10,
        elapsed_seconds=30,
        eta_seconds=70,
        done=False,
    )
    assert state["percent"] == 9.25
    assert read_progress(tmp_path / "progress.json")["percent"] == 9.25

    state = update_progress(
        tmp_path,
        phase="training",
        epoch=50,
        batch=5,
        total_batches=10,
        elapsed_seconds=100_000,
        eta_seconds=0,
        done=False,
    )
    assert state["percent"] == 47.925

    state = update_progress(tmp_path, phase="completed", done=True)
    assert state["percent"] == 100


def test_stage_elapsed_survives_training_milestones(tmp_path: Path) -> None:
    started = time.time() - 10
    initialize_progress(
        tmp_path,
        10,
        started_at=started,
        stage_started_at=started,
        phase="training",
    )
    training = update_progress(tmp_path, phase="training", epoch=1, total_batches=1)
    indexing = update_progress(tmp_path, phase="indexing")
    validating = update_progress(tmp_path, phase="validating")

    assert training["phase_label"] == "步骤4 · 模型训练"
    assert indexing["phase_label"] == "步骤4 · 生成索引"
    assert validating["phase_label"] == "步骤4 · 验证模型"
    assert indexing["stage_elapsed_seconds"] >= training["stage_elapsed_seconds"]
    assert validating["stage_elapsed_seconds"] >= indexing["stage_elapsed_seconds"]


def test_preparing_percent_can_reset_to_zero(tmp_path: Path) -> None:
    update_progress(tmp_path, phase="preprocessing", percent=60, done=False)
    state = update_progress(
        tmp_path,
        phase="preparing",
        percent=0,
        reset_percent=True,
        done=False,
    )
    assert state["percent"] == 0


def test_upload_failed_flag_is_preserved(tmp_path: Path) -> None:
    state = update_progress(
        tmp_path,
        phase="completed",
        percent=100,
        done=True,
        upload_failed=True,
        phase_label="步骤4 · 训练完成",
    )
    got = read_progress(tmp_path / "progress.json")
    assert got["upload_failed"] is True
    assert got["phase_label"] == "步骤4 · 训练完成"


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
