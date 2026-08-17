"""
Module which exposes functionality for training voice conversion
models.
"""

from __future__ import annotations

import logging
import os
import re
import signal
from collections.abc import Mapping
from pathlib import Path

from ultimate_rvc.common import PRETRAINED_MODELS_DIR
from ultimate_rvc.core.common import (
    TRAINING_MODELS_DIR,
    VOICE_MODELS_DIR,
    copy_files_to_new_dir,
    json_dump,
    json_load,
    validate_model,
)
from ultimate_rvc.core.exceptions import (
    Entity,
    ModelAsssociatedEntityNotFoundError,
    ModelExistsError,
    NotProvidedError,
    PretrainedModelIncompatibleError,
    PretrainedModelNotAvailableError,
    Step,
)
from ultimate_rvc.core.train.common import validate_devices
from ultimate_rvc.core.train.typing_extra import ModelInfo, TrainingInfo
from ultimate_rvc.typing_extra import (
    DeviceType,
    IndexAlgorithm,
    PrecisionType,
    PretrainedType,
    RVCVersion,
    TrainingSampleRate,
    Vocoder,
)

logger = logging.getLogger(__name__)


def _checkpoint_model_state(path: str | Path) -> tuple[Mapping[str, object], Mapping[str, object]]:
    """Load a training checkpoint and return its metadata and model state."""
    from ultimate_rvc.security import load_torch_checkpoint

    checkpoint = load_torch_checkpoint(path)
    if not isinstance(checkpoint, Mapping):
        raise ValueError(f"底模不是有效 checkpoint：{Path(path).name}")
    state = checkpoint.get("model")
    if not isinstance(state, Mapping) or not state:
        raise ValueError(f"底模缺少可训练的 model 权重：{Path(path).name}")
    return checkpoint, state


def _state_tensor(state: Mapping[str, object], suffix: str) -> object | None:
    return next((value for key, value in state.items() if key.endswith(suffix)), None)


def _infer_pretrained_sample_rate(
    checkpoint: Mapping[str, object], state: Mapping[str, object]
) -> int | None:
    explicit = checkpoint.get("sample_rate", checkpoint.get("sr"))
    if explicit is not None:
        return int(explicit)
    config = checkpoint.get("config")
    if isinstance(config, (list, tuple)) and config:
        return int(config[-1])

    first_upsample = _state_tensor(state, "dec.ups.0.weight_v")
    if first_upsample is None:
        first_upsample = _state_tensor(
            state, "dec.ups.0.parametrizations.weight.original1"
        )
    shape = getattr(first_upsample, "shape", ())
    kernel_size = int(shape[-1]) if shape else 0
    return {20: 32000, 16: 40000, 24: 48000}.get(kernel_size)


def _validate_pretrained_generator(
    path: str | Path,
    sample_rate: TrainingSampleRate,
    version: RVCVersion,
    f0_guidance: bool,
) -> None:
    """Reject incompatible pretrained generators before GPU workers start."""
    checkpoint, state = _checkpoint_model_state(path)
    phone_weight = _state_tensor(state, "enc_p.emb_phone.weight")
    phone_shape = getattr(phone_weight, "shape", ())
    feature_dim = int(phone_shape[-1]) if phone_shape else 0
    inferred_version = checkpoint.get("version")
    if inferred_version is None:
        inferred_version = {256: "v1", 768: "v2"}.get(feature_dim)
    if str(inferred_version) != version.value:
        raise ValueError(
            f"底模版本不匹配：需要 {version.value}，实际 {inferred_version or '无法识别'}"
        )

    explicit_f0 = checkpoint.get("f0")
    inferred_f0 = bool(int(explicit_f0)) if explicit_f0 is not None else any(
        key.endswith("enc_p.emb_pitch.weight") for key in state
    )
    if inferred_f0 != f0_guidance:
        raise ValueError(
            f"底模 F0 配置不匹配：需要 {int(f0_guidance)}，实际 {int(inferred_f0)}"
        )

    inferred_sample_rate = _infer_pretrained_sample_rate(checkpoint, state)
    if inferred_sample_rate is None:
        raise ValueError(f"无法识别底模采样率：{Path(path).name}")
    if inferred_sample_rate != int(sample_rate):
        raise PretrainedModelIncompatibleError(Path(path).name, sample_rate)


