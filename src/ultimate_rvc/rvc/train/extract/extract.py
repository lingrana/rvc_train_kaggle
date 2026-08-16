import concurrent.futures
import glob
import json
import logging
import multiprocessing as mp
import os
import pathlib
from pathlib import Path
import sys
import threading
import time

import numpy as np
import tqdm

import torch

now_dir = pathlib.Path.cwd()
sys.path.append(os.path.join(now_dir))

# Zluda hijack
import ultimate_rvc.rvc.lib.zluda
from ultimate_rvc.common import RVC_MODELS_DIR
from ultimate_rvc.rvc.configs.config import Config
from ultimate_rvc.rvc.lib.predictors.f0 import CREPE, FCPE, RMVPE
from ultimate_rvc.rvc.lib.utils import load_audio_16k, load_embedding
from ultimate_rvc.rvc.train.progress import update_progress
from ultimate_rvc.rvc.train.utils import remove_sox_libmso6_from_ld_preload

logger = logging.getLogger(__name__)

# Load config
config = Config()
mp.set_start_method("spawn", force=True)


class FeatureInput:
    def __init__(self, f0_method="rmvpe", device="cpu"):
        self.hop_size = 160  # default
        self.sample_rate = 16000  # default
        self.f0_bin = 256
        self.f0_max = 1100.0
        self.f0_min = 50.0
        self.f0_mel_min = 1127 * np.log(1 + self.f0_min / 700)
        self.f0_mel_max = 1127 * np.log(1 + self.f0_max / 700)
        self.device = device
        if f0_method in {"crepe", "crepe-tiny"}:
            self.model = CREPE(
                device=self.device, sample_rate=self.sample_rate, hop_size=self.hop_size
            )
        elif f0_method == "rmvpe":
            self.model = RMVPE(
                device=self.device, sample_rate=self.sample_rate, hop_size=self.hop_size
            )
        elif f0_method == "fcpe":
            self.model = FCPE(
                device=self.device, sample_rate=self.sample_rate, hop_size=self.hop_size
            )
        self.f0_method = f0_method

    def compute_f0(self, x, p_len=None):
        if self.f0_method == "crepe":
            f0 = self.model.get_f0(x, self.f0_min, self.f0_max, p_len, "full")
        elif self.f0_method == "crepe-tiny":
            f0 = self.model.get_f0(x, self.f0_min, self.f0_max, p_len, "tiny")
        elif self.f0_method == "rmvpe":
            f0 = self.model.get_f0(x, filter_radius=0.03)
        elif self.f0_method == "fcpe":
            f0 = self.model.get_f0(x, p_len, filter_radius=0.006)
        return f0

    def coarse_f0(self, f0):
        f0_mel = 1127.0 * np.log(1.0 + f0 / 700.0)
        f0_mel = np.clip(
            (f0_mel - self.f0_mel_min)
            * (self.f0_bin - 2)
            / (self.f0_mel_max - self.f0_mel_min)
            + 1,
            1,
            self.f0_bin - 1,
        )
        return np.rint(f0_mel).astype(int)

    def process_file(self, file_info):
        inp_path, opt_path_coarse, opt_path_full, _ = file_info
        if (
            pathlib.Path(opt_path_coarse).exists()
            and pathlib.Path(opt_path_full).exists()
        ):
            return

        try:
            np_arr = load_audio_16k(inp_path)
            feature_pit = self.compute_f0(np_arr)
            np.save(opt_path_full, feature_pit, allow_pickle=False)
            coarse_pit = self.coarse_f0(feature_pit)
            np.save(opt_path_coarse, coarse_pit, allow_pickle=False)
        except Exception as error:
            logger.error(  # noqa: TRY400
                "An error occurred extracting file %s on %s: %s",
                inp_path,
                self.device,
                error,
            )


def _count_done(done_path: str) -> int:
    try:
        with open(done_path, "r", encoding="utf-8") as done_file:
            return sum(1 for _ in done_file)
    except OSError:
        return 0


