from __future__ import annotations

from pathlib import Path

import pytest

from ultimate_rvc.core.train import train as train_module
from ultimate_rvc.typing_extra import RVCVersion, TrainingSampleRate


class FakeTensor:
    def __init__(self, shape: tuple[int, ...]) -> None:
        self.shape = shape


def test_multi_gpu_training_keeps_batch_size_per_device() -> None:
    source = (
        Path(__file__).parents[1]
        / "src"
        / "ultimate_rvc"
        / "rvc"
        / "train"
        / "train.py"
    ).read_text(encoding="utf-8")

    assert "batch_size * n_gpus" not in source
    assert '"nccl" if device.type == "cuda"' in source
    assert "dist.all_reduce(loss_totals" in source


def _checkpoint_data(
    *,
    feature_dim: int = 768,
    f0: bool = True,
    first_upsample_kernel: int = 24,
    metadata: dict[str, object] | None = None,
) -> tuple[dict[str, object], dict[str, object]]:
    state: dict[str, object] = {
        "enc_p.emb_phone.weight": FakeTensor((192, feature_dim)),
        "dec.ups.0.weight_v": FakeTensor((192, 96, first_upsample_kernel)),
    }
    if f0:
        state["enc_p.emb_pitch.weight"] = FakeTensor((256, 192))
    return dict(metadata or {}), state


def _mock_checkpoint(
    monkeypatch: pytest.MonkeyPatch,
    checkpoint: tuple[dict[str, object], dict[str, object]],
) -> None:
    monkeypatch.setattr(
        train_module,
        "_checkpoint_model_state",
        lambda path: checkpoint,
    )


def test_pretrained_generator_accepts_matching_tensor_structure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _mock_checkpoint(monkeypatch, _checkpoint_data())

    train_module._validate_pretrained_generator(
        Path("G.pth"),
        TrainingSampleRate.HZ_48K,
        RVCVersion.V2,
        True,
    )


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"feature_dim": 256}, "版本"),
        ({"f0": False}, "F0"),
        ({"first_upsample_kernel": 16}, "sample rate"),
    ],
)
def test_pretrained_generator_rejects_incompatible_structure(
    monkeypatch: pytest.MonkeyPatch,
    kwargs: dict[str, object],
    message: str,
) -> None:
    _mock_checkpoint(monkeypatch, _checkpoint_data(**kwargs))

    with pytest.raises((OSError, ValueError), match=message):
        train_module._validate_pretrained_generator(
            Path("G.pth"),
            TrainingSampleRate.HZ_48K,
            RVCVersion.V2,
            True,
        )


def test_pretrained_generator_prefers_checkpoint_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _mock_checkpoint(
        monkeypatch,
        _checkpoint_data(
            first_upsample_kernel=16,
            metadata={"version": "v2", "f0": 1, "sample_rate": 48000},
        ),
    )

    train_module._validate_pretrained_generator(
        Path("G.pth"),
        TrainingSampleRate.HZ_48K,
        RVCVersion.V2,
        True,
    )
