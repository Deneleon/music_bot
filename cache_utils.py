"""cache_utils.py
================
Функции, отвечающие за локальный диск-кеш (96×54 thumbnails).

• **thumb_from_disk(vid)**   — вернуть ImageTk.PhotoImage для Treeview; если
                               файла нет, вернуть прозрачную заглушку.
• **sync_cache(...)**        — фоновая проверка кеша: удаляем лишние файлы,
                               скачиваем недостающие.  Используется при
                               запуске приложения (через Splash).

Модуль зависит от `tkinter` и `Pillow`, потому что возвращает ImageTk объекты.
"""
from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Dict, List, Tuple

import tkinter as tk
from PIL import Image, ImageTk

from config import CACHE_DIR, ICON_H, ICON_W
from gui_widgets import Splash
from youtube_utils import download_thumbnail
from youtube_utils import youtube_id as _youtube_id

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Внутренние кеши
# ---------------------------------------------------------------------------

_thumb_photo_cache: Dict[str, ImageTk.PhotoImage] = {}
_blank_icon: ImageTk.PhotoImage | None = None
_cache_lock = threading.Lock()  # защита при одновременных обращениях


# ---------------------------------------------------------------------------
# API: получить превью или заглушку
# ---------------------------------------------------------------------------

def _blank_icon_factory() -> ImageTk.PhotoImage:
    global _blank_icon  # noqa: PLW0603
    if _blank_icon is None:
        _blank_icon = ImageTk.PhotoImage(Image.new("RGBA", (ICON_W, ICON_H), (0, 0, 0, 0)))
    return _blank_icon


def thumb_from_disk(vid: str | None):
    """Вернуть ImageTk.PhotoImage превью (или пустую картинку).

    Возвращаемый объект кэшируется в памяти, чтобы не плодить ImageTk.
    """
    if not vid:
        return _blank_icon_factory()

    key = str(vid)
    if key in _thumb_photo_cache:
        return _thumb_photo_cache[key]

    path = CACHE_DIR / f"{vid}.jpg"
    if path.is_file():
        try:
            img = ImageTk.PhotoImage(Image.open(path).resize((ICON_W, ICON_H)))
            _thumb_photo_cache[key] = img
            return img
        except Exception:  # noqa: BLE001
            logger.warning("Broken image file for %s", path)

    return _blank_icon_factory()


# ---------------------------------------------------------------------------
# Фоновая синхронизация кеша (используется main.py)
# ---------------------------------------------------------------------------

def sync_cache(playlists: Dict[str, List[Dict[str, str]]], gui_ref: tk.Tk, splash: Splash):
    """Скачать недостающие превью и удалить лишние файлы.

    Аргументы:
        playlists — словарь плейлистов (pm.data)
        gui_ref   — ссылка на GUI, чтобы вызывать .after()
        splash    — окно сплэша для отображения прогресса
    """

    existing = {f.stem for f in CACHE_DIR.glob("*.jpg")}
    needed = {}

    # Сбор ID всех треков
    for pl in playlists.values():
        for tr in pl:
            vid = tr.get("vid") or _youtube_id(tr["url"])
            tr["vid"] = vid
            if vid:
                needed[vid] = f"https://i.ytimg.com/vi/{vid}/default.jpg"

    # Удаляем лишние файлы --------------------------------------------------
    for extra in existing - needed.keys():
        try:
            (CACHE_DIR / f"{extra}.jpg").unlink(missing_ok=True)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not remove %s: %s", extra, exc)

    # Скачиваем недостающие -------------------------------------------------
    todo = [vid for vid in needed if vid not in existing]
    splash.prog["maximum"] = len(todo) if todo else 1

    for idx, vid in enumerate(todo, 1):
        download_thumbnail(needed[vid], vid, (ICON_W, ICON_H))
        gui_ref.after(0, splash.step, f"{idx}/{len(todo)}")

    # Обновляем GUI и закрываем сплэш --------------------------------------
    gui_ref.after(0, gui_ref.refresh_tracks)
    gui_ref.after(0, splash.destroy)

    # Финальное сохранение через PlaylistManager (если GUI ещё жив)
    if hasattr(gui_ref, "pm"):
        gui_ref.pm.save()
