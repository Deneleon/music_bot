"""playlist_manager.py
=====================
Управление JSON‑плейлистами (load / save / CRUD).

Формат файла совместим с исходным: объект { "Playlist name": [ {track}, … ] }.

Ключевые изменения (v2):
* Внутренний словарь хранится в `self._data`, чтобы не конфликтовать с
  одноимённым property.  GUI по‑прежнему использует `pm.data` для доступа.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, MutableMapping

from config import PLAYLIST_FILE

logger = logging.getLogger(__name__)


class PlaylistManager:  # noqa: D101 — simple manager class
    __slots__ = ("path", "_data")

    # ------------------------------------------------------------------
    # Constructor / IO
    # ------------------------------------------------------------------

    def __init__(self, path: Path | str | None = None) -> None:  # noqa: D401
        self.path: Path = Path(path or PLAYLIST_FILE)
        self._data: Dict[str, List[Dict[str, Any]]] = {}
        self.load()

    # ------------------------- file operations ------------------------
    def load(self) -> None:
        """Load playlists from JSON.

        On any error — start with empty dict and log the problem.
        """
        try:
            if self.path.is_file():
                with self.path.open("r", encoding="utf8") as f:
                    self._data = json.load(f)
            else:
                self._data = {}
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not load %s: %s", self.path, exc)
            self._data = {}

    def save(self) -> None:
        try:
            with self.path.open("w", encoding="utf8") as f:
                json.dump(self._data, f, ensure_ascii=False, indent=2)
        except Exception as exc:  # noqa: BLE001
            logger.error("Could not save %s: %s", self.path, exc)

    # ------------------------------------------------------------------
    # Playlist‑level operations
    # ------------------------------------------------------------------

    def add_playlist(self, name: str) -> None:
        if name in self._data:
            return
        self._data[name] = []
        self.save()

    def rename_playlist(self, old: str, new: str) -> None:
        if old not in self._data or new in self._data:
            return
        self._data[new] = self._data.pop(old)
        self.save()

    def delete_playlist(self, name: str) -> None:
        if name in self._data:
            self._data.pop(name)
            self.save()

    def move_playlist(self, index: int, delta: int) -> None:
        keys = list(self._data.keys())
        new_idx = index + delta
        if not (0 <= new_idx < len(keys)):
            return
        keys[index], keys[new_idx] = keys[new_idx], keys[index]
        self._data = {k: self._data[k] for k in keys}
        self.save()

    # ------------------------------------------------------------------
    # Track‑level operations
    # ------------------------------------------------------------------

    def _tracks(self, pl_name: str) -> List[Dict[str, Any]]:
        if pl_name not in self._data:
            raise KeyError(f"Playlist not found: {pl_name}")
        return self._data[pl_name]

    def add_track(self, pl_name: str, track: Dict[str, Any]) -> None:
        self._tracks(pl_name).append(track)
        self.save()

    def rename_track(self, pl_name: str, idx: int, new_title: str) -> None:
        tracks = self._tracks(pl_name)
        if 0 <= idx < len(tracks):
            tracks[idx]["title"] = new_title
            self.save()

    def delete_track(self, pl_name: str, idx: int) -> None:
        tracks = self._tracks(pl_name)
        if 0 <= idx < len(tracks):
            tracks.pop(idx)
            self.save()

    def move_track(self, pl_name: str, idx: int, delta: int) -> None:
        tracks = self._tracks(pl_name)
        new_idx = idx + delta
        if 0 <= new_idx < len(tracks):
            tracks[idx], tracks[new_idx] = tracks[new_idx], tracks[idx]
            self.save()

    # ------------------------------------------------------------------
    # Property for external read‑only access
    # ------------------------------------------------------------------

    @property
    def data(self) -> MutableMapping[str, List[Dict[str, Any]]]:  # noqa: D401
        """Return live reference to internal dict (read‑write by design)."""
        return self._data


__all__ = ["PlaylistManager"]
