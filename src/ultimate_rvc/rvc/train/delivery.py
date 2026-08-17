"""Validation and metadata helpers for trained RVC delivery artifacts."""

from __future__ import annotations

from typing import Any

import hashlib
import json
import os
import tempfile
from pathlib import Path

from ultimate_rvc.security import load_torch_checkpoint, validate_safe_name


def validate_model_name(model_name: str) -> str:
    """Return a safe model name or raise before it is used in a path or URL."""
    return validate_safe_name(model_name)


def delivery_files(model_dir: Path, model_name: str) -> dict[str, Path]:
    """Return the three public delivery files using matching model basenames."""
    name = validate_model_name(model_name)
    return {
        "pth": model_dir / f"{name}.pth",
        "index": model_dir / f"{name}.index",
        "log": model_dir / f"{name}_train.log",
    }


def prepare_delivery_files(model_dir: Path, model_name: str) -> dict[str, Path]:
    """Create stable public filenames without changing the trainer's internals."""
    files = delivery_files(model_dir, model_name)
    sources = {
        "pth": model_dir / f"{model_name}_best.pth",
        "index": model_dir / f"{model_name}.index",
        "log": model_dir / "train.log",
    }
    for kind, source in sources.items():
        destination = files[kind]
        if not source.is_file():
            raise FileNotFoundError(f"缺少训练产物：{source.name}")
        if source.resolve() == destination.resolve():
            continue
        temporary = destination.with_suffix(destination.suffix + ".tmp")
        with source.open("rb") as reader, temporary.open("wb") as writer:
            while chunk := reader.read(1024 * 1024):
                writer.write(chunk)
        Path(temporary).replace(destination)
    return files


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        while chunk := file.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_json_dump(data: Any, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            json.dump(data, file, indent=2, ensure_ascii=False)
            file.flush()
            os.fsync(file.fileno())
        Path(temporary_name).replace(path)
    except Exception:
        try:
            Path(temporary_name).unlink()
        except OSError:
            pass
        raise


def validate_delivery(model_dir: Path, model_name: str) -> dict[str, Any]:
    """Validate that exported artifacts load as a supported RVC v2 model."""
    import faiss
    import torch

    files = delivery_files(model_dir, model_name)
    missing = [path.name for path in files.values() if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"缺少可下载文件：{', '.join(missing)}")

    checkpoint = load_torch_checkpoint(files["pth"])
    if not isinstance(checkpoint, dict):
        raise ValueError("推理模型不是有效的 RVC checkpoint")
    weights = checkpoint.get("weight")
    config = checkpoint.get("config")
    if not isinstance(weights, dict) or not weights:
        raise ValueError("推理模型缺少 weight")
    if not isinstance(config, (list, tuple)) or len(config) != 18:
        raise ValueError("推理模型 config 必须包含 18 项")
    if checkpoint.get("version") != "v2":
        raise ValueError("推理模型不是 RVC v2")
    sample_rate = int(checkpoint.get("sr", config[-1]))
    if sample_rate not in {32000, 40000, 48000} or int(config[-1]) != sample_rate:
        raise ValueError("推理模型采样率无效或 config 不一致")
    f0_guidance = bool(int(checkpoint.get("f0", 0)))
    if checkpoint.get("vocoder", "HiFi-GAN") != "HiFi-GAN":
        raise ValueError("推理模型不是标准 HiFi-GAN")
    if "emb_g.weight" not in weights:
        raise ValueError("推理模型缺少 emb_g.weight")
    if any("enc_q" in key for key in weights):
        raise ValueError("推理小模型仍包含仅训练使用的 enc_q")

    from ultimate_rvc.rvc.lib.algorithm.synthesizers import Synthesizer

    network = Synthesizer(
        *config,
        use_f0=f0_guidance,
        text_enc_hidden_dim=768,
        vocoder="HiFi-GAN",
    )
    del network.enc_q
    incompatible = network.load_state_dict(weights, strict=False)
    missing_keys = [key for key in incompatible.missing_keys if "enc_q" not in key]
    if missing_keys or incompatible.unexpected_keys:
        raise ValueError(
            "模型权重与 RVC v2 结构不兼容："
            f"missing={missing_keys[:5]}, unexpected={incompatible.unexpected_keys[:5]}"
        )
    network.eval()
    frames = 12
    with torch.inference_mode():
        audio, *_ = network.infer(
            torch.zeros((1, frames, 768), dtype=torch.float32),
            torch.tensor([frames], dtype=torch.long),
            torch.full((1, frames), 128, dtype=torch.long),
            torch.full((1, frames), 220.0, dtype=torch.float32),
            torch.zeros((1,), dtype=torch.long),
        )
    if audio.numel() == 0 or not bool(torch.isfinite(audio).all()):
        raise ValueError("生成器短帧推理输出无效")
    if float(audio.abs().max()) <= 1e-7:
        raise ValueError("生成器短帧推理输出为全静音")
    smoke_samples = int(audio.numel())
    del network, checkpoint, audio

    index = faiss.read_index(str(files["index"]))
    if index.d != 768 or index.ntotal <= 0:
        raise ValueError(f"索引无效：dimension={index.d}, vectors={index.ntotal}")

    result = {
        "compatible": True,
        "version": "v2",
        "sample_rate": sample_rate,
        "f0": int(f0_guidance),
        "index_dimension": int(index.d),
        "index_vectors": int(index.ntotal),
        "generator_smoke_samples": smoke_samples,
        "files": {
            kind: {
                "name": path.name,
                "size": path.stat().st_size,
                "sha256": sha256_file(path),
            }
            for kind, path in files.items()
        },
    }
    atomic_json_dump(result, model_dir / "delivery.json")
    return result
