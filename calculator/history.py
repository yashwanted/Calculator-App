"""Persistent calculation history, stored as JSON in the user's app data folder.

Storage problems are never fatal: a missing or corrupt file means an empty
history, and a failed save leaves the in-memory history working normally.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

APP_FOLDER_NAME = "Calculator"
MAX_ENTRIES = 500


def default_history_path() -> Path:
    """Return the per-user history file path for this platform."""
    home = Path.home()
    if sys.platform == "darwin":
        base = home / "Library" / "Application Support"
    elif sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", home / "AppData" / "Roaming"))
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", home / ".local" / "share"))
    return base / APP_FOLDER_NAME / "history.json"


@dataclass(frozen=True)
class HistoryEntry:
    expression: str  # As displayed, e.g. "2 + 3 × 4 =".
    result: str  # As displayed, e.g. "1,234.5".
    value: str  # Full-precision value that gets loaded back on click.


class HistoryStore:
    """Past calculations, newest first."""

    def __init__(self, path: Optional[Path] = None):
        self.path = Path(path) if path is not None else default_history_path()
        self.entries: list[HistoryEntry] = self._load()

    def add(self, expression: str, result: str, value: str) -> HistoryEntry:
        entry = HistoryEntry(expression, result, value)
        self.entries.insert(0, entry)
        del self.entries[MAX_ENTRIES:]
        self._save()
        return entry

    def clear(self) -> None:
        self.entries.clear()
        self._save()

    def _load(self) -> list[HistoryEntry]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
        if not isinstance(data, list):
            return []
        entries = []
        for item in data[:MAX_ENTRIES]:
            # Skip anything malformed rather than discarding the whole file.
            if isinstance(item, dict) and all(
                isinstance(item.get(field), str)
                for field in ("expression", "result", "value")
            ):
                entries.append(
                    HistoryEntry(item["expression"], item["result"], item["value"])
                )
        return entries

    def _save(self) -> None:
        """Write atomically, so that a crash can't leave a half-written file."""
        temporary_path = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            payload = json.dumps(
                [asdict(entry) for entry in self.entries],
                ensure_ascii=False,
                indent=2,
            )
            descriptor, temporary_path = tempfile.mkstemp(
                dir=self.path.parent, prefix=".history-", suffix=".tmp"
            )
            with os.fdopen(descriptor, "w", encoding="utf-8") as file:
                file.write(payload)
            os.replace(temporary_path, self.path)
        except OSError:
            if temporary_path is not None:
                try:
                    os.unlink(temporary_path)
                except OSError:
                    pass
