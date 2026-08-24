import datetime
import glob
import json
import logging
import os
import sys
import warnings
import pathlib
import shutil
import signal
import traceback
from collections import deque
from random import randint, shuffle
from time import time as ttime

import numpy as np
from tqdm import tqdm

warnings.filterwarnings(
    "ignore",
    message=r"Grad strides do not match bucket view strides.*",
    category=UserWarning,
)

import torch
from ultimate_rvc.security import load_torch_checkpoint
import torch.distributed as dist
import torch.multiprocessing as mp
from torch.nn.parallel import DistributedDataParallel as DDP
from torch.utils.data import DataLoader
from torch.utils.tensorboard import SummaryWriter

now_dir = pathlib.Path.cwd()
sys.path.append(os.path.join(str(now_dir)))

# Zluda hijack
import ultimate_rvc.rvc.lib.zluda
from ultimate_rvc.common import TRAINING_MODELS_DIR
from ultimate_rvc.rvc.common import RVC_TRAINING_MODELS_DIR
from ultimate_rvc.rvc.lib.algorithm import commons
from ultimate_rvc.rvc.train.losses import (
    discriminator_loss,
    feature_loss,
    generator_loss,
    kl_loss,
)
from ultimate_rvc.rvc.train.mel_processing import (
    MultiScaleMelSpectrogramLoss,
    mel_spectrogram_torch,
    spec_to_mel_torch,
)
from ultimate_rvc.rvc.train.process.extract_model import extract_model
from ultimate_rvc.rvc.train.utils import (
    HParams,
    latest_checkpoint_path,
    load_checkpoint,
    load_wav_to_torch,
    plot_spectrogram_to_numpy,
    remove_sox_libmso6_from_ld_preload,
    save_checkpoint,
    summarize,
)

logging.getLogger("torch").setLevel(logging.ERROR)
logger = logging.getLogger(__name__)

torch.backends.cudnn.deterministic = False
torch.backends.cudnn.benchmark = True
torch.multiprocessing.set_start_method("spawn", force=True)
os.environ["USE_LIBUV"] = "0" if sys.platform == "win32" else "1"

randomized = True
d_lr_coeff = 1.0
g_lr_coeff = 1.0
d_step_per_g_step = 1
bf16_adamw = False
global_step = 0
lowest_g_value = {"value": float("inf"), "epoch": 0}
lowest_d_value = {"value": float("inf"), "epoch": 0}
consecutive_increases_gen = 0
consecutive_increases_disc = 0
_stop_requested = False
_last_progress_write = 0.0

avg_losses = {
    "grad_d_50": deque(maxlen=50),
    "grad_g_50": deque(maxlen=50),
    "disc_loss_50": deque(maxlen=50),
    "adv_loss_50": deque(maxlen=50),
    "fm_loss_50": deque(maxlen=50),
    "kl_loss_50": deque(maxlen=50),
    "mel_loss_50": deque(maxlen=50),
    "gen_loss_50": deque(maxlen=50),
}


class EpochRecorder:
    """
    Records the time elapsed per epoch.
    """

    def __init__(self):
        self.last_time = ttime()

    def record(self) -> tuple[str, float]:
        """
        Records the elapsed time and returns a formatted string and raw seconds.
        """
        now_time = ttime()
        elapsed_time = now_time - self.last_time
        self.last_time = now_time
        elapsed_time = round(elapsed_time, 1)
        elapsed_time_str = str(datetime.timedelta(seconds=int(elapsed_time)))
        current_time = datetime.datetime.now().strftime("%H:%M:%S")
        return f"time={current_time} | training_speed={elapsed_time_str}", elapsed_time