def _watch_done(done_path: str, model_dir: str, total: int, base_pct: int, label: str, phase: str, stop: threading.Event) -> None:
    while True:
        n = _count_done(done_path)
        if total:
            update_progress(
                Path(model_dir),
                phase=phase,
                percent=min(99.9, base_pct + n * 50 / total),
                stage_detail=f"{label} {n}/{total}",
                done=False,
            )
        if stop.wait(0.5):
            return


def process_files(files, f0_method, device, done_path=None):
    fe = FeatureInput(f0_method=f0_method, device=device)
    processed = 0
    with tqdm.tqdm(total=len(files), leave=True) as pbar:
        for file_info in files:
            fe.process_file(file_info)
            pbar.update(1)
            processed += 1
            if done_path:
                with open(done_path, "a", encoding="utf-8") as done_file:
                    done_file.write("1\n")
    return processed


def run_pitch_extraction(
    files: list[list[str]],
    devices: list[str],
    f0_method: str,
    threads: int,
    model_dir: str,
) -> None:
    devices_str = ", ".join(devices)
    logger.info(
        "Starting pitch extraction with %d cores on %s using %s...",
        threads,
        devices_str,
        f0_method,
    )
    start_time = time.time()
    total_files = len(files)
    done_files = 0
    last_report = 0.0
    done_path = os.path.join(model_dir, ".extract_done_pitch")
    try:
        os.unlink(done_path)
    except FileNotFoundError:
        pass
    _stop_watcher = threading.Event()
    watcher = threading.Thread(
        target=_watch_done,
        args=(done_path, model_dir, total_files, 0, "Pitch 提取", "extracting_pitch", _stop_watcher),
        daemon=True,
    )
    watcher.start()

    with concurrent.futures.ProcessPoolExecutor(max_workers=len(devices)) as executor:
        tasks = [
            executor.submit(
                process_files,
                files[i :: len(devices)],
                f0_method,
                devices[i],
                done_path,
            )
            for i in range(len(devices))
        ]
        try:
            for future in concurrent.futures.as_completed(tasks):
                done_files += int(future.result())
                now_time = time.time()
                if total_files and (
                    now_time - last_report >= 0.5 or done_files == total_files
                ):
                    last_report = now_time
                    update_progress(
                        Path(model_dir),
                        phase="extracting_pitch",
                        percent=done_files * 45 / total_files,
                        stage_detail=f"Pitch 提取 {done_files}/{total_files}",
                        done=False,
                    )
        finally:
            _stop_watcher.set()
            watcher.join(timeout=2)
            try:
                os.unlink(done_path)
            except FileNotFoundError:
                pass

    logger.info("Pitch extraction completed in %.2f seconds.", time.time() - start_time)


def process_file_embedding(
    files,
    embedder_model,
    embedder_model_custom,
    device_num,
    device,
    n_threads,
    done_path=None,
):
    model = load_embedding(embedder_model, embedder_model_custom).to(device).float()
    model.eval()
    n_threads = max(1, n_threads)

    def worker(file_info):
        wav_file_path, _, _, out_file_path = file_info
        try:
            if not pathlib.Path(out_file_path).exists():
                feats = torch.from_numpy(load_audio_16k(wav_file_path)).to(device).float()
                feats = feats.view(1, -1)
                with torch.no_grad():
                    result = model(feats)["last_hidden_state"]
                feats_out = result.squeeze(0).float().cpu().numpy()
                if not np.isnan(feats_out).any():
                    np.save(out_file_path, feats_out, allow_pickle=False)
                else:
                    logger.error("%s contains NaN values and will be skipped.", wav_file_path)
        except Exception as error:  # noqa: BLE001
            logger.error("Failed to embed %s: %s", wav_file_path, error)
        finally:
            if done_path:
                with open(done_path, "a", encoding="utf-8") as done_file:
                    done_file.write("1\n")

    with tqdm.tqdm(total=len(files), leave=True, position=device_num) as pbar:
        with concurrent.futures.ThreadPoolExecutor(max_workers=n_threads) as executor:
            futures = [executor.submit(worker, f) for f in files]
            for _ in concurrent.futures.as_completed(futures):
                pbar.update(1)
    return len(files)


