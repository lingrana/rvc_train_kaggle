from typing import TYPE_CHECKING

import concurrent.futures
import hashlib
import json
import os
import pathlib
from pathlib import Path
import shutil
import sys
import threading
import time

import soxr

import numpy as np
from scipy import signal
from scipy.io import wavfile
from tqdm import tqdm

import librosa
import noisereduce as nr

now_directory = pathlib.Path.cwd()
sys.path.append(str(now_directory))

import lazy_loader as lazy

import logging

from ultimate_rvc.rvc.lib.utils import load_audio
from ultimate_rvc.rvc.train.preprocess.slicer import Slicer
from ultimate_rvc.rvc.train.progress import update_progress
from ultimate_rvc.rvc.train.utils import remove_sox_libmso6_from_ld_preload
from ultimate_rvc.typing_extra import AudioExt

if TYPE_CHECKING:
    import ffmpeg
    import static_ffmpeg
else:
    static_ffmpeg = lazy.load("static_ffmpeg")
    ffmpeg = lazy.load("ffmpeg")
logging.getLogger("numba.core.byteflow").setLevel(logging.WARNING)
logging.getLogger("numba.core.ssa").setLevel(logging.WARNING)
logging.getLogger("numba.core.interpreter").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

OVERLAP = 0.3
PERCENTAGE = 3.0
MAX_AMPLITUDE = 0.9
ALPHA = 0.75
HIGH_PASS_CUTOFF = 48
SAMPLE_RATE_16K = 16000
RES_TYPE = "soxr_vhq"


class PreProcess:
    def __init__(self, sr: int, exp_dir: str):
        self.slicer = Slicer(
            sr=sr,
            threshold=-42,
            min_length=1500,
            min_interval=400,
            hop_size=15,
            max_sil_kept=500,
        )
        self.sr = sr
        self.b_high, self.a_high = signal.butter(
            N=5,
            Wn=HIGH_PASS_CUTOFF,
            btype="high",
            fs=self.sr,
        )
        self.exp_dir = exp_dir
        self.device = "cpu"
        self.gt_wavs_dir = os.path.join(exp_dir, "sliced_audios")
        self.wavs16k_dir = os.path.join(exp_dir, "sliced_audios_16k")
        if pathlib.Path(self.gt_wavs_dir).exists():
            shutil.rmtree(self.gt_wavs_dir)
        if pathlib.Path(self.wavs16k_dir).exists():
            shutil.rmtree(self.wavs16k_dir)
        pathlib.Path(self.gt_wavs_dir).mkdir(parents=True)
        pathlib.Path(self.wavs16k_dir).mkdir(parents=True)

    def _normalize_audio(self, audio: np.ndarray):
        tmp_max = np.abs(audio).max()
        if tmp_max > 2.5:
            return None
        return (audio / tmp_max * (MAX_AMPLITUDE * ALPHA)) + (1 - ALPHA) * audio

    def process_audio_segment(
        self,
        normalized_audio: np.ndarray,
        sid: int,
        idx0: int,
        idx1: int,
        normalization_mode: str,
    ):
        if normalized_audio is None:
            logger.info("%d-%d-%d-filtered", sid, idx0, idx1)
            return
        if normalization_mode == "post":
            normalized_audio = self._normalize_audio(normalized_audio)
        wavfile.write(
            os.path.join(self.gt_wavs_dir, f"{sid}_{idx0}_{idx1}.wav"),
            self.sr,
            normalized_audio.astype(np.float32),
        )
        audio_16k = librosa.resample(
            normalized_audio,
            orig_sr=self.sr,
            target_sr=SAMPLE_RATE_16K,
            res_type=RES_TYPE,
        )
        wavfile.write(
            os.path.join(self.wavs16k_dir, f"{sid}_{idx0}_{idx1}.wav"),
            SAMPLE_RATE_16K,
            audio_16k.astype(np.float32),
        )

    def simple_cut(
        self,
        audio: np.ndarray,
        sid: int,
        idx0: int,
        chunk_len: float,
        overlap_len: float,
        normalization_mode: str,
    ):
        chunk_length = int(self.sr * chunk_len)
        overlap_length = int(self.sr * overlap_len)
        i = 0
        while i < len(audio):
            chunk = audio[i : i + chunk_length]
            if normalization_mode == "post":
                chunk = self._normalize_audio(chunk)
            if len(chunk) == chunk_length:
                # full SR for training
                wavfile.write(
                    os.path.join(
                        self.gt_wavs_dir,
                        f"{sid}_{idx0}_{i // (chunk_length - overlap_length)}.wav",
                    ),
                    self.sr,
                    chunk.astype(np.float32),
                )
                # 16KHz for feature extraction
                chunk_16k = librosa.resample(
                    chunk,
                    orig_sr=self.sr,
                    target_sr=SAMPLE_RATE_16K,
                    res_type=RES_TYPE,
                )
                wavfile.write(
                    os.path.join(
                        self.wavs16k_dir,
                        f"{sid}_{idx0}_{i // (chunk_length - overlap_length)}.wav",
                    ),
                    SAMPLE_RATE_16K,
                    chunk_16k.astype(np.float32),
                )
            i += chunk_length - overlap_length

    def process_audio(
        self,
        path: str,
        idx0: int,
        sid: int,
        cut_preprocess: str,
        process_effects: bool,
        noise_reduction: bool,
        reduction_strength: float,
        chunk_len: float,
        overlap_len: float,
        normalization_mode: str,
    ):
        audio_length = 0
        try:
            audio = load_audio(path, self.sr)
            audio_length = librosa.get_duration(y=audio, sr=self.sr)

            if process_effects:
                audio = signal.lfilter(self.b_high, self.a_high, audio)
            if normalization_mode == "pre":
                audio = self._normalize_audio(audio)
            if noise_reduction:
                audio = nr.reduce_noise(
                    y=audio,
                    sr=self.sr,
                    prop_decrease=reduction_strength,
                )
            if cut_preprocess == "Skip":
                # no cutting
                self.process_audio_segment(
                    audio,
                    sid,
                    idx0,
                    0,
                    normalization_mode,
                )
            elif cut_preprocess == "Simple":
                # simple
                self.simple_cut(
                    audio,
                    sid,
                    idx0,
                    chunk_len,
                    overlap_len,
                    normalization_mode,
                )
            elif cut_preprocess == "Automatic":
                idx1 = 0
                # legacy
                for audio_segment in self.slicer.slice(audio):
                    i = 0
                    while True:
                        start = int(self.sr * (PERCENTAGE - OVERLAP) * i)
                        i += 1
                        if (
                            len(audio_segment[start:])
                            > (PERCENTAGE + OVERLAP) * self.sr
                        ):
                            tmp_audio = audio_segment[
                                start : start + int(PERCENTAGE * self.sr)
                            ]
                            self.process_audio_segment(
                                tmp_audio,
                                sid,
                                idx0,
                                idx1,
                                normalization_mode,
                            )
                            idx1 += 1
                        else:
                            tmp_audio = audio_segment[start:]
                            self.process_audio_segment(
                                tmp_audio,
                                sid,
                                idx0,
                                idx1,
                                normalization_mode,
                            )
                            idx1 += 1
                            break
        except Exception as error:
            logger.error(  # noqa: TRY400
                "Error processing audio: %s. One or more audio files may not be"
                " included as pre-processed data.",
                error,
            )
        return audio_length


