"""Persistent record of target media that already produced a saved output.

The Target Media panel uses this to draw a green tick on items that were
processed, and batch processing can use it to skip them. Records are keyed by
the normalized source path and remember the source file's size and mtime, so a
file that is replaced or edited afterwards stops counting as processed.

Pure Python (no Qt) so it can be unit tested and used from worker threads.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
import threading
import time
from collections.abc import Iterable

_TIMESTAMP_SUFFIX = r"_\d{4}_\d{2}_\d{2}_\d{2}_\d{2}_\d{2}"
_OUTPUT_EXTENSIONS = (".mp4", ".mkv", ".mov", ".avi", ".png", ".jpg", ".jpeg", ".webp")


def normalize_media_key(path: str) -> str:
    """Stable dictionary key for a media path (absolute, normalized, case-folded on Windows)."""
    return os.path.normcase(os.path.normpath(os.path.abspath(str(path))))


def _file_signature(path: str) -> tuple[int, float] | None:
    try:
        stat = os.stat(path)
    except OSError:
        return None
    return int(stat.st_size), round(float(stat.st_mtime), 3)


class ProcessedMediaStore:
    """Thread-safe JSON-backed store of processed target media."""

    VERSION = 1

    def __init__(self, store_path: str | os.PathLike[str]):
        self.store_path = str(store_path)
        self._lock = threading.Lock()
        self._records: dict[str, dict] = {}
        self._load()

    # ------------------------------------------------------------------ IO
    def _load(self) -> None:
        try:
            with open(self.store_path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError):
            return
        records = data.get("records") if isinstance(data, dict) else None
        if isinstance(records, dict):
            self._records = {
                str(k): v for k, v in records.items() if isinstance(v, dict)
            }

    def _save_locked(self) -> None:
        directory = os.path.dirname(self.store_path) or "."
        try:
            os.makedirs(directory, exist_ok=True)
            fd, tmp_path = tempfile.mkstemp(
                prefix=".processed_media_", suffix=".tmp", dir=directory
            )
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(
                    {"version": self.VERSION, "records": self._records}, fh, indent=1
                )
            os.replace(tmp_path, self.store_path)
        except OSError as exc:
            print(
                f"[WARN] ProcessedMediaStore: could not save {self.store_path}: {exc}"
            )

    # ------------------------------------------------------------- queries
    def is_processed(self, media_path: str) -> bool:
        key = normalize_media_key(media_path)
        with self._lock:
            record = self._records.get(key)
        if not record:
            return False
        signature = _file_signature(media_path)
        if signature is None:
            # Source no longer reachable: keep showing the record.
            return True
        size, mtime = signature
        return (
            record.get("size") == size
            and abs(float(record.get("mtime", -1.0)) - mtime) < 0.01
        )

    def outputs_for(self, media_path: str) -> list[str]:
        with self._lock:
            record = self._records.get(normalize_media_key(media_path)) or {}
        return list(record.get("outputs", []))

    def __len__(self) -> int:
        with self._lock:
            return len(self._records)

    # ----------------------------------------------------------- mutations
    def mark_processed(self, media_path: str, output_path: str | None = None) -> bool:
        signature = _file_signature(media_path)
        if signature is None:
            return False
        size, mtime = signature
        key = normalize_media_key(media_path)
        with self._lock:
            record = self._records.get(key)
            if (
                not record
                or record.get("size") != size
                or abs(float(record.get("mtime", -1.0)) - mtime) >= 0.01
            ):
                record = {"outputs": []}
            record.update(
                {
                    "path": os.path.normpath(os.path.abspath(str(media_path))),
                    "size": size,
                    "mtime": mtime,
                    "processed_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                }
            )
            outputs = record.setdefault("outputs", [])
            if output_path:
                normalized_output = os.path.normpath(str(output_path))
                if normalized_output not in outputs:
                    outputs.append(normalized_output)
                    del outputs[:-20]  # keep the record small
            self._records[key] = record
            self._save_locked()
        return True

    def unmark(self, media_path: str) -> bool:
        key = normalize_media_key(media_path)
        with self._lock:
            removed = self._records.pop(key, None) is not None
            if removed:
                self._save_locked()
        return removed


def match_outputs_to_sources(
    source_paths: Iterable[str], output_filenames: Iterable[str]
) -> dict[str, list[str]]:
    """Map source media to output files that VisoMaster's default naming produced.

    Default outputs are named ``<source stem>_YYYY_MM_DD_HH_MM_SS.<ext>`` (see
    ``misc_helpers.get_output_file_path``). Outputs saved under a job name or a
    custom file name can't be attributed and are ignored.
    """
    outputs = [
        name
        for name in output_filenames
        if os.path.splitext(name)[1].lower() in _OUTPUT_EXTENSIONS
    ]
    matches: dict[str, list[str]] = {}
    for source in source_paths:
        stem = os.path.splitext(os.path.basename(str(source)))[0]
        if not stem:
            continue
        pattern = re.compile(
            re.escape(stem) + _TIMESTAMP_SUFFIX + r"\.[A-Za-z0-9]+$", re.IGNORECASE
        )
        found = [name for name in outputs if pattern.match(os.path.basename(name))]
        if found:
            matches[str(source)] = found
    return matches