def _validate_pretrained_discriminator(
    path: str | Path,
    sample_rate: TrainingSampleRate,
    vocoder: Vocoder,
) -> None:
    """Validate discriminator metadata when it is present."""
    checkpoint, _ = _checkpoint_model_state(path)
    explicit_sample_rate = checkpoint.get("sample_rate", checkpoint.get("sr"))
    if explicit_sample_rate is not None and int(explicit_sample_rate) != int(sample_rate):
        raise PretrainedModelIncompatibleError(Path(path).name, sample_rate)
    explicit_vocoder = checkpoint.get("vocoder")
    if explicit_vocoder is not None and str(explicit_vocoder) != vocoder.value:
        raise ValueError(
            f"底模声码器不匹配：需要 {vocoder.value}，实际 {explicit_vocoder}"
        )


def _get_pretrained_model(
    pretrained_type: PretrainedType,
    vocoder: Vocoder,
    sample_rate: TrainingSampleRate,
    version: RVCVersion,
    f0_guidance: bool,
    custom_pretrained: str | None = None,
) -> tuple[str, str]:
    """
    Get the pretrained model to finetune a voice model on.

    Parameters
    ----------
    pretrained_type : PretrainedType
        The type of pretrained model to finetune the voice model on
    vocoder : str
        The vocoder to use for audio synthesis when training the voice
        model.
    sample_rate : int
        The sample rate of the preprocessed dataset associated with the
        voice model to be trained.
    custom_pretrained : str, optional
        The name of a custom pretrained model to finetune the voice
        model on

    Returns
    -------
    pg : str
        The path to the generator of the pretrained model to finetune.
    pd : str
        The path to the discriminator of the pretrained model to
        finetune.

    Raises
    ------
    ModelAsssociatedEntityNotFoundError
        If the voice model to be trained does not have an associated
        dataset file list or if a custom pretrained
        generator/discriminator model does not have an associated
        generator or discriminator.
    PretrainedModelIncompatibleError
        if a custom pretrained model is not compatible with the sample
        rate of the preprocessed dataset associated with the voice model
        to be trained.
    PretrainedModelNotAvailableError
        If no default pretrained model is available for the provided
        vocoder and sample rate.

    """
    match pretrained_type:
        case PretrainedType.NONE:
            pg, pd = "", ""
        case PretrainedType.DEFAULT:
            if version != RVCVersion.V2 or not f0_guidance:
                raise ValueError("默认底模仅支持 RVC v2 + F0；其他结构请使用匹配的自定义底模或 None")
            base_path = PRETRAINED_MODELS_DIR / vocoder.lower()
            pg = base_path / f"f0G{str(sample_rate)[:2]}k.pth"
            pd = base_path / f"f0D{str(sample_rate)[:2]}k.pth"
            if not pg.is_file() or not pd.is_file():
                raise PretrainedModelNotAvailableError(
                    name=vocoder, sample_rate=sample_rate, download=False
                )
            pg, pd = str(pg), str(pd)
        case PretrainedType.CUSTOM:
            custom_pretrained_path = validate_model(
                custom_pretrained,
                Entity.CUSTOM_PRETRAINED_MODEL,
            )
            custom_pretrained = custom_pretrained_path.name

            pg = next(
                (
                    str(path)
                    for path in sorted(custom_pretrained_path.iterdir())
                    if re.match(r"^(G|f0G).*\.pth$|.*G\.pth$", path.name)
                ),
                None,
            )
            if pg is None:
                raise ModelAsssociatedEntityNotFoundError(
                    Entity.GENERATOR,
                    custom_pretrained,
                )
            pd = next(
                (
                    str(path)
                    for path in sorted(custom_pretrained_path.iterdir())
                    if re.match(r"^(D|f0D).*\.pth$|.*D\.pth$", path.name)
                ),
                None,
            )
            if pd is None:
                raise ModelAsssociatedEntityNotFoundError(
                    Entity.DISCRIMINATOR,
                    custom_pretrained,
                )

    if pg:
        _validate_pretrained_generator(pg, sample_rate, version, f0_guidance)
    if pd:
        _validate_pretrained_discriminator(pd, sample_rate, vocoder)
    return pg, pd