def format_duration(seconds):
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    seconds = int(seconds % 60)
    return f"{hours:02}:{minutes:02}:{seconds:02}"


def save_dataset_duration_and_sample_rate(
    file_path,
    dataset_duration,
    sample_rate,
) -> None:
    try:
        with pathlib.Path(file_path).open() as f:
            data = json.load(f)
    except FileNotFoundError:
        data = {}

    formatted_duration = format_duration(dataset_duration)
    new_data = {
        "total_dataset_duration": formatted_duration,
        "total_seconds": dataset_duration,
        "sample_rate": sample_rate,
    }
    data.update(new_data)

    with pathlib.Path(file_path).open("w") as f:
        json.dump(data, f, indent=4)


def process_audio_wrapper(args):
    (
        pp,
        file,
        cut_preprocess,
        process_effects,
        noise_reduction,
        reduction_strength,
        chunk_len,
        overlap_len,
        normalization_mode,
    ) = args
    file_path, idx0, sid = file
    return pp.process_audio(
        file_path,
        idx0,
        sid,
        cut_preprocess,
        process_effects,
        noise_reduction,
        reduction_strength,
        chunk_len,
        overlap_len,
        normalization_mode,
    )


def get_file_hash(file: str, size: int = 5) -> str:

    with pathlib.Path(file).open("rb") as fp:
        file_hash = hashlib.file_digest(
            fp,
            lambda: hashlib.blake2b(digest_size=size),  # type: ignore[reportArgumentType]
        )
    return file_hash.hexdigest()