def run_embedding_extraction(
    files: list[list[str]],
    devices: list[str],
    embedder_model: str,
    embedder_model_custom: str | None,
    threads: int,
    model_dir: str,
) -> None:
    devices_str = ", ".join(devices)
    logger.info(
        "Starting embedding extraction with %d cores on %s...",
        threads,
        devices_str,
    )
    start_time = time.time()
    total_files = len(files)
    done_files = 0
    last_report = 0.0
    done_path = os.path.join(model_dir, ".extract_done_embed")
    try:
        os.unlink(done_path)
    except FileNotFoundError:
        pass
    _stop_watcher = threading.Event()
    watcher = threading.Thread(
        target=_watch_done,
        args=(done_path, model_dir, total_files, 45, "Embedding 提取", "extracting_embed", _stop_watcher),
        daemon=True,
    )
    watcher.start()

    with concurrent.futures.ProcessPoolExecutor(max_workers=len(devices)) as executor:
        tasks = [
            executor.submit(
                process_file_embedding,
                files[i :: len(devices)],
                embedder_model,
                embedder_model_custom,
                i,
                devices[i],
                threads // len(devices),
                done_path,
            )
            for i in range(len(devices))
        ]
        try:
            for future in concurrent.futures.as_completed(tasks):
                done_files += int(future.result())
                now_time = time.time()
                if total_files and (
                    now_time - last_report >= 0.5 or done_files == total_files
                ):
                    last_report = now_time
                    update_progress(
                        Path(model_dir),
                        phase="extracting_embed",
                        percent=45 + done_files * 50 / total_files,
                        stage_detail=f"Embedding 提取 {done_files}/{total_files}",
                        done=False,
                    )
        finally:
            _stop_watcher.set()
            watcher.join(timeout=2)
            try:
                os.unlink(done_path)
            except FileNotFoundError:
                pass

    logger.info(
        "Embedding extraction completed in %.2f seconds.",
        time.time() - start_time,
    )


def initialize_extraction(
    exp_dir: str,
    f0_method: str,
    embedder_model: str,
) -> list[list[str]]:
    wav_path = os.path.join(exp_dir, "sliced_audios_16k")
    pathlib.Path(os.path.join(exp_dir, f"f0_{f0_method}")).mkdir(
        exist_ok=True, parents=True
    )
    pathlib.Path(os.path.join(exp_dir, f"f0_{f0_method}_voiced")).mkdir(
        exist_ok=True, parents=True
    )
    pathlib.Path(os.path.join(exp_dir, f"{embedder_model}_extracted")).mkdir(
        exist_ok=True, parents=True
    )

    files: list[list[str]] = []
    for file in glob.glob(os.path.join(wav_path, "*.wav")):
        file_name = os.path.basename(file)
        file_info = [
            file,
            os.path.join(exp_dir, f"f0_{f0_method}", file_name + ".npy"),
            os.path.join(exp_dir, f"f0_{f0_method}_voiced", file_name + ".npy"),
            os.path.join(
                exp_dir,
                f"{embedder_model}_extracted",
                file_name.replace("wav", "npy"),
            ),
        ]
        files.append(file_info)

    return files


def update_model_info(
    exp_dir: str,
    embedder_model: str,
    custom_embedder_model_hash: str | None,
) -> None:
    file_path = os.path.join(exp_dir, "model_info.json")
    if pathlib.Path(file_path).exists():
        with pathlib.Path(file_path).open() as f:
            data = json.load(f)
    else:
        data = {}
    data["embedder_model"] = embedder_model
    data["custom_embedder_model_hash"] = custom_embedder_model_hash
    with pathlib.Path(file_path).open("w") as f:
        json.dump(data, f, indent=4)