def run_training(
    model_name: str,
    version: RVCVersion = RVCVersion.V2,
    f0_guidance: bool = True,
    num_epochs: int = 300,
    batch_size: int = 16,
    detect_overtraining: bool = True,
    overtraining_threshold: int = 50,
    vocoder: Vocoder = Vocoder.HIFI_GAN,
    index_algorithm: IndexAlgorithm = IndexAlgorithm.FAISS,
    pretrained_type: PretrainedType = PretrainedType.DEFAULT,
    custom_pretrained: str | None = None,
    save_interval: int = 5,
    save_all_checkpoints: bool = False,
    save_all_weights: bool = False,
    clear_saved_data: bool = False,
    upload_model: bool = False,
    upload_name: str | None = None,
    hardware_acceleration: DeviceType = DeviceType.AUTOMATIC,
    gpu_ids: set[int] | None = None,
    precision: PrecisionType = PrecisionType.FP32,
    preload_dataset: bool = False,
    reduce_memory_usage: bool = False,
    started_at: float | None = None,
) -> list[str] | None:
    """

    Train a voice model using its associated preprocessed dataset and
    extracted features.

    Parameters
    ----------
    model_name : str
        The name of the voice model to train.
    num_epochs : int, default=500
        The number of epochs to train the voice model. A higher number
        can improve voice model performance but may lead to
        overtraining.
    batch_size : int, default=8
        The number of samples to include in each training batch. It is
        advisable to align this value with the available VRAM of your
        GPU. A setting of 4 offers improved accuracy but slower
        processing, while 8 provides faster and standard results.
    detect_overtraining : bool, default=False
        Whether to detect overtraining to prevent the voice model from
        learning the training data too well and losing the ability to
        generalize to new data.
    overtraining_threshold : int, default=50
        The maximum number of epochs to continue training without any
        observed improvement in voice model performance.
    vocoder : Vocoder, default=Vocoder.HIFI_GAN
        The vocoder to use for audio synthesis during training. HiFi-GAN
        provides basic audio fidelity, while RefineGAN provides the
        highest audio fidelity.
    index_algorithm : IndexAlgorithm, default=IndexAlgorithm.AUTO
        The method to use for generating an index file for the trained
        voice model. KMeans is particularly useful for large datasets.
    pretrained_type : PretrainedType, default=PretrainedType.DEFAULT
        The type of pretrained model to finetune the voice model on.
        "None" will train the voice model from scratch, while
        "Default" will use a pretrained model tailored to the specific
        voice model architecture. "Custom" will use a custom pretrained
        model that you provide.
    custom_pretrained: str, optional
        The name of a custom pretrained model to finetune the voice
        model on.
    save_interval : int, default=10
        The epoch interval at which to to save voice model weights and
        checkpoints. The best model weights are always saved regardless
        of this setting.
    save_all_checkpoints : bool, default=False
        Whether to save a unique checkpoint at each save interval. If
        not enabled, only the latest checkpoint will be saved at each
        interval.
    save_all_weights : bool, default=False
        Whether to save unique voice model weights at each save
        interval. If not enabled, only the best voice model weights will
        be saved.
    clear_saved_data : bool, default=False
        Whether to delete any existing training data associated
        with the voice model before training commences. Enable this
        setting only if you are training a new voice model from scratch
        or restarting training.
    upload_model : bool, default=False
        Whether to automatically upload the trained voice model so that
        it can be used for audio generation tasks within the Ultimate
        RVC app.
    upload_name : str, optional
        The name to give the uploaded voice model.
    hardware_acceleration : DeviceType, default=DeviceType.AUTOMATIC
        The type of hardware acceleration to use when training the voice
        model. `AUTOMATIC` will select the first available GPU and fall
        back to CPU if no GPUs are available.
    gpu_ids : set[int], optional
        Set of ids of the GPUs to use for training the voice model when
        `GPU` is selected for hardware acceleration.
    precision : PrecisionType, default=PrecisionType.FP32
        The precision type to use when training the voice model. FP16
        and BF16 can reduce VRAM usage and speed up training on
        supported hardware.
    preload_dataset : bool, default=False
        Whether to preload all training data into GPU memory. This can
        improve training speed but requires a lot of VRAM.
    reduce_memory_usage : bool, default=False
        Whether to reduce VRAM usage at the cost of slower training
        speed by enabling activation checkpointing. This is useful for
        GPUs with limited memory (e.g., <6GB VRAM) or when training with
        a batch size larger than what your GPU can normally accommodate.

    Returns
    -------
    list[str] | None
        A list containing the paths to the best weights file and the
        index file for the trained voice model, if they exist.
        Otherwise, None.

    Raises
    ------
    ModelAsssociatedEntityNotFoundError
        If the voice model to be trained does not have an associated
        dataset file list.
    NotProvidedError
        If an upload name is not provided when the upload parameter is
        set
    ModelExistsError
        If a voice with the provided upload name already exists when the
        upload parameter is set


    """
    from ultimate_rvc.rvc.train.delivery import validate_model_name

    validate_model_name(model_name)
    model_path = validate_model(model_name, Entity.TRAINING_MODEL)
    filelist_path = model_path / "filelist.txt"
    if not filelist_path.is_file():
        raise ModelAsssociatedEntityNotFoundError(
            Entity.DATASET_FILE_LIST,
            model_name,
            Step.FEATURE_EXTRACTION,
        )
    upload_model_path = None
    if upload_model:
        if not upload_name:
            raise NotProvidedError(Entity.UPLOAD_NAME)
        upload_model_path = VOICE_MODELS_DIR / upload_name.strip()
        if upload_model_path.is_dir():
            raise ModelExistsError(Entity.VOICE_MODEL, upload_name)

    model_info_dict = json_load(model_path / "model_info.json")

    model_info = ModelInfo.model_validate(model_info_dict)
    sample_rate = model_info.sample_rate

    from ultimate_rvc.rvc.train.progress import (  # noqa: PLC0415
        initialize_progress,
        mark_failed,
        update_progress,
    )

    initialize_progress(
        model_path,
        num_epochs,
        started_at=started_at,
        stage_started_at=started_at,
        phase="training",
    )

    if version != RVCVersion.V2:
        error = ValueError("当前训练管线只支持 RVC v2，v1 会产生与特征和交付格式不匹配的模型")
        mark_failed(model_path, error)
        raise error

    resume_root = os.environ.get("RVC_RESUME_ROOT")
    if resume_root and not any(model_path.glob("G_*.pth")):
        from ultimate_rvc.rvc.train.resume import restore_resume_snapshot

        candidates = [
            path.parent
            for path in Path(resume_root).rglob("resume_manifest.json")
        ]
        for snapshot in candidates:
            try:
                restored_epoch = restore_resume_snapshot(snapshot, model_path)
                logger.info("Restored %s from epoch %d", model_name, restored_epoch)
                break
            except (OSError, ValueError, KeyError) as error:
                logger.warning("Skipped incompatible resume snapshot %s: %s", snapshot, error)

    try:
        resume_checkpoints = list(model_path.glob("G_*.pth"))
        if resume_checkpoints:
            resume_checkpoint = max(
                resume_checkpoints, key=lambda path: path.stat().st_mtime_ns
            )
            _validate_pretrained_generator(
                resume_checkpoint,
                sample_rate,
                version,
                f0_guidance,
            )
            pg, pd = "", ""
            logger.info("Resume checkpoint validated; pretrained base model is skipped")
        else:
            pg, pd = _get_pretrained_model(
                pretrained_type,
                vocoder,
                sample_rate,
                version,
                f0_guidance,
                custom_pretrained,
            )
        device_type, device_ids = validate_devices(hardware_acceleration, gpu_ids)
    except Exception as error:
        mark_failed(model_path, error)
        raise

    from ultimate_rvc.rvc.train.train import main as train_main  # noqa: PLC0415

    try:
        update_progress(
            model_path,
            phase="training",
            percent=5,
            stage_detail="训练配置和数据已准备完成",
            done=False,
        )
        train_main(
            model_name,
            sample_rate,
            vocoder,
            num_epochs,
            batch_size,
            save_interval,
            not save_all_checkpoints,
            save_all_weights,
            pg,
            pd,
            detect_overtraining,
            overtraining_threshold,
            clear_saved_data,
            preload_dataset,
            reduce_memory_usage,
            device_type,
            device_ids,
            precision,
            version,
            f0_guidance,
        )

        model_file = model_path / f"{model_name}_best.pth"

        if not model_file.is_file():
            raise RuntimeError("训练进程结束，但没有生成可推理模型")

        from ultimate_rvc.rvc.train.process.extract_index import (  # noqa: PLC0415
            main as extract_index_main,
        )

        update_progress(model_path, phase="indexing", done=False)
        extract_index_main(str(model_path), index_algorithm)

        index_file = model_path / f"{model_name}.index"

        if not index_file.is_file():
            raise RuntimeError(
                f"训练已完成，但索引生成失败：{index_file}。"
                "请确认特征提取文件存在后，在 Result 页面执行补全。"
            )
        from ultimate_rvc.rvc.train.delivery import (
            prepare_delivery_files,
            validate_delivery,
        )

        update_progress(model_path, phase="validating", done=False)
        prepare_delivery_files(model_path, model_name)
        validate_delivery(model_path, model_name)
        if upload_model_path:
            copy_files_to_new_dir([index_file, model_file], upload_model_path)
        update_progress(model_path, phase="completed", percent=100, done=True)
        return [str(model_file), str(index_file)]
    except Exception as error:
        mark_failed(model_path, error)
        raise


