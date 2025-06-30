"""youtube_utils.py
==================
Функции-помощники, работающие с YouTube:

* **youtube_id(url)**        — извлекает 11‑символьный идентификатор видео.
* **ytdlp_info(url)**        — асинхронно возвращает метаданные ролика через
                               *yt‑dlp*, результат кешируется.
* **download_thumbnail(...)**— скачивает миниатюру и сохраняет в `cache/thumbs`.

Этот модуль намеренно ничего не знает о Tk или ImageTk — только о диске и сети.
"""
from __future__ import annotations

import asyncio
import logging
import re
import threading
from io import BytesIO
from pathlib import Path
from typing import Dict, Final, Tuple

import requests
import yt_dlp as ytdlp
from PIL import Image

from config import CACHE_DIR

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Регулярка для извлечения ID
# ---------------------------------------------------------------------------

_YT_RE: Final[re.Pattern[str]] = re.compile(r"(?:v=|/)([A-Za-z0-9_-]{11})")


def youtube_id(url: str) -> str | None:
    """Вернуть 11‑символьный ID видео или *None*, если ссылка не похожа."""
    m = _YT_RE.search(url)
    return m.group(1) if m else None


# ---------------------------------------------------------------------------
# yt‑dlp: вытаскиваем info в отдельном потоке, чтобы не блокировать loop
# ---------------------------------------------------------------------------

_ytdlp_cache: Dict[str, dict] = {}
_ytdlp_lock = threading.Lock()  # сериализуем доступ к yt‑dlp (она не потокобез.)


async def ytdlp_info(url: str) -> dict:  # noqa: D401 — imperative mood OK
    """Асинхронно получить info-dict от yt-dlp; результат кешируется."""

    # --- кеш ---------------------------------------------------------------
    if url in _ytdlp_cache:
        return _ytdlp_cache[url]

    loop = asyncio.get_running_loop()

    # --- извлечение метаданных --------------------------------------------
    def _extract():
        with _ytdlp_lock:                     # yt-dlp не потокобезопасна
            with ytdlp.YoutubeDL({"quiet": True, "format": "bestaudio"}) as y:
                return y.extract_info(url, download=False)

    info = await loop.run_in_executor(None, _extract)

    # --- гарантируем наличие поля «thumbnail» -----------------------------
    if "thumbnail" not in info:
        if info.get("thumbnails"):            # берём самую большую картинку
            best = max(info["thumbnails"], key=lambda t: t.get("width", 0))
            info["thumbnail"] = best.get("url")
        elif info.get("id"):                  # запасной вариант по шаблону
            info["thumbnail"] = f"https://i.ytimg.com/vi/{info['id']}/hqdefault.jpg"

    # --- кладём в кеш и возвращаем ----------------------------------------
    _ytdlp_cache[url] = info
    return info



# ---------------------------------------------------------------------------
# Скачивание миниатюр
# ---------------------------------------------------------------------------

_thumb_cache: Dict[str, Path] = {}


def download_thumbnail(th_url: str, vid: str, size: Tuple[int, int]) -> Path:
    """Скачать превью *size* и сохранить в CACHE_DIR/<vid>.jpg.

    Если файл уже существует, просто вернуть путь.
    """

    dest = CACHE_DIR / f"{vid}.jpg"
    if dest.exists():
        _thumb_cache[vid] = dest
        return dest

    try:
        r = requests.get(th_url, timeout=15)
        r.raise_for_status()
        img = Image.open(BytesIO(r.content)).resize(size)
        dest.parent.mkdir(parents=True, exist_ok=True)
        img.save(dest, "JPEG")
        _thumb_cache[vid] = dest
    except Exception as exc:  # noqa: BLE001
        logger.warning("thumbnail download failed for %s: %s", vid, exc)
    return dest


__all__ = ["youtube_id", "ytdlp_info", "download_thumbnail"]