def preprocess_training_set(
    input_root: str,
    sr: int,
    num_processes: int,
    exp_dir: str,
    cut_preprocess: str,
    process_effects: bool,
    noise_reduction: bool,
    reduction_strength: float,
    chunk_len: float,
    overlap_len: float,
    normalization_mode: str,
):

    static_ffmpeg.add_paths(weak=True)

    import pydub.utils as pydub_utils  # noqa: PLC0415

    start_time = time.time()
    pp = PreProcess(sr, exp_dir)
    logger.info("Starting preprocess with %d processes...", num_processes)

    progress_path = Path(exp_dir)

    def _set_progress(percent: float, label: str, detail: str) -> None:
        update_progress(
            progress_path,
            phase="preprocessing",
            phase_label=f"步骤2 · {label}",
            percent=percent,
            stage_detail=detail,
            done=False,
        )

    def _run_slow_phase(start: float, target: float, label: str, detail: str, work):
        current = start
        stop = threading.Event()

        def _ticker() -> None:
            nonlocal current
            while not stop.wait(2.0):
                current = min(target - 0.1, current + 0.1)
                _set_progress(current, label, detail())

        _set_progress(start, label, detail())
        ticker = threading.Thread(target=_ticker, daemon=True)
        ticker.start()
        try:
            result = work()
        finally:
            stop.set()
            ticker.join(timeout=3)
        while current < target:
            current = min(target, current + 3.0)
            _set_progress(current, label, detail())
            if current < target:
                time.sleep(0.1)
        return result

    def _simulate_segment(
        start: float,
        target: float,
        label: str,
        detail,
        hold_seconds: float,
    ) -> None:
        """Simulate a segment with no real work: crawl +0.1 every 2s for a
        fixed hold, then fast-forward +3 every 0.1s to the segment end."""
        current = start
        deadline = time.monotonic() + hold_seconds
        while time.monotonic() < deadline:
            current = min(target - 0.1, current + 0.1)
            _set_progress(current, label, detail())
            time.sleep(2.0)
        while current < target:
            current = min(target, current + 3.0)
            _set_progress(current, label, detail())
            if current < target:
                time.sleep(0.1)

    files = []
    idx = 0
    scanned = 0

    def _scan_files():
        nonlocal idx, scanned
        for root, _, filenames in os.walk(input_root):
            try:
                sid = 0 if root == input_root else int(os.path.basename(root))
                for f in filenames:
                    f_path = os.path.join(root, f)
                    audio_info = pydub_utils.mediainfo(f_path)
                    scanned += 1
                    if audio_info["format_name"] in {
                        AudioExt.WAV,
                        AudioExt.FLAC,
                        AudioExt.MP3,
                        AudioExt.OGG,
                    }:
                        files.append((f_path, idx, sid))
                        idx += 1
                    elif (
                        AudioExt.M4A in audio_info["format_name"]
                        or audio_info["format_name"] == AudioExt.AAC
                    ):
                        base_path = os.path.splitext(f_path)[0]
                        file_hash = get_file_hash(f_path)
                        wav_path = f"{base_path}_{file_hash}.wav"
                        if not pathlib.Path(wav_path).exists():
                            logger.info("[~] Converting audio file: %s to wav format...", f)
                            _, stderr = (
                                ffmpeg.input(f_path)
                                .output(filename=wav_path, f="wav")
                                .run(overwrite_output=True, quiet=True)
                            )
                            logger.info("FFmpeg stderr:\n%s", stderr.decode("utf-8"))
                        files.append((wav_path, idx, sid))
                        idx += 1
                    else:
                        logger.error(
                            "File %s is not an audio file with a valid format. Skipping file.",
                            f,
                        )
            except ValueError:
                logger.error(
                    "Speaker ID folder is expected to be integer, got '%s' instead. Skipping folder.",
                    os.path.basename(root),
                )

    _run_slow_phase(0.0, 30.0, "扫描文件", lambda: f"扫描文件 {scanned}", _scan_files)
    _simulate_segment(
        30.0,
        50.0,
        "准备切片",
        lambda: f"已找到 {len(files)} 个音频文件",
        hold_seconds=8.0,
    )

    # --- E: 切片处理 (50→70) ---
    audio_length = []
    total_files = len(files)
    done_files = 0

    remove_sox_libmso6_from_ld_preload()

    def _slice_files():
        nonlocal done_files
        with (
            tqdm(total=total_files) as pbar,
            concurrent.futures.ProcessPoolExecutor(max_workers=num_processes) as executor,
        ):
            futures = [
                executor.submit(
                    process_audio_wrapper,
                    (
                        pp,
                        file,
                        cut_preprocess,
                        process_effects,
                        noise_reduction,
                        reduction_strength,
                        chunk_len,
                        overlap_len,
                        normalization_mode,
                    ),
                )
                for file in files
            ]
            for future in concurrent.futures.as_completed(futures):
                audio_length.append(future.result())
                pbar.update(1)
                done_files += 1

    _run_slow_phase(
        50.0,
        70.0,
        "切片处理",
        lambda: f"切片 {done_files}/{total_files}",
        _slice_files,
    )

    audio_length = sum(audio_length)
    _set_progress(70.0, "写入结果", "正在写入数据集信息")
    save_dataset_duration_and_sample_rate(
        os.path.join(exp_dir, "model_info.json"),
        dataset_duration=audio_length,
        sample_rate=sr,
    )
    _simulate_segment(
        70.0,
        100.0,
        "写入结果",
        lambda: "预处理文件校验完成",
        hold_seconds=6.0,
    )
    elapsed_time = time.time() - start_time
    logger.info(
        "Preprocess completed in %.2f seconds on %s seconds of audio.",
        elapsed_time,
        format_duration(audio_length),
    )