def stop_training(model_name: str) -> None:
    """
    Stop the training of a voice model.

    Parameters
    ----------
    model_name : str
        The name of the voice model to stop training for.

    """
    from ultimate_rvc.rvc.train.delivery import validate_model_name  # noqa: PLC0415

    model_name = validate_model_name(model_name)
    training_info_path = TRAINING_MODELS_DIR / model_name / "config.json"
    stop_path = TRAINING_MODELS_DIR / model_name / "stop_requested"
    from ultimate_rvc.rvc.train.progress import mark_stopped  # noqa: PLC0415

    mark_stopped(TRAINING_MODELS_DIR / model_name)
    try:
        stop_path.write_text("stop\n", encoding="utf-8")
        training_info_dict = json_load(training_info_path)
        training_info = TrainingInfo.model_validate(training_info_dict)
        process_ids = training_info.process_pids
        for pid in set(process_ids):
            try:
                os.kill(pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            except Exception:
                try:
                    os.kill(pid, signal.SIGKILL)
                except Exception:
                    pass
        training_info.process_pids = []
        updated_training_info_dict = training_info.model_dump()
        json_dump(updated_training_info_dict, training_info_path)
    except Exception as e:  # noqa: BLE001
        logger.error("Error stopping training: %s", e)  # noqa: TRY400
