from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

torch = pytest.importorskip("torch")

from ultimate_rvc.rvc.train.process.extract_model import extract_model  # noqa: E402
from ultimate_rvc.typing_extra import RVCVersion, Vocoder  # noqa: E402


def _fake_hps() -> SimpleNamespace:
    data = SimpleNamespace(
        filter_length=2048,
        sample_rate=48000,
    )
    model = SimpleNamespace(
        inter_channels=192,
        hidden_channels=192,
        filter_channels=768,
        n_heads=2,
        n_layers=6,
        kernel_size=3,
        p_dropout=0.1,
        resblock="1",
        resblock_kernel_sizes=[3, 7, 11],
        resblock_dilation_sizes=[[1, 3, 5], [1, 3, 5], [1, 3, 5]],
        upsample_rates=[12, 10],
        upsample_initial_channel=512,
        upsample_kernel_sizes=[24, 20],
        spk_embed_dim=109,
        gin_channels=256,
    )
    return SimpleNamespace(data=data, model=model)


def test_extract_model_saves_only_weights_only_safe_payload(tmp_path: Path) -> None:
    model_path = tmp_path / "out" / "demo.pth"
    ckpt = {"enc_p.weight": torch.zeros(4)}

    extract_model(
        ckpt=ckpt,
        sr=48000,
        name="demo",
        model_path=str(model_path),
        epoch=7,
        step=1234,
        hps=_fake_hps(),
        overtrain_info="",
        vocoder=Vocoder.HIFI_GAN,
        pitch_guidance=True,
        version=RVCVersion.V2,
    )

    assert model_path.is_file()

    # torch>=2.6 defaults to weights_only=True; this is exactly the code path
    # third-party inference forks (e.g. original RVC WebUI) use when loading.
    payload = torch.load(model_path, map_location="cpu", weights_only=True)

    assert payload["version"] == "v2"
    assert isinstance(payload["version"], str)
    assert payload["vocoder"] == "HiFi-GAN"
    assert isinstance(payload["vocoder"], str)
    assert payload["f0"] is True
    assert isinstance(payload["sr"], int)
    assert "weight" in payload and "enc_q" not in "".join(payload["weight"])
