"""Atomic JSON persistence — crash/race-safe state writes.

Two processes share the state dir (the realtime bot and the always-on brain). A plain
open("w") truncates the file first, so a reader (or a crash) mid-write sees partial
JSON. Writing to a temp file in the same directory and os.replace()-ing it in is
atomic on POSIX: readers see either the old complete file or the new complete file,
never a torn one.
"""
import json
import os
import tempfile


def atomic_json_dump(obj, path: str, indent: int = 2) -> None:
    d = os.path.dirname(path) or "."
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".tmp-", suffix=".json")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(obj, f, indent=indent)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