def main(
    model_name: str,
    sample_rate: int | None,
    vocoder: str,
    total_epoch: int,
    batch_size: int,
    save_every_epoch: int,
    save_only_latest: bool,
    save_every_weights: bool,
    pretrain_g: str,
    pretrain_d: str,
    overtraining_detector: bool,
    overtraining_threshold: int,
    cleanup: bool,
    cache_data_in_gpu: bool,
    checkpointing: bool,
    device_type: str,
    gpus: set[int] | None,
    precision: str = "fp32",
    version: str = "v2",
    f0_guidance: bool = True,
) -> None:
    """
    Start the training process.

    Raises:
        RuntimeError: If the sample rate of the pretrained model does not match the dataset audio sample rate.

    """
    vocoder = "HiFi-GAN"
    remove_sox_libmso6_from_ld_preload()
    import faulthandler

    faulthandler.enable(all_threads=True)
    experiment_dir = os.path.join(TRAINING_MODELS_DIR, model_name)
    config_save_path = os.path.join(experiment_dir, "config.json")
    stop_requested_path = os.path.join(experiment_dir, "stop_requested")
    try:
        os.unlink(stop_requested_path)
    except FileNotFoundError:
        pass

    try:
        with pathlib.Path(config_save_path).open() as f:
            config = json.load(f)
        config = HParams(**config)
    except FileNotFoundError:
        logger.error(
            "Config file not found at %s. Did you run preprocessing and feature"
            " extraction steps?",
            config_save_path,
        )
        raise FileNotFoundError(f"Config file not found at {config_save_path}. Did you run preprocessing and feature extraction steps?")
    sample_rate = config.data.sample_rate if sample_rate is None else sample_rate

    if (
        precision == "bf16"
        and torch.cuda.is_available()
        and torch.cuda.is_bf16_supported()
    ):
        train_dtype = torch.bfloat16
    elif precision == "fp16" and torch.cuda.is_available():
        train_dtype = torch.float16
    else:
        train_dtype = torch.float32

    config.data.training_files = os.path.join(experiment_dir, "filelist.txt")

    # Set up distributed training environment for master node.
    # master node is localhost because we are running on a single local
    # machine. master port is randomly selected
    os.environ["MASTER_ADDR"] = "localhost"
    os.environ["MASTER_PORT"] = str(randint(20000, 55555))
    logger.info("MASTER_PORT: %s", os.environ["MASTER_PORT"])
    # Check sample rate
    wavs = glob.glob(
        os.path.join(experiment_dir, "sliced_audios", "*.wav"),
    )
    if wavs:
        _, sr = load_wav_to_torch(wavs[0])
        if sr != sample_rate:
            error_message = (
                f"Error: Pretrained model sample rate ({sample_rate} Hz) does not match"
                f" dataset audio sample rate ({sr} Hz)."
            )
            raise RuntimeError(error_message)
    else:
        logger.warning("No wav file found.")

    device = torch.device(device_type)
    gpus = set(gpus or {0})
    if device.type == "cuda":
        # Diagnostics: log what this process can actually see. On shared
        # Kaggle boxes nvidia-smi may report cards that have no usable memory,
        # or CUDA_VISIBLE_DEVICES may hide devices entirely.
        try:
            visible = os.environ.get("CUDA_VISIBLE_DEVICES", "")
            logger.warning(
                "GPU self-check: CUDA_VISIBLE_DEVICES=%r device_count=%d",
                visible,
                torch.cuda.device_count(),
            )
            for gpu_idx in range(torch.cuda.device_count()):
                try:
                    free_mem, total_mem = torch.cuda.mem_get_info(gpu_idx)
                    logger.warning(
                        "  GPU %d: free=%d MiB total=%d MiB name=%s",
                        gpu_idx,
                        free_mem // (1024 * 1024),
                        total_mem // (1024 * 1024),
                        torch.cuda.get_device_name(gpu_idx),
                    )
                except Exception as gpu_error:  # noqa: BLE001
                    logger.warning("  GPU %d: not usable (%s)", gpu_idx, gpu_error)
        except Exception as check_error:  # noqa: BLE001
            logger.warning("GPU self-check failed: %s", check_error)
        available_devices = torch.cuda.device_count()
        if available_devices < 1:
            device = torch.device("cpu")
            gpus = set()
        else:
            usable = set()
            for gpu_idx in gpus:
                if gpu_idx >= available_devices:
                    logger.warning("Requested GPU %d is not visible to torch; skipping.", gpu_idx)
                    continue
                try:
                    free_mem, _ = torch.cuda.mem_get_info(gpu_idx)
                    if free_mem < 512 * 1024 * 1024:
                        logger.warning(
                            "Requested GPU %d has only %d MiB free; skipping it.",
                            gpu_idx,
                            free_mem // (1024 * 1024),
                        )
                        continue
                except Exception as gpu_error:  # noqa: BLE001
                    logger.warning("Requested GPU %d unusable (%s); skipping.", gpu_idx, gpu_error)
                    continue
                usable.add(gpu_idx)
            if not usable:
                usable = {0}
                logger.warning("No usable GPU found for the requested set %s; falling back to GPU 0.", sorted(gpus))
            if usable != gpus:
                logger.warning("Training GPUs filtered %s -> %s.", sorted(gpus), sorted(usable))
            gpus = usable
    n_gpus = max(1, len(gpus))

    if device.type == "cpu":
        logger.warning("Training with CPU, this will take a long time.")

    def start() -> None:
        """Start the training process with multi-GPU support or CPU.

        Mirrors the reference implementation: the requested GPU set is exposed
        to children via CUDA_VISIBLE_DEVICES so rank == device index in the
        remapped world, and a single GPU trains directly without DDP.
        """
        if device.type == "cuda":
            os.environ["CUDA_VISIBLE_DEVICES"] = ",".join(
                str(gpu_idx) for gpu_idx in sorted(gpus)
            )
            logger.warning(
                "Training GPUs %s -> CUDA_VISIBLE_DEVICES=%s",
                sorted(gpus),
                os.environ["CUDA_VISIBLE_DEVICES"],
            )
        single_gpu = device.type == "cuda" and len(gpus) == 1
        if single_gpu:
            run(
                0,
                1,
                experiment_dir,
                pretrain_g,
                pretrain_d,
                total_epoch,
                save_every_weights,
                config,
                device,
                0,
                model_name,
                sample_rate,
                vocoder,
                batch_size,
                save_every_epoch,
                save_only_latest,
                overtraining_detector,
                overtraining_threshold,
                checkpointing,
                cache_data_in_gpu,
                train_dtype,
                version,
                f0_guidance,
                use_ddp=False,
            )
            return
        # Multi-GPU DDP path: attempt DDP, fall back to single-GPU on failure.
        children = []
        pid_data = {"process_pids": []}
        try:
            with pathlib.Path(config_save_path).open("r") as pid_file:
                try:
                    existing_data = json.load(pid_file)
                    pid_data.update(existing_data)
                except json.JSONDecodeError:
                    pass
            with pathlib.Path(config_save_path).open("w") as pid_file:
                for rank in range(n_gpus):
                    subproc = mp.Process(
                        target=run,
                        args=(
                            rank,
                            n_gpus,
                            experiment_dir,
                            pretrain_g,
                            pretrain_d,
                            total_epoch,
                            save_every_weights,
                            config,
                            device,
                            rank,
                            model_name,
                            sample_rate,
                            vocoder,
                            batch_size,
                            save_every_epoch,
                            save_only_latest,
                            overtraining_detector,
                            overtraining_threshold,
                            checkpointing,
                            cache_data_in_gpu,
                            train_dtype,
                            version,
                            f0_guidance,
                            True,
                        ),
                    )
                    children.append(subproc)
                    subproc.start()
                    pid_data["process_pids"].append(subproc.pid)
                json.dump(pid_data, pid_file, indent=4)
            cancel_signal = signal.SIGTERM if os.name == "nt" else -signal.SIGTERM
            failed_child = None
            while any(child.is_alive() for child in children):
                for child in children:
                    child.join(timeout=0.5)
                    if child.exitcode not in {None, 0}:
                        failed_child = child
                        break
                if failed_child is not None:
                    for child in children:
                        if child.is_alive():
                            child.terminate()
                    break
            for child in children:
                child.join()

            error_codes = []
            for i, child in enumerate(children):
                exit_code = child.exitcode
                if exit_code != 0:
                    logger.warning(
                        "Process running on device %s exited with code %s.",
                        i,
                        exit_code,
                    )
                    if exit_code != cancel_signal:
                        error_codes.append(exit_code)
            try:
                torch.cuda.empty_cache()
            except Exception:
                pass
            try:
                dist.destroy_process_group()
            except Exception:
                pass
            print("[RVC] 所有训练进程已退出，GPU 资源已清理")
            if error_codes:
                # DDP failed - fall back to single GPU with first available
                logger.warning(
                    "Multi-GPU DDP failed (codes %s). Falling back to single GPU.",
                    error_codes,
                )
                if n_gpus > 0 and children:
                    # Kill any remaining children
                    for child in children:
                        if child.is_alive():
                            child.terminate()
                    # Fallback to single GPU on first available device
                    single_fallback_device = torch.device("cuda", 0)
                    run(
                        0,
                        1,
                        experiment_dir,
                        pretrain_g,
                        pretrain_d,
                        total_epoch,
                        save_every_weights,
                        config,
                        single_fallback_device,
                        0,
                        model_name,
                        sample_rate,
                        vocoder,
                        batch_size,
                        save_every_epoch,
                        save_only_latest,
                        overtraining_detector,
                        overtraining_threshold,
                        checkpointing,
                        cache_data_in_gpu,
                        train_dtype,
                        version,
                        f0_guidance,
                        use_ddp=False,
                    )
        except Exception as start_error:
            logger.warning("DDP startup failed: %s. Falling back to single GPU.", start_error)
            try:
                torch.cuda.empty_cache()
            except Exception:
                pass
            # Fallback to single GPU
            single_fallback_device = torch.device("cuda", 0)
            run(
                0,
                1,
                experiment_dir,
                pretrain_g,
                pretrain_d,
                total_epoch,
                save_every_weights,
                config,
                single_fallback_device,
                0,
                model_name,
                sample_rate,
                vocoder,
                batch_size,
                save_every_epoch,
                save_only_latest,
                overtraining_detector,
                overtraining_threshold,
                checkpointing,
                cache_data_in_gpu,
                train_dtype,
                version,
                f0_guidance,
                use_ddp=False,
            )

    if cleanup:
        logger.info("Removing files from the prior training attempt...")

        # Clean up unnecessary files
        for entry in os.scandir(os.path.join(TRAINING_MODELS_DIR, model_name)):
            if entry.is_file():
                _, file_extension = os.path.splitext(entry.name)
                if file_extension in {".0", ".pth", ".index"}:
                    pathlib.Path(entry.path).unlink()
            elif entry.is_dir() and entry.name == "eval":
                shutil.rmtree(entry.path)

        logger.info("Cleanup done!")
    start()


