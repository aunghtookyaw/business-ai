#!/usr/bin/env python3
"""Size-based rotation for BigShot Business OS operational logs."""

from pathlib import Path
import shutil


LOG_DIR = Path("/Users/bigshot/Library/Logs/BigShotBusinessOS")
MAX_BYTES = 10 * 1024 * 1024
KEEP = 10


def rotate(path):
    if not path.is_file() or path.stat().st_size < MAX_BYTES:
        return
    oldest = path.with_name(f"{path.name}.{KEEP}")
    oldest.unlink(missing_ok=True)
    for index in range(KEEP - 1, 0, -1):
        source = path.with_name(f"{path.name}.{index}")
        if source.exists():
            source.rename(path.with_name(f"{path.name}.{index + 1}"))
    # launchd keeps stdout/stderr file descriptors open. Copy-and-truncate keeps
    # those descriptors attached to the active log after rotation.
    shutil.copy2(path, path.with_name(f"{path.name}.1"))
    with path.open("w"):
        pass


LOG_DIR.mkdir(parents=True, exist_ok=True)
for log_path in LOG_DIR.glob("*.log"):
    rotate(log_path)
