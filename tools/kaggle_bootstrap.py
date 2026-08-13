"""Install and verify the canonical RVC v2 48k training assets on Kaggle."""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
from pathlib import Path

from huggingface_hub import hf_hub_download


REPOSITORY = "lj1995/VoiceConversionWebUI"
ASSETS = {
    "pretrained_v2/f0G48k.pth": (
        "models/rvc/pretraineds/hifi-gan/f0G48k.pth",
        "b5d51f589cc3632d4eae36a315b4179397695042edc01d15312e1bddc2b764a4",
    ),
    "pretrained_v2/f0D48k.pth": (
        "models/rvc/pretraineds/hifi-gan/f0D48k.pth",
        "2269b73c7a4cf34da09aea99274dabf99b2ddb8a42cbfb065fb3c0aa9a2fc748",
    ),
    "hubert_base/pytorch_model.bin": (
        "models/rvc/embedders/hubert_base/pytorch_model.bin",
        "cc8c20f4b90a520757260197a3ff2505705a7adbd20ad9eeaa4e1a9b38442ef5",
    ),
    "hubert_base/config.json": (
        "models/rvc/embedders/hubert_base/config.json",
        "0346950779dfb7f9316fa74ed846e2b8a22a08eedfdc5387b73f327cb1a4a7cf",
    ),
    "hubert_base/preprocessor_config.json": (
        "models/rvc/embedders/hubert_base/preprocessor_config.json",
        "7c1976a680fb7acc757cd36fb08eef878fa36c70b4c9d2d595df9c608bbbbf0e",
    ),
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        while chunk := file.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def install_assets(project_root: Path) -> None:
    for remote_name, (relative_destination, expected_hash) in ASSETS.items():
        destination = project_root / relative_destination
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.is_file() and sha256(destination) == expected_hash:
            print(f"[RVC] verified {destination.name}")
            continue
        downloaded = Path(hf_hub_download(REPOSITORY, remote_name))
        temporary = destination.with_suffix(destination.suffix + ".tmp")
        shutil.copyfile(downloaded, temporary)
        actual_hash = sha256(temporary)
        if actual_hash != expected_hash:
            temporary.unlink(missing_ok=True)
            raise RuntimeError(
                f"SHA-256 mismatch for {remote_name}: {actual_hash} != {expected_hash}"
            )
        os.replace(temporary, destination)
        print(f"[RVC] installed {relative_destination}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    install_assets(args.project_root.resolve())


if __name__ == "__main__":
    main()
