import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
import uuid
from pathlib import Path

import pytest

from ultimate_rvc.control import jobs


def test_refresh_collects_worker_result(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(jobs, "JOBS_DIR", tmp_path / "jobs")
    job_id = str(uuid.uuid4())
    directory = jobs.JOBS_DIR / job_id
    directory.mkdir(parents=True)
    state = {"id": job_id, "phase": "running", "pid": 999999999, "params": {}, "created_at": 1}
    (directory / "job.json").write_text(json.dumps(state), "utf-8")
    (directory / "result.json").write_text(json.dumps({"ok": True, "result": ["x"], "finished_at": 2}), "utf-8")
    result = jobs.read_job(job_id)
    assert result["phase"] == "completed"
    assert result["result"] == ["x"]


def test_refresh_exposes_cached_kaggle_dataset_url(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(jobs, "JOBS_DIR", tmp_path / "jobs")
    monkeypatch.setattr(jobs, "TRAINING_MODELS_DIR", tmp_path / "models")
    model_dir = jobs.TRAINING_MODELS_DIR / "voice"
    model_dir.mkdir(parents=True)
    for filename in ("voice.pth", "voice.index", "voice_train.log"):
        (model_dir / filename).touch()
    expected = "https://www.kaggle.com/datasets/owner/rvc-voice"
    (model_dir / "kaggle_urls.json").write_text(
        json.dumps({"kaggle": expected}), "utf-8"
    )
    job_id = str(uuid.uuid4())
    directory = jobs.JOBS_DIR / job_id
    directory.mkdir(parents=True)
    state = {
        "id": job_id,
        "phase": "completed",
        "params": {"model_name": "voice"},
        "created_at": 1,
    }
    (directory / "job.json").write_text(json.dumps(state), "utf-8")

    result = jobs.read_job(job_id)

    assert result["kaggle_url"] == expected


def test_invalid_job_id_is_rejected() -> None:
    try:
        jobs.read_job("../outside")
    except ValueError:
        pass
    else:
        raise AssertionError("unsafe job ID was accepted")


class ControlJobsUnitTest(unittest.TestCase):
    def test_result_recovery_and_path_validation(self) -> None:
        original = jobs.JOBS_DIR
        with tempfile.TemporaryDirectory() as temporary:
            jobs.JOBS_DIR = Path(temporary) / "jobs"
            try:
                job_id = str(uuid.uuid4())
                directory = jobs.JOBS_DIR / job_id
                directory.mkdir(parents=True)
                state = {
                    "id": job_id,
                    "phase": "running",
                    "pid": 999999999,
                    "params": {},
                    "created_at": 1,
                }
                (directory / "job.json").write_text(json.dumps(state), "utf-8")
                (directory / "result.json").write_text(
                    json.dumps({"ok": True, "result": ["x"], "finished_at": 2}),
                    "utf-8",
                )
                result = jobs.read_job(job_id)
                self.assertEqual(result["phase"], "completed")
                self.assertEqual(result["result"], ["x"])
                with self.assertRaises(ValueError):
                    jobs.read_job("../outside")
            finally:
                jobs.JOBS_DIR = original


def test_concurrent_submissions_start_only_one_worker(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(jobs, "CONTROL_DIR", tmp_path / "control")
    monkeypatch.setattr(jobs, "JOBS_DIR", tmp_path / "control" / "jobs")
    dataset = tmp_path / "dataset"
    dataset.mkdir()
    started: list[int] = []

    class Process:
        pid = 12345

    def fake_popen(*args, **kwargs):
        started.append(1)
        return Process()

    monkeypatch.setattr(jobs.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(jobs, "pid_alive", lambda pid: bool(pid))
    params = {"model_name": "voice", "dataset": str(dataset)}
    barrier = threading.Barrier(2)
    results: list[tuple[dict, bool]] = []

    def submit() -> None:
        barrier.wait()
        results.append(jobs.create_job("preprocess", dict(params)))

    threads = [threading.Thread(target=submit) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len(started) == 1
    assert sorted(created for _, created in results) == [False, True]


@pytest.mark.skipif(os.name == "nt", reason="zombie reaping is POSIX-only")
def test_refresh_reaps_crashed_worker_zombie(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(jobs, "JOBS_DIR", tmp_path / "jobs")
    child = subprocess.Popen([sys.executable, "-c", "pass"])
    child.wait()
    assert jobs.pid_alive(child.pid) is True
    job_id = str(uuid.uuid4())
    directory = jobs.JOBS_DIR / job_id
    directory.mkdir(parents=True)
    state = {"id": job_id, "phase": "running", "pid": child.pid, "params": {}, "created_at": 1}
    (directory / "job.json").write_text(json.dumps(state), "utf-8")
    result = jobs.read_job(job_id)
    assert result["phase"] == "failed"
    child.wait()
