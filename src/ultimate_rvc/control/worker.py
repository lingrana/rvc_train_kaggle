"""Subprocess entry point for control-service jobs."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

from ultimate_rvc.control.jobs import JOBS_DIR, read_job, update_job
from ultimate_rvc.rvc.train.delivery import atomic_json_dump
from ultimate_rvc.typing_extra import (
    AudioNormalizationMode,
    AudioSplitMethod,
    DeviceType,
    EmbedderModel,
    F0Method,
    IndexAlgorithm,
    PrecisionType,
    PretrainedType,
    RVCVersion,
    TrainingSampleRate,
    Vocoder,
)


def preprocess(params: dict[str, Any], started_at: float | None = None) -> None:
    from ultimate_rvc.common import TRAINING_MODELS_DIR
    from ultimate_rvc.control.registry import mark_stage
    from ultimate_rvc.rvc.train.progress import update_progress

    model_dir = TRAINING_MODELS_DIR / params["model_name"]
    model_dir.mkdir(parents=True, exist_ok=True)
    started = started_at or time.time()

    try:
        from ultimate_rvc.core.train.prepare import preprocess_dataset  # noqa: PLC0415

        preprocess_dataset(
            params["model_name"], params["dataset"],
            TrainingSampleRate(int(params.get("sample_rate", 48000))),
            AudioNormalizationMode(params.get("normalization_mode", "post")),
            bool(params.get("filter_audio", True)), bool(params.get("clean_audio", False)),
            float(params.get("clean_strength", 0.7)),
            AudioSplitMethod(params.get("split_method", "Automatic")),
            float(params.get("chunk_len", 3.0)), float(params.get("overlap_len", 0.3)),
            int(params.get("preprocess_cores", params.get("cpu_cores", 2))),
        )
    except Exception:
        update_progress(model_dir, phase="failed", stage_detail="预处理失败", done=False)
        raise
    elapsed = time.time() - started
    mark_stage(params["model_name"], "preprocess", elapsed)
    update_progress(
        model_dir, phase="preprocessing", percent=100, stage_detail="预处理完成", done=False,
    )


def extract(params: dict[str, Any], started_at: float | None = None) -> None:
    from ultimate_rvc.common import TRAINING_MODELS_DIR
    from ultimate_rvc.control.registry import mark_stage
    from ultimate_rvc.rvc.train.progress import update_progress

    model_dir = TRAINING_MODELS_DIR / params["model_name"]
    started = started_at or time.time()

    try:
        from ultimate_rvc.core.train.extract import extract_features  # noqa: PLC0415

        extract_features(
            params["model_name"], F0Method(params.get("f0_method", "rmvpe")),
            EmbedderModel(params.get("embedder_model", "local-hubert-base")),
            params.get("custom_embedder_model") or None,
            int(params.get("include_mutes", 2)),
            int(params.get("extraction_cores", params.get("cpu_cores", 2))),
            DeviceType(params.get("extraction_device", params.get("device", "Automatic"))),
            set(params.get("extraction_gpu_ids", params.get("gpu_ids", []))) or None,
        )
    except Exception:
        update_progress(model_dir, phase="failed", stage_detail="特征提取失败", done=False)
        raise
    elapsed = time.time() - started
    mark_stage(params["model_name"], "extract", elapsed)
    update_progress(
        model_dir, phase="extracting_embed", percent=100, stage_detail="特征提取完成", done=False,
    )


def train(params: dict[str, Any], started_at: float | None = None) -> Any:
    from ultimate_rvc.core.train.train import run_training

    started = started_at or time.time()
    result = run_training(
        params["model_name"], RVCVersion(params.get("version", "v2")),
        bool(params.get("f0_guidance", True)),
        int(params.get("epochs", 300)), int(params.get("batch_size", 8)),
        bool(params.get("detect_overtraining", True)), int(params.get("overtraining_threshold", 50)),
        Vocoder(params.get("vocoder", "HiFi-GAN")),
        IndexAlgorithm(params.get("index_algorithm", "Faiss")),
        PretrainedType(params.get("pretrained_type", "Default")),
        params.get("custom_pretrained_model") or None,
        int(params.get("save_interval", 25)),
        bool(params.get("save_all_checkpoints", False)),
        bool(params.get("save_all_weights", False)),
        bool(params.get("clear_saved_data", False)),
        bool(params.get("upload_model", False)),
        params.get("upload_name") or None,
        DeviceType(params.get("training_device", params.get("device", "Automatic"))),
        set(params.get("training_gpu_ids", params.get("gpu_ids", []))) or None,
        PrecisionType(params.get("precision", "fp32")),
        bool(params.get("preload_dataset", False)),
        bool(params.get("reduce_memory_usage", False)),
        started_at=started_at,
    )
    return result


def ensure_models() -> None:
    """Download any missing RVC prerequisites (pitch predictors, embedders,
    pretrained weights) before a pipeline stage runs."""
    from ultimate_rvc.rvc.lib.tools.prerequisites_download import (
        prequisites_download_pipeline,
    )

    prequisites_download_pipeline(exe=False)


def run(job_id: str) -> None:
    job = read_job(job_id)
    params = job["params"]
    try:
        from ultimate_rvc.common import TRAINING_MODELS_DIR
        from ultimate_rvc.control.registry import mark_stage, reset_stage
        from ultimate_rvc.rvc.train.progress import update_progress

        model_dir = TRAINING_MODELS_DIR / str(params.get("model_name", ""))
        model_dir.mkdir(parents=True, exist_ok=True)
        job_created_at = float(job.get("created_at") or time.time())
        prepared_at = time.time()
        initial_stage = {
            "preprocess": "preprocessing",
            "extract": "extracting_pitch",
            "train": "training",
            "pipeline": "preprocessing",
        }.get(job["type"], "preprocessing")
        initial_job_stage = {
            "preprocess": "preprocessing",
            "extract": "extracting",
            "train": "training",
            "pipeline": "preprocessing",
        }.get(job["type"], "preprocessing")
        update_job(
            job_id,
            stage=initial_job_stage,
            stage_started_at=prepared_at,
        )
        update_progress(
            model_dir,
            phase=initial_stage,
            percent=0,
            stage_detail="正在检查运行环境…",
            done=False,
            started_at=job_created_at,
            stage_started_at=prepared_at,
            phase_started_at=prepared_at,
            reset_percent=True,
        )
        ensure_models()
        if job["type"] == "preprocess":
            reset_stage(params["model_name"], "preprocess")
            result = preprocess(params, started_at=prepared_at)
        elif job["type"] == "extract":
            reset_stage(params["model_name"], "extract")
            result = extract(params, started_at=prepared_at)
        elif job["type"] == "train":
            reset_stage(params["model_name"], "train")
            result = train(params, started_at=prepared_at)
        else:
            reset_stage(params["model_name"], "preprocess")
            preprocess(params, started_at=prepared_at)
            _stage_at = time.time()
            update_job(job_id, stage="extracting", stage_started_at=_stage_at)
            update_progress(
                model_dir,
                phase="extracting_pitch",
                percent=0,
                stage_detail="正在检查特征提取环境…",
                stage_started_at=_stage_at,
                reset_percent=True,
            )
            reset_stage(params["model_name"], "extract")
            extract(params, started_at=_stage_at)
            _train_stage_at = time.time()
            update_job(job_id, stage="training", stage_started_at=_train_stage_at)
            update_progress(
                model_dir,
                phase="training",
                percent=0,
                stage_detail="正在准备训练环境…",
                stage_started_at=_train_stage_at,
                reset_percent=True,
            )
            reset_stage(params["model_name"], "train")
            result = train(params, started_at=_train_stage_at)
        train_stage_started_at = (
            prepared_at
            if job["type"] == "train"
            else locals().get("_train_stage_at", prepared_at)
        )
        if job["type"] in {"train", "pipeline"} and params.get("upload_kaggle", True):
            update_job(job_id, stage="uploading")
            from ultimate_rvc.control.kaggle_delivery import upload_model
            from ultimate_rvc.common import TRAINING_MODELS_DIR
            from ultimate_rvc.rvc.train.progress import update_progress

            update_progress(
                TRAINING_MODELS_DIR / params["model_name"],
                phase="uploading",
                phase_label="步骤4 · 上传阶段",
                percent=98,
                stage_detail="正在上传模型…",
                done=False,
            )
            upload = upload_model(params["model_name"])
            if upload.get("errors"):
                warning = "；".join(str(item) for item in upload["errors"])
                update_progress(
                    TRAINING_MODELS_DIR / params["model_name"],
                    phase="completed",
                    percent=100,
                    done=True,
                    upload_failed=True,
                    warning=f"Kaggle 上传失败：{warning}",
                )
            else:
                update_progress(
                    TRAINING_MODELS_DIR / params["model_name"],
                    phase="completed",
                    percent=100,
                    done=True,
                    upload_failed=False,
                    warning="",
                )
            result = {"files": result, "upload": upload}
        if job["type"] in {"train", "pipeline"}:
            mark_stage(
                params["model_name"],
                "train",
                time.time() - train_stage_started_at,
            )
            if not params.get("upload_kaggle", True):
                update_progress(
                    TRAINING_MODELS_DIR / params["model_name"],
                    phase="completed",
                    percent=100,
                    done=True,
                    upload_failed=False,
                    warning="",
                )
        payload = {"ok": True, "result": result, "finished_at": time.time()}
    except BaseException as error:
        payload = {"ok": False, "error": f"{type(error).__name__}: {error}", "finished_at": time.time()}
    atomic_json_dump(payload, JOBS_DIR / job_id / "result.json")


if __name__ == "__main__":
    run(sys.argv[1])
