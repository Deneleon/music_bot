"""config.py
=================
Централизованные настройки приложения.

Все чувствительные данные и машинозависимые пути задаются через файл `.env`
или переменные окружения.  Константы, не влияющие на безопасность, задаются
жёстко в коде.

• DISCORD_TOKEN — токен вашего Discord‑бота (обязательно)
• TARGET_USER_ID — ID пользователя, к которому бот привязывается (int, опц.)
• VOICE_ID       — голосовой канал, куда бот подключается по умолчанию
• FFMPEG_EXE     — путь к ffmpeg. Оставьте просто "ffmpeg", если он находится
                    в PATH.
• PLAYLIST_FILE  — имя JSON‑файла с плейлистами
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Final

from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Загрузка переменных окружения из .env (если есть)
# ---------------------------------------------------------------------------

load_dotenv()

# ---------------------------------------------------------------------------
# Базовые константы проекта
# ---------------------------------------------------------------------------

# Токен Discord‑бота (обязателен) -------------------------------------------
DISCORD_TOKEN: Final[str | None] = os.getenv("DISCORD_TOKEN")
if not DISCORD_TOKEN:
    raise RuntimeError(
        "DISCORD_TOKEN is not set. Добавьте в .env или переменные окружения."
    )

# Целевой пользователь (для auto‑join) --------------------------------------
TARGET_USER_ID: Final[int] = int(os.getenv("TARGET_USER_ID", "0"))

# Стартовый голосовой канал (0 → искать пользователя) -----------------------
VOICE_ID: Final[int] = int(os.getenv("VOICE_ID", "0"))

# Путь к ffmpeg --------------------------------------------------------------
FFMPEG_EXE: Final[str] = os.getenv("FFMPEG_EXE", "ffmpeg")

# Файл с плейлистами ---------------------------------------------------------
PLAYLIST_FILE: Final[str] = os.getenv("PLAYLIST_FILE", "playlists.json")

# Каталог кеша превью --------------------------------------------------------
BASE_DIR: Final[Path] = Path(__file__).resolve().parent
CACHE_DIR: Final[Path] = BASE_DIR / "cache" / "thumbs"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Размеры иконок/превью (px) -------------------------------------------------
ICON_W: Final[int] = 96
ICON_H: Final[int] = 54
PREVIEW_W: Final[int] = 320
PREVIEW_H: Final[int] = 180

# ---------------------------------------------------------------------------
__all__ = [
    "DISCORD_TOKEN",
    "TARGET_USER_ID",
    "VOICE_ID",
    "FFMPEG_EXE",
    "PLAYLIST_FILE",
    "CACHE_DIR",
    "ICON_W",
    "ICON_H",
    "PREVIEW_W",
    "PREVIEW_H",
]
