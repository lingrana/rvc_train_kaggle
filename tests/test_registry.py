import pytest

import ultimate_rvc.control.registry as registry


@pytest.fixture
def registry_path(tmp_path, monkeypatch):
    path = tmp_path / "registry.json"
    monkeypatch.setattr(registry, "REGISTRY_PATH", path)
    return path


def test_register_dataset_creates_entry(registry_path):
    entry = registry.register_dataset("MyDataset")
    assert entry["dataset"] == "MyDataset"
    assert entry["stages"]["preprocess"]["done"] is False
    assert entry["stages"]["extract"]["done"] is False
    assert entry["stages"]["train"]["done"] is False
    assert registry_path.is_file()
    assert "MyDataset" in registry.read_registry()


def test_register_is_idempotent(registry_path):
    registry.register_dataset("MyDataset")
    registry.mark_stage("MyDataset", "preprocess", 45.0)
    registry.register_dataset("MyDataset")
    entry = registry.read_registry()["MyDataset"]
    assert entry["stages"]["preprocess"]["done"] is True
    assert entry["stages"]["preprocess"]["elapsed_seconds"] == 45.0


def test_mark_stage_records_timing_and_phase(registry_path):
    registry.mark_stage("Demo", "extract", 12.5)
    entry = registry.read_registry()["Demo"]
    stage = entry["stages"]["extract"]
    assert stage["done"] is True
    assert stage["elapsed_seconds"] == 12.5
    assert stage["finished_at"] > 0
    assert entry["last_phase"] == "extract"
    assert entry["dataset"] == "Demo"


def test_mark_stage_without_timing_keeps_previous(registry_path):
    registry.mark_stage("Demo", "train")
    entry = registry.read_registry()["Demo"]
    assert entry["stages"]["train"]["done"] is True
    assert entry["stages"]["train"]["elapsed_seconds"] is None


def test_reset_stage_clears_completion_on_rerun(registry_path):
    registry.mark_stage("Demo", "preprocess", 123.0)
    entry = registry.read_registry()["Demo"]
    assert entry["stages"]["preprocess"]["done"] is True
    registry.reset_stage("Demo", "preprocess")
    entry = registry.read_registry()["Demo"]
    stage = entry["stages"]["preprocess"]
    assert stage["done"] is False
    assert stage["finished_at"] is None
    assert stage["elapsed_seconds"] is None
    assert entry["stages"]["extract"]["done"] is False


def test_invalid_stage_rejected(registry_path):
    with pytest.raises(ValueError):
        registry.mark_stage("Demo", "bogus")


def test_invalid_name_rejected(registry_path):
    with pytest.raises(ValueError):
        registry.register_dataset("bad/name")
    with pytest.raises(ValueError):
        registry.mark_stage("bad/name", "train")
