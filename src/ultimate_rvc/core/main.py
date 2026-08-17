"""
Module which defines functions for initializing the core of the Ultimate
RVC project.
"""

from __future__ import annotations

import shutil
from typing import TYPE_CHECKING

import lazy_loader as lazy

from ultimate_rvc.core.common import FLAG_FILE
from ultimate_rvc.rvc.lib.tools.prerequisites_download import (
    prequisites_download_pipeline,
)

if TYPE_CHECKING:
    import static_sox

else:
    static_sox = lazy.load("static_sox")


def initialize() -> None:
    """Initialize the Ultimate RVC project."""
    prequisites_download_pipeline(exe=False)
    if not FLAG_FILE.is_file():
        # Kaggle already provides SoX. Avoid static-sox's remote binary
        # download when a working system executable is available.
        if shutil.which("sox") is None:
            static_sox.add_paths(weak=True)
        FLAG_FILE.touch()


if __name__ == "__main__":
    initialize()