def run(*args: object, **kwargs: object) -> None:
    """Subprocess entry point that surfaces child-process failures in the log.

    Child processes crash with opaque exit codes (e.g. -11 SIGSEGV) that the
    parent only summarizes as "One or more training processes failed". This
    wrapper installs a faulthandler (so segfaults dump a Python stack trace)
    and prints full tracebacks for raised exceptions, landing in worker.log.
    """
    import faulthandler

    faulthandler.enable(all_threads=True)
    try:
        _run(*args, **kwargs)  # type: ignore[arg-type]
    except Exception:
        print("[RVC] 训练子进程异常（traceback 已写入日志）:")
        traceback.print_exc()
        raise


def _run(
    rank,
    n_gpus,
    experiment_dir,
    pretrain_g,
    pretrain_d,
    custom_total_epoch,
    custom_save_every_weights,
    config,
    device,
    device_id,
    model_name,
    sample_rate,
    vocoder,
    batch_size,
    save_every_epoch,
    save_only_latest,
    overtraining_detector,
    overtraining_threshold,
    checkpointing,
    cache_data_in_gpu,
    train_dtype,
    version="v2",
    f0_guidance=True,
    use_ddp=True,
    ):
    """
    Runs the training loop on a specific GPU or CPU.

    Args:
        rank (int): The rank of the current process within the distributed training setup.
        n_gpus (int): The total number of GPUs available for training.
        experiment_dir (str): The directory where experiment logs and checkpoints will be saved.
        pretrain_g (str): Path to the pre-trained generator model.
        pretrain_d (str): Path to the pre-trained discriminator of the model.
        custom_total_epoch (int): The total number of epochs for training.
        custom_save_every_weights (int): The interval (in epochs) at which to save model weights.
        config (object): Configuration object containing training parameters.
        device (torch.device): The device to use for training (CPU or GPU).

    """
    # Log conflicting modules that may interfere with CUDA — do NOT delete
    # loaded modules as that can corrupt an already-initialized CUDA context
    _CONFLICTING = frozenset({"jax", "jaxlib", "numba", "numba.core", "numba._dispatcher"})
    _found = [_m for _m in sys.modules if _m in _CONFLICTING or _m.startswith("numba.") or _m.startswith("jax")]
    if _found:
        logger.warning("Potentially conflicting modules detected (not removed): %s", _found)
    global global_step, optimizer, lowest_d_value, lowest_g_value, consecutive_increases_gen, consecutive_increases_disc, _stop_requested

    def _handle_stop(signum, frame):
        global _stop_requested
        _stop_requested = True
        print(f"[RVC] 收到停止信号，训练将在当前 epoch 结束后停止...")

    signal.signal(signal.SIGTERM, _handle_stop)
    signal.signal(signal.SIGINT, _handle_stop)

    if rank == 0:
        writer_eval = SummaryWriter(log_dir=os.path.join(experiment_dir, "eval"))
    else:
        writer_eval = None

    if device.type == "cuda":
        torch.cuda.set_device(device_id)

    # Initialize distributed training. NCCL is substantially faster for
    # CUDA on Linux; gloo remains the portable fallback for Windows/CPU.
    if use_ddp:
        requested_backend = os.environ.get("RVC_DDP_BACKEND", "").strip().lower()
        backend = requested_backend or (
            "nccl" if device.type == "cuda" and sys.platform != "win32" else "gloo"
        )
        if backend not in {"nccl", "gloo"}:
            raise ValueError(f"Unsupported RVC_DDP_BACKEND: {backend}")
        os.environ.setdefault("TORCH_DISTRIBUTED_USE_LIBUV", "0")
        if backend == "nccl":
            os.environ.setdefault("NCCL_ASYNC_ERROR_HANDLING", "1")
        try:
            dist.init_process_group(
                backend=backend,
                init_method="env://",
                world_size=n_gpus,
                rank=rank,
                timeout=datetime.timedelta(seconds=120),
            )
            logger.info("DDP initialized with %s (rank %d/%d)", backend, rank, n_gpus)
        except Exception as init_error:
            raise RuntimeError(
                f"DDP initialization failed on rank {rank} with {backend}"
            ) from init_error

    torch.manual_seed(config.train.seed)

    # Create datasets and dataloaders
    from ultimate_rvc.rvc.train.data_utils import (
        DistributedBucketSampler,
        TextAudioCollateMultiNSFsid,
        TextAudioLoaderMultiNSFsid,
    )

    train_dataset = TextAudioLoaderMultiNSFsid(config.data)
    collate_fn = TextAudioCollateMultiNSFsid()
    train_sampler = DistributedBucketSampler(
        train_dataset,
        batch_size,
        [50, 100, 200, 300, 400, 500, 600, 700, 800, 900],
        num_replicas=n_gpus,
        rank=rank,
        shuffle=True,
    )

    train_loader = DataLoader(
        train_dataset,
        num_workers=2,
        shuffle=False,
        pin_memory=True,
        collate_fn=collate_fn,
        batch_sampler=train_sampler,
        persistent_workers=True,
        prefetch_factor=8,
    )
    if len(train_loader) < 3:
        logger.error(
            "Not enough data in the training set. Perhaps you forgot to slice the"
            " audio files in preprocess?",
        )
        raise RuntimeError("Not enough data in the training set. Perhaps you forgot to slice the audio files in preprocess?")

    # defaults
    embedder_name = "contentvec"
    spk_dim = config.model.spk_embed_dim  # 109 default speakers

    model_info_path = os.path.join(experiment_dir, "model_info.json")
    try:
        with pathlib.Path(model_info_path).open("r") as f:
            model_info = json.load(f)
            embedder_name = model_info["embedder_model"]
            spk_dim = model_info["speakers_id"]
    except Exception as e:
        logger.error("Could not load model info file: %s. Using defaults.", e)

    # Try to load speaker dim from latest checkpoint or pretrain_g
    try:
        last_g = latest_checkpoint_path(experiment_dir, "G_*.pth")
        chk_path = last_g or (pretrain_g if pretrain_g not in {"", "None"} else None)

        if chk_path:
            ckpt = load_torch_checkpoint(chk_path)
            spk_dim = ckpt["model"]["emb_g.weight"].shape[0]
            del ckpt
    except Exception as e:
        logger.error(
            "Failed to load checkpoint: %s. Using default number of speakers.", e
        )

    # update config before the model init
    logger.info("Initializing the generator with %s speakers.", spk_dim)
    config.model.spk_embed_dim = spk_dim

    # Initialize models and optimizers
    from ultimate_rvc.rvc.lib.algorithm.discriminators import MultiPeriodDiscriminator
    from ultimate_rvc.rvc.lib.algorithm.synthesizers import Synthesizer

    # NOTE checkingpointing here means whether or not activations are
    # saved during forward pass for backpropagation during backward pass

    net_g = Synthesizer(
        config.data.filter_length // 2 + 1,
        config.train.segment_size // config.data.hop_length,
        **config.model,
        use_f0=f0_guidance,
        sr=sample_rate,
        vocoder=vocoder,
        checkpointing=checkpointing,
        randomized=randomized,
    )
    if vocoder == "RefineGAN":
        disc_version = "v3"
        fn_mel_loss = MultiScaleMelSpectrogramLoss(sample_rate=sample_rate)
        logger.info("Using Multi-Scale Mel loss function")
    else:
        disc_version = "v2"
        fn_mel_loss = torch.nn.L1Loss()
        logger.info("Using Single-Scale Mel loss function")
    net_d = MultiPeriodDiscriminator(
        config.model.use_spectral_norm,
        checkpointing=checkpointing,
        version=disc_version,
    )

    if device.type == "cuda":
        net_g = net_g.cuda(device_id)
        net_d = net_d.cuda(device_id)
    else:
        net_g = net_g.to(device)
        net_d = net_d.to(device)

    if bf16_adamw and train_dtype == torch.bfloat16:
        logger.info("Using BFloat16 AdamW optimizer")
        from ultimate_rvc.rvc.train.anyprecision_optimizer import AnyPrecisionAdamW

        optimizer = AnyPrecisionAdamW
    else:
        logger.info("Using AdamW optimizer")
        optimizer = torch.optim.AdamW

    if device.type == "cuda":
        try:
            free_mem, total_mem = torch.cuda.mem_get_info(device_id)
            logger.info(
                "GPU %d memory before optimizer: free=%d MiB total=%d MiB",
                device_id, free_mem // (1024 * 1024), total_mem // (1024 * 1024),
            )
        except Exception as mem_err:
            logger.warning("Could not query GPU memory: %s", mem_err)

    # Prevent triton segfault on Kaggle — its C extensions are incompatible.
    # Monkey-patch has_triton_package before torch.optim triggers _dynamo import.
    try:
        import torch.utils._triton as _triton_mod
        _triton_mod.has_triton_package = lambda: False  # type: ignore[attr-defined]
    except Exception:
        pass

    try:
        optim_g = optimizer(
            net_g.parameters(),
            config.train.learning_rate * g_lr_coeff,
            betas=config.train.betas,
            eps=config.train.eps,
        )
        optim_d = optimizer(
            net_d.parameters(),
            config.train.learning_rate * d_lr_coeff,
            betas=config.train.betas,
            eps=config.train.eps,
        )
    except Exception as optim_err:
        logger.error("Optimizer creation failed: %s", optim_err)
        if device.type == "cuda":
            try:
                free_mem, total_mem = torch.cuda.mem_get_info(device_id)
                logger.error("GPU %d: free=%d MiB total=%d MiB", device_id, free_mem // (1024 * 1024), total_mem // (1024 * 1024))
            except Exception:
                pass
        raise

    # Wrap models with DDP for multi-gpu processing
    if use_ddp and device.type == "cuda":
        logger.info("DDP: wrapping generator on device %s", device_id)
        net_g = DDP(net_g, device_ids=[device_id])
        logger.info("DDP: generator wrapped")
        logger.info("DDP: wrapping discriminator on device %s", device_id)
        net_d = DDP(net_d, device_ids=[device_id])
        logger.info("DDP: discriminator wrapped")

    if rank == 0 and device.type == "cuda" and train_dtype == torch.bfloat16:
        logger.info("Using BFloat16 for training.")
    elif rank == 0 and device.type == "cuda" and train_dtype == torch.float16:
        logger.info("Using Float16 for training.")

    # Load checkpoint if available
    scaler_dict = {}
    try:
        latest_g_checkpoint = latest_checkpoint_path(experiment_dir, "G_*.pth")
        checkpoint_metadata = load_torch_checkpoint(latest_g_checkpoint)
        _, _, _, epoch_str, lowest_d_value, consecutive_increases_disc, scaler_dict = (
            load_checkpoint(
                latest_checkpoint_path(experiment_dir, "D_*.pth"),
                net_d,
                optim_d,
            )
        )
        _, _, _, epoch_str, lowest_g_value, consecutive_increases_gen, _ = (
            load_checkpoint(
                latest_g_checkpoint,
                net_g,
                optim_g,
            )
        )
        if checkpoint_metadata.get("loss_metric") != "mean_per_optimizer_step_v1":
            logger.info("Legacy loss metric detected; resetting best-loss tracking")
            lowest_g_value = {"value": float("inf"), "epoch": 0}
            lowest_d_value = {"value": float("inf"), "epoch": 0}
            consecutive_increases_gen = 0
            consecutive_increases_disc = 0
        epoch_str += 1
        global_step = (epoch_str - 1) * len(train_loader)
        logger.info("Resumed from epoch %s", epoch_str)
        logger.info(
            "Loaded lowest generator loss %.3f at epoch %s, lowest discriminator loss"
            " %.3f at epoch %s",
            lowest_g_value["value"],
            lowest_g_value["epoch"],
            lowest_d_value["value"],
            lowest_d_value["epoch"],
        )
        logger.info(
            "Loaded consecutive increases gen %d, consecutive increases disc %d",
            consecutive_increases_gen,
            consecutive_increases_disc,
        )

    except Exception:
        logger.info("No checkpoint found, training from scratch")
        if (
            not pretrain_g
            or pretrain_g == "None"
            or not pretrain_d
            or pretrain_d == "None"
        ):
            raise RuntimeError(
                "未加载预训练底模（G=%r，D=%r）：将从随机权重开始训练，loss 会异常偏高且难以收敛。"
                "请将预训练模型设为 Default（底模位于 models/rvc/pretraineds/hifigan/）"
                "或提供匹配的自定义底模后重试。"
                % (pretrain_g, pretrain_d)
            )
        epoch_str = 1
        global_step = 0
        if pretrain_g not in {"", "None"}:
            if rank == 0:
                logger.info("Loaded pretrained (G) '%s'", pretrain_g)
            try:
                ckpt = load_torch_checkpoint(pretrain_g)[
                    "model"
                ]
                if hasattr(net_g, "module"):
                    net_g.module.load_state_dict(ckpt)
                else:
                    net_g.load_state_dict(ckpt)
                del ckpt
            except RuntimeError:
                logger.error(  # noqa: TRY400
                    "The parameters of the pretrain model such as the sample rate or"
                    " architecture do not match the selected model.",
                )
                raise RuntimeError("Pretrained generator model parameters (sample rate or architecture) do not match the selected model.")

        if pretrain_d not in {"", "None"}:
            if rank == 0:
                logger.info("Loaded pretrained (D) '%s'", pretrain_d)
            try:
                ckpt = load_torch_checkpoint(pretrain_d)[
                    "model"
                ]
                if hasattr(net_d, "module"):
                    net_d.module.load_state_dict(ckpt)
                else:
                    net_d.load_state_dict(ckpt)
                del ckpt
            except RuntimeError:
                logger.error(  # noqa: TRY400
                    "The parameters of the pretrain model such as the sample rate or"
                    " architecture do not match the selected model.",
                )
                raise RuntimeError("Pretrained discriminator model parameters (sample rate or architecture) do not match the selected model.")

    # Initialize schedulers
    scheduler_g = torch.optim.lr_scheduler.ExponentialLR(
        optim_g,
        gamma=config.train.lr_decay,
        last_epoch=epoch_str - 2,
    )
    scheduler_d = torch.optim.lr_scheduler.ExponentialLR(
        optim_d,
        gamma=config.train.lr_decay,
        last_epoch=epoch_str - 2,
    )

    use_scaler = device.type == "cuda" and train_dtype == torch.float16
    scaler = torch.amp.GradScaler(enabled=use_scaler)
    if len(scaler_dict) > 0:
        scaler.load_state_dict(scaler_dict)

    cache = []
    logger.info("Checkpoint/pretrain prepared, locating reference audio...")
    # collect the reference audio for tensorboard evaluation
    if pathlib.Path(
        os.path.join(RVC_TRAINING_MODELS_DIR, "reference", embedder_name, "feats.npy")
    ).is_file():
        logger.info("Using %s reference set for validation", embedder_name)
        phone = np.load(
            os.path.join(
                RVC_TRAINING_MODELS_DIR,
                "reference",
                embedder_name,
                "feats.npy",
            ),
        )
        # expanding x2 to match pitch size
        phone = np.repeat(phone, 2, axis=0)
        phone_lengths = torch.LongTensor([phone.shape[0]]).to(device)
        phone = torch.FloatTensor(phone).unsqueeze(0).to(device)
        pitch = np.load(
            os.path.join(
                RVC_TRAINING_MODELS_DIR,
                "reference",
                "pitch_coarse.npy",
            ),
        )
        # removed last frame to match features
        pitch = torch.LongTensor(pitch[:-1]).unsqueeze(0).to(device)
        pitchf = np.load(
            os.path.join(
                RVC_TRAINING_MODELS_DIR,
                "reference",
                "pitch_fine.npy",
            ),
        )
        # removed last frame to match features
        pitchf = torch.FloatTensor(pitchf[:-1]).unsqueeze(0).to(device)
        sid = torch.LongTensor([0]).to(device)
        reference = (
            phone,
            phone_lengths,
            pitch,
            pitchf,
            sid,
        )
    else:
        logger.info(
            "No custom reference found, using a default audio sample for validation"
        )
        logger.info("Highlight: first dataloader batch fetch begins (fork point)...")
        info = next(iter(train_loader))
        phone, phone_lengths, pitch, pitchf, _, _, _, _, sid = info
        reference = (
            phone.to(device),
            phone_lengths.to(device),
            pitch.to(device),
            pitchf.to(device),
            sid.to(device),
        )
    if epoch_str > custom_total_epoch:
        if rank == 0:
            cleanup_training_processes(experiment_dir)
        elif dist.is_initialized():
            dist.destroy_process_group()
        return
    logger.info("Starting training...")
    for epoch in range(epoch_str, custom_total_epoch + 1):
        stop_requested = _stop_requested
        if dist.is_initialized():
            stop_tensor = torch.tensor(
                [int(stop_requested)],
                device=device if dist.get_backend() == "nccl" else "cpu",
            )
            dist.all_reduce(stop_tensor, op=dist.ReduceOp.MAX)
            stop_requested = bool(stop_tensor.item())
        if stop_requested:
            print("[RVC] 训练已停止")
            if rank == 0:
                _safe_cleanup(experiment_dir)
            elif dist.is_initialized():
                dist.destroy_process_group()
            return
        done = train_and_evaluate(
            rank,
            epoch,
            config,
            [net_g, net_d],
            [optim_g, optim_d],
            [scheduler_g, scheduler_d],
            [train_loader, None],
            [writer_eval],
            cache,
            custom_save_every_weights,
            custom_total_epoch,
            device,
            device_id,
            reference,
            fn_mel_loss,
            model_name,
            experiment_dir,
            sample_rate,
            vocoder,
            save_every_epoch,
            save_only_latest,
            overtraining_detector,
            overtraining_threshold,
            cache_data_in_gpu,
            scaler,
            train_dtype,
            f0_guidance,
            version,
        )
        if done:
            if rank == 0:
                _safe_cleanup(experiment_dir)
            elif dist.is_initialized():
                dist.destroy_process_group()
            return


def train_and_evaluate(
    rank,
    epoch,
    config,
    nets,
    optims,
    schedulers,
    loaders,
    writers,
    cache,
    custom_save_every_weights,
    custom_total_epoch,
    device,
    device_id,
    reference,
    fn_mel_loss,
    model_name,
    experiment_dir,
    sample_rate,
    vocoder,
    save_every_epoch,
    save_only_latest,
    overtraining_detector,
    overtraining_threshold,
    cache_data_in_gpu,
    scaler,
    train_dtype,
    f0_guidance=True,
    version="v2",
) -> bool:
    """Train and evaluates the model for one epoch."""
    global global_step, lowest_g_value, lowest_d_value, consecutive_increases_gen, consecutive_increases_disc, _last_progress_write

    model_add = []
    checkpoint_idxs = []
    done = False
    epoch_gen_loss = 0.0
    epoch_disc_loss = 0.0
    epoch_gen_steps = 0
    epoch_disc_steps = 0

    net_g, net_d = nets
    optim_g, optim_d = optims
    scheduler_g, scheduler_d = schedulers
    train_loader = loaders[0] if loaders is not None else None
    if writers is not None:
        writer = writers[0]

    train_loader.batch_sampler.set_epoch(epoch)

    net_g.train()
    net_d.train()

    use_amp = device.type == "cuda" and (train_dtype in {torch.bfloat16, torch.float16})

    # Data caching
    if device.type == "cuda" and cache_data_in_gpu:
        if cache == []:
            for batch_idx, info in enumerate(train_loader):
                # phone, phone_lengths, pitch, pitchf, spec, spec_lengths, wave, wave_lengths, sid
                info = [tensor.cuda(device_id, non_blocking=True) for tensor in info]
                cache.append((batch_idx, info))
        shuffle(cache)
        data_iterator = cache
    else:
        data_iterator = enumerate(train_loader)

    epoch_recorder = EpochRecorder()
    with tqdm(total=len(train_loader), leave=False,
              disable=True,
              desc=f"Epoch {epoch+1}") as pbar:
        for batch_idx, info in data_iterator:
            if rank == 0 and batch_idx == 0:
                logger.info("Training loop started, first batch in-flight")
            if device.type == "cuda" and not cache_data_in_gpu:
                info = [tensor.cuda(device_id, non_blocking=True) for tensor in info]
            elif device.type != "cuda":
                info = [tensor.to(device) for tensor in info]
            # else iterator is going thru a cached list with a device already assigned

            (
                phone,
                phone_lengths,
                pitch,
                pitchf,
                spec,
                spec_lengths,
                wave,
                wave_lengths,
                sid,
            ) = info

            with torch.amp.autocast(
                device_type="cuda", enabled=use_amp, dtype=train_dtype
            ):
                # Forward pass
                model_output = net_g(
                    phone,
                    phone_lengths,
                    pitch,
                    pitchf,
                    spec,
                    spec_lengths,
                    sid,
                )
                y_hat, ids_slice, x_mask, z_mask, (z, z_p, m_p, logs_p, m_q, logs_q) = (
                    model_output
                )
                # slice of the original waveform to match a generate slice
                if randomized:
                    wave = commons.slice_segments(
                        wave,
                        ids_slice * config.data.hop_length,
                        config.train.segment_size,
                        dim=3,
                    )
            for _ in range(d_step_per_g_step):  # default x1
                with torch.amp.autocast(
                    device_type="cuda", enabled=use_amp, dtype=train_dtype
                ):
                    y_d_hat_r, y_d_hat_g, _, _ = net_d(wave, y_hat.detach())
                loss_disc, _, _ = discriminator_loss(y_d_hat_r, y_d_hat_g)
                # Discriminator backward and update
                epoch_disc_loss += loss_disc.item()
                epoch_disc_steps += 1
                optim_d.zero_grad()
                if device.type == "cuda" and train_dtype == torch.float16:
                    scaler.scale(loss_disc).backward()
                    scaler.unscale_(optim_d)
                    grad_norm_d = commons.grad_norm(net_d.parameters())
                    scaler.step(optim_d)
                else:
                    loss_disc.backward()
                    grad_norm_d = commons.grad_norm(net_d.parameters())
                    optim_d.step()

            with torch.amp.autocast(
                device_type="cuda", enabled=use_amp, dtype=train_dtype
            ):
                # Generator backward and update
                _, y_d_hat_g, fmap_r, fmap_g = net_d(wave, y_hat)

            if vocoder == "RefineGAN":
                loss_mel = fn_mel_loss(wave, y_hat) * config.train.c_mel / 3.0
            else:
                wave_mel = mel_spectrogram_torch(
                    wave.float().squeeze(1),
                    config.data.filter_length,
                    config.data.n_mel_channels,
                    config.data.sample_rate,
                    config.data.hop_length,
                    config.data.win_length,
                    config.data.mel_fmin,
                    config.data.mel_fmax,
                )
                y_hat_mel = mel_spectrogram_torch(
                    y_hat.float().squeeze(1),
                    config.data.filter_length,
                    config.data.n_mel_channels,
                    config.data.sample_rate,
                    config.data.hop_length,
                    config.data.win_length,
                    config.data.mel_fmin,
                    config.data.mel_fmax,
                )
                loss_mel = fn_mel_loss(wave_mel, y_hat_mel) * config.train.c_mel
            loss_kl = kl_loss(z_p, logs_q, m_p, logs_p, z_mask) * config.train.c_kl
            loss_fm = feature_loss(fmap_r, fmap_g)
            loss_gen, _ = generator_loss(y_d_hat_g)
            loss_gen_all = loss_gen + loss_fm + loss_mel + loss_kl
            epoch_gen_loss += loss_gen_all.item()
            epoch_gen_steps += 1
            optim_g.zero_grad()
            if device.type == "cuda" and train_dtype == torch.float16:
                scaler.scale(loss_gen_all).backward()
                scaler.unscale_(optim_g)
                grad_norm_g = commons.grad_norm(net_g.parameters())
                scaler.step(optim_g)
                scaler.update()
            else:
                loss_gen_all.backward()
                grad_norm_g = commons.grad_norm(net_g.parameters())
                optim_g.step()

            global_step += 1

            if rank == 0 and ttime() - _last_progress_write >= 2:
                try:
                    from ultimate_rvc.rvc.train.progress import update_progress

                    update_progress(
                        pathlib.Path(experiment_dir),
                        phase="training",
                        epoch=int(epoch),
                        batch=int(batch_idx) + 1,
                        total_batches=len(train_loader),
                        done=False,
                    )
                    _last_progress_write = ttime()
                except Exception as error:
                    print(f"[WARN] Failed to write batch progress: {error}")

            # queue for rolling losses over 50 steps
            avg_losses["grad_d_50"].append(grad_norm_d)
            avg_losses["grad_g_50"].append(grad_norm_g)
            avg_losses["disc_loss_50"].append(loss_disc.detach())
            avg_losses["adv_loss_50"].append(loss_gen.detach())
            avg_losses["fm_loss_50"].append(loss_fm.detach())
            avg_losses["kl_loss_50"].append(loss_kl.detach())
            avg_losses["mel_loss_50"].append(loss_mel.detach())
            avg_losses["gen_loss_50"].append(loss_gen_all.detach())

            if rank == 0 and global_step % 50 == 0:
                # logging rolling averages
                scalar_dict = {
                    "grad_avg_50/norm_d": (
                        sum(avg_losses["grad_d_50"]) / len(avg_losses["grad_d_50"])
                    ),
                    "grad_avg_50/norm_g": (
                        sum(avg_losses["grad_g_50"]) / len(avg_losses["grad_g_50"])
                    ),
                    "loss_avg_50/d/adv": torch.mean(
                        torch.stack(list(avg_losses["disc_loss_50"])),
                    ),
                    "loss_avg_50/g/adv": torch.mean(
                        torch.stack(list(avg_losses["adv_loss_50"])),
                    ),
                    "loss_avg_50/g/fm": torch.mean(
                        torch.stack(list(avg_losses["fm_loss_50"])),
                    ),
                    "loss_avg_50/g/kl": torch.mean(
                        torch.stack(list(avg_losses["kl_loss_50"])),
                    ),
                    "loss_avg_50/g/mel": torch.mean(
                        torch.stack(list(avg_losses["mel_loss_50"])),
                    ),
                    "loss_avg_50/g/total": torch.mean(
                        torch.stack(list(avg_losses["gen_loss_50"])),
                    ),
                }
                summarize(
                    writer=writer,
                    global_step=global_step,
                    scalars=scalar_dict,
                )

            pbar.update(1)
        # end of batch train
    # end of tqdm
    scheduler_d.step()
    scheduler_g.step()

    with torch.no_grad():
        torch.cuda.empty_cache()
    loss_totals = torch.tensor(
        [epoch_gen_loss, epoch_disc_loss, epoch_gen_steps, epoch_disc_steps],
        dtype=torch.float64,
        device=device if dist.is_initialized() and dist.get_backend() == "nccl" else "cpu",
    )
    if dist.is_initialized():
        dist.all_reduce(loss_totals, op=dist.ReduceOp.SUM)
    total_gen_loss, total_disc_loss, total_gen_steps, total_disc_steps = (
        loss_totals.tolist()
    )
    if total_gen_steps <= 0 or total_disc_steps <= 0:
        raise RuntimeError("Training epoch completed without optimizer steps")
    avg_global_gen_loss = total_gen_loss / total_gen_steps
    avg_global_disc_loss = total_disc_loss / total_disc_steps
    # Logging and checkpointing
    if rank == 0:
        min_delta = 0.001

        if avg_global_disc_loss < lowest_d_value["value"] - min_delta:
            lowest_d_value = {"value": avg_global_disc_loss, "epoch": epoch}
            consecutive_increases_disc = 0
        else:
            consecutive_increases_disc += 1

        if avg_global_gen_loss < lowest_g_value["value"] - min_delta:
            logger.info(
                "New best epoch %d with average generator loss %.3f and discriminator"
                " loss %.3f",
                epoch,
                avg_global_gen_loss,
                avg_global_disc_loss,
            )
            lowest_g_value = {"value": avg_global_gen_loss, "epoch": epoch}
            consecutive_increases_gen = 0
            model_add.append(
                os.path.join(experiment_dir, f"{model_name}_best.pth"),
            )
        else:
            consecutive_increases_gen += 1

        # used for tensorboard chart - all/mel
        mel = spec_to_mel_torch(
            spec,
            config.data.filter_length,
            config.data.n_mel_channels,
            config.data.sample_rate,
            config.data.mel_fmin,
            config.data.mel_fmax,
        )
        # used for tensorboard chart - slice/mel_org
        if randomized:
            y_mel = commons.slice_segments(
                mel,
                ids_slice,
                config.train.segment_size // config.data.hop_length,
                dim=3,
            )
        else:
            y_mel = mel
        # used for tensorboard chart - slice/mel_gen
        y_hat_mel = mel_spectrogram_torch(
            y_hat.float().squeeze(1),
            config.data.filter_length,
            config.data.n_mel_channels,
            config.data.sample_rate,
            config.data.hop_length,
            config.data.win_length,
            config.data.mel_fmin,
            config.data.mel_fmax,
        )

        lr = optim_g.param_groups[0]["lr"]

        scalar_dict = {
            "loss/g/total": loss_gen_all,
            "loss/d/adv": loss_disc,
            "learning_rate": lr,
            "grad/norm_d": grad_norm_d,
            "grad/norm_g": grad_norm_g,
            "loss/g/adv": loss_gen,
            "loss/g/fm": loss_fm,
            "loss/g/mel": loss_mel,
            "loss/g/kl": loss_kl,
        }

        image_dict = {
            "slice/mel_org": plot_spectrogram_to_numpy(y_mel[0].data.cpu().numpy()),
            "slice/mel_gen": plot_spectrogram_to_numpy(y_hat_mel[0].data.cpu().numpy()),
            "all/mel": plot_spectrogram_to_numpy(mel[0].data.cpu().numpy()),
        }
        overtrain_info = ""
        # Print training progress
        lowest_g_value_rounded = float(lowest_g_value["value"])
        lowest_g_value_rounded = round(lowest_g_value_rounded, 3)

        _rec_str, _epoch_secs = epoch_recorder.record()
        record = f"{model_name} | epoch={epoch} | {_rec_str}"
        record += (
            f" | best avg-gen-loss={lowest_g_value_rounded:.3f} (epoch"
            f" {lowest_g_value['epoch']})"
        )
        # Check overtraining
        if overtraining_detector:
            overtrain_info = (
                f"Average epoch generator loss {avg_global_gen_loss:.3f} and"
                f" discriminator loss {avg_global_disc_loss:.3f}"
            )

            remaining_epochs_gen = max(
                overtraining_threshold - consecutive_increases_gen,
                0,
            )
            remaining_epochs_disc = max(
                overtraining_threshold * 2 - consecutive_increases_disc,
                0,
            )
            record += (
                " | overtrain countdown: g="
                f"{remaining_epochs_gen},d={remaining_epochs_disc} |"
                f" avg-gen-loss={avg_global_gen_loss:.3f} | avg-"
                f"disc-loss={avg_global_disc_loss:.3f}"
            )

            if remaining_epochs_disc == 0 or remaining_epochs_gen == 0:
                record += (
                    f"\nOvertraining detected at epoch {epoch} with average"
                    f" generator loss {avg_global_gen_loss:.3f} and discriminator loss"
                    f" {avg_global_disc_loss:.3f}"
                )
                done = True
        if epoch >= custom_total_epoch:
            done = True
        print(record)

        # Write progress file for web UI polling
        try:
            from ultimate_rvc.rvc.train.progress import tail_log, update_progress
            _progress = {
                "phase": "training",
                "epoch": int(epoch),
                "total_epochs": int(custom_total_epoch),
                "batch": 0,
                "total_batches": len(train_loader),
                "stage_detail": f"第 {int(epoch)}/{int(custom_total_epoch)} 轮 · G {round(float(avg_global_gen_loss), 4)} / D {round(float(avg_global_disc_loss), 4)}",
                "loss_g": round(float(avg_global_gen_loss), 4),
                "loss_d": round(float(avg_global_disc_loss), 4),
                "best_loss": round(float(lowest_g_value_rounded), 4),
                "best_epoch": int(lowest_g_value["epoch"]),
                "done": False,
                "epoch_secs": round(float(_epoch_secs), 1),
                "overtraining": bool(overtraining_detector),
                "overtraining_threshold": int(overtraining_threshold),
                "consecutive_increases_gen": int(consecutive_increases_gen),
                "consecutive_increases_disc": int(consecutive_increases_disc),
            }
            _progress_path = pathlib.Path(experiment_dir) / "progress.json"
            from ultimate_rvc.rvc.train.progress import read_progress
            _previous = read_progress(_progress_path)
            _prev_times = list(_previous.get("recent_epoch_times", []))
            _prev_times.append(round(float(_epoch_secs), 1))
            _progress["recent_epoch_times"] = _prev_times[-3:]
            _log_path = os.path.join(experiment_dir, "train.log")
            with open(_log_path, "a", encoding="utf-8") as _lf:
                _lf.write(record + "\n")
            _elapsed = max(0, ttime() - float(_previous.get("started_at", ttime())))
            _avg_secs = sum(_progress["recent_epoch_times"]) / len(_progress["recent_epoch_times"])
            _progress["elapsed_seconds"] = round(_elapsed, 1)
            _progress["eta_seconds"] = round(max(0, custom_total_epoch - epoch) * _avg_secs, 1)
            _progress["recent_log"] = tail_log(pathlib.Path(_log_path))
            update_progress(pathlib.Path(experiment_dir), **_progress)
            _last_progress_write = ttime()
        except Exception as e:
            print(f"[WARN] Failed to write progress: {e}")

        # Save weights, checkpoints and reference inference results
        # every N epochs
        if epoch % save_every_epoch == 0:
            with (
                torch.amp.autocast(
                    device_type="cuda", enabled=use_amp, dtype=train_dtype
                ),
                torch.no_grad(),
            ):
                if hasattr(net_g, "module"):
                    o, *_ = net_g.module.infer(*reference)
                else:
                    o, *_ = net_g.infer(*reference)
            audio_dict = {f"gen/audio_{global_step:07d}": o[0, :, :]}
            summarize(
                writer=writer,
                global_step=global_step,
                images=image_dict,
                scalars=scalar_dict,
                audios=audio_dict,
                audio_sample_rate=config.data.sample_rate,
            )
            checkpoint_idxs.append(2333333)
            if not save_only_latest:
                checkpoint_idxs.append(epoch)

            if custom_save_every_weights:
                model_add.append(
                    os.path.join(experiment_dir, f"{model_name}_{epoch}.pth"),
                )
        else:
            summarize(
                writer=writer,
                global_step=global_step,
                images=image_dict,
                scalars=scalar_dict,
            )
        checkpoint_version = str(getattr(version, "value", version))
        checkpoint_vocoder = str(getattr(vocoder, "value", vocoder))
        for idx in checkpoint_idxs:
            save_checkpoint(
                net_g,
                optim_g,
                config.train.learning_rate,
                epoch,
                lowest_g_value,
                consecutive_increases_gen,
                os.path.join(experiment_dir, f"G_{idx}.pth"),
                scaler,
                {
                    "model_kind": "generator",
                    "version": checkpoint_version,
                    "f0": int(f0_guidance),
                    "sample_rate": int(sample_rate),
                    "vocoder": checkpoint_vocoder,
                    "loss_metric": "mean_per_optimizer_step_v1",
                },
            )
            save_checkpoint(
                net_d,
                optim_d,
                config.train.learning_rate,
                epoch,
                lowest_d_value,
                consecutive_increases_disc,
                os.path.join(experiment_dir, f"D_{idx}.pth"),
                scaler,
                {
                    "model_kind": "discriminator",
                    "version": checkpoint_version,
                    "f0": int(f0_guidance),
                    "sample_rate": int(sample_rate),
                    "vocoder": checkpoint_vocoder,
                    "loss_metric": "mean_per_optimizer_step_v1",
                },
            )
        if checkpoint_idxs:
            try:
                from ultimate_rvc.rvc.train.resume import (
                    create_resume_snapshot,
                    sync_resume_snapshot,
                )

                create_resume_snapshot(pathlib.Path(experiment_dir))
                resume_slug = sync_resume_snapshot(pathlib.Path(experiment_dir))
                if resume_slug:
                    logger.info("Resume state synced to private dataset %s", resume_slug)
            except Exception as error:
                logger.warning("Could not refresh resume snapshot: %s", error)
        if model_add:
            ckpt = (
                net_g.module.state_dict()
                if hasattr(net_g, "module")
                else net_g.state_dict()
            )
            for m in model_add:
                extract_model(
                    ckpt=ckpt,
                    sr=sample_rate,
                    name=model_name,
                    model_path=m,
                    epoch=epoch,
                    step=global_step,
                    hps=config,
                    overtrain_info=overtrain_info,
                    vocoder=vocoder,
                    pitch_guidance=f0_guidance,
                    version=version,
                )
        # Check completion
        if epoch >= custom_total_epoch:
            lowest_g_value_rounded = float(lowest_g_value["value"])
            lowest_g_value_rounded = round(lowest_g_value_rounded, 3)
            print(
                f"Training has been successfully completed with {epoch} epoch(s),"
                f" {global_step} step(s) and {round(avg_global_gen_loss, 3)} average"
                " generator loss.",
            )
            print(
                f"Lowest average generator loss: {lowest_g_value_rounded} at epoch"
                f" {lowest_g_value['epoch']}",
            )
        with torch.no_grad():
            torch.cuda.empty_cache()
    if dist.is_initialized():
        done_tensor = torch.tensor(
            [int(done)],
            device=device if dist.get_backend() == "nccl" else "cpu",
        )
        dist.broadcast(done_tensor, src=0)
        done = bool(done_tensor.item())
    return done


def _safe_cleanup(experiment_dir) -> None:
    """Safe cleanup that ensures process exit even if cleanup fails."""
    try:
        cleanup_training_processes(experiment_dir)
    except Exception as e:
        print(f"[RVC] 清理时出错: {e}")
    return


def cleanup_training_processes(experiment_dir) -> None:
    try:
        dist.destroy_process_group()
    except Exception:
        pass
    pid_file_path = os.path.join(experiment_dir, "config.json")
    with pathlib.Path(pid_file_path).open() as pid_file:
        pid_data = json.load(pid_file)
    with pathlib.Path(pid_file_path).open("w") as pid_file:
        pid_data.pop("process_pids", None)
        json.dump(pid_data, pid_file, indent=4)
