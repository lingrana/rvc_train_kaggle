import json
import tempfile
import threading
import unittest
import uuid
from pathlib import Path

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
