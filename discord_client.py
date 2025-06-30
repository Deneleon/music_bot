"""discord_client.py
===================
Обёртка над `discord.py`, инкапсулирующая всю логику подключения к голосовому
каналу и воспроизведения аудио.

Экспортируемое API, которым пользуется GUI и main:

• **run_discord_bot()**      — функция, которую вызывает `main.py` в фоновом
                                потоке; внутри создаётся event‑loop и
                                запускается `discord.Client.start()`.

• **ensure_join()**          — coroutine: подключиться (или вернуть) активный
                                `discord.VoiceClient`.
• **start_playback(track)**  — coroutine: начать воспроизведение трека
                                (`track` — dict с ключами «title» и «url»).
• **pause_toggle()**         — coroutine: приостановить / возобновить.
• **leave_voice()**          — coroutine: выйти из голосового канала.

• **BOT_LOOP**               — asyncio‑loop, в который GUI отправляет задачи
                                через `asyncio.run_coroutine_threadsafe`.
• **PLAYING_STATE**          — объект с текущим состоянием воспроизведения
                                (читает GUI; пишет `start_playback()`).
"""
from __future__ import annotations

import asyncio
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Final, Optional

import discord

from config import DISCORD_TOKEN, FFMPEG_EXE, TARGET_USER_ID, VOICE_ID
from youtube_utils import ytdlp_info

# ---------------------------------------------------------------------------
# Event‑loop и клиент Discord
# ---------------------------------------------------------------------------

BOT_LOOP: Final[asyncio.AbstractEventLoop] = asyncio.new_event_loop()

intents = discord.Intents.default()
intents.message_content = True
intents.members = intents.voice_states = True

bot: Final[discord.Client] = discord.Client(intents=intents, loop=BOT_LOOP)

# ---------------------------------------------------------------------------
# Общие ресурсы (блокировка и состояние)
# ---------------------------------------------------------------------------

vc_lock = threading.Lock()  # сериализация доступа к VoiceClient


@dataclass(slots=True)
class PlayingState:
    """Содержит всю публичную информацию о текущем треке."""

    # — данные трека --------------------------------------------------------
    title: str = ""
    src_url: str = ""
    thumb_url: str = ""
    duration: int = 0  # сек

    # — тайминг -------------------------------------------------------------
    start_time: float = 0.0  # время запуска в секундах (time.time())
    paused: bool = False
    pause_at: float = 0.0

    # — превью --------------------------------------------------------------
    preview_loaded: Any = None  # ImageTk.PhotoImage (загружается в GUI‑потоке)
    preview_loader_started: bool = False

    # ---------------------------------------------------------- runtime ----
    def clear(self) -> None:
        """Сбросить все поля к значениям по-умолчанию."""
        default = PlayingState.__new__(PlayingState)     # обойдём dataclass-init
        for name in self.__dataclass_fields__:
            setattr(self, name, getattr(default, name, None))

    # — свойства, используемые GUI -----------------------------------------
    @property
    def is_playing(self) -> bool:  # noqa: D401 — property not method
        return bool(self.title)

    @property
    def elapsed_seconds(self) -> int:  # noqa: D401
        if not self.is_playing:
            return 0
        if self.paused:
            return int(self.pause_at - self.start_time)
        return int(time.time() - self.start_time)

    @property
    def voice_connected(self) -> bool:  # noqa: D401
        return bool(bot.voice_clients)


PLAYING_STATE: Final[PlayingState] = PlayingState()

# ---------------------------------------------------------------------------
# Вспомогательные корутины
# ---------------------------------------------------------------------------


async def ensure_join() -> Optional[discord.VoiceClient]:
    """Подключиться к голосовому каналу или вернуть существующий VoiceClient."""

    if bot.voice_clients:
        return bot.voice_clients[0]

    # 1) явный VOICE_ID
    if VOICE_ID:
        ch = bot.get_channel(VOICE_ID)
        if isinstance(ch, discord.VoiceChannel):
            return await ch.connect()

    # 2) канал, где сидит TARGET_USER_ID
    for guild in bot.guilds:
        for ch in guild.voice_channels:
            if any(m.id == TARGET_USER_ID for m in ch.members):
                return await ch.connect()

    print("[WARN] User not in voice or channel not found.")  # простое логирование
    return None


async def start_playback(track: dict[str, Any]) -> None:
    """Запустить воспроизведение указанного трека (YouTube URL)."""

    if not track:
        return

    # — получаем инфо о видео
    info = await ytdlp_info(track["url"])
    vc = await ensure_join()
    if not vc:
        return

    # — Эксклюзивный доступ к VoiceClient -----------------------------------
    with vc_lock:
        if vc.is_playing():
            vc.pause()
            await asyncio.sleep(0.2)
            vc.stop()
        elif vc.is_paused():
            vc.stop()

        src = discord.FFmpegPCMAudio(
            info["url"],
            executable=FFMPEG_EXE,
            before_options="-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
        )
        vc.play(discord.PCMVolumeTransformer(src, volume=0.5))

    # ─ Обновляем глобальное состояние ───────────────────────────────
    PLAYING_STATE.clear()
    PLAYING_STATE.title     = track["title"]
    PLAYING_STATE.src_url   = track["url"]
    PLAYING_STATE.thumb_url = f"https://i.ytimg.com/vi/{info['id']}/hqdefault.jpg"
    PLAYING_STATE.duration  = info.get("duration", 0)
    PLAYING_STATE.start_time = time.time()

    # заставляем GUI подгрузить новую картинку
    PLAYING_STATE.preview_loaded = None
    PLAYING_STATE.preview_loader_started = False



async def pause_toggle() -> None:
    if not bot.voice_clients:
        return
    vc = bot.voice_clients[0]
    if vc.is_playing():
        vc.pause()
        PLAYING_STATE.paused = True
        PLAYING_STATE.pause_at = time.time()
    elif vc.is_paused():
        vc.resume()
        # корректируем стартовое время, чтобы elapsed шёл непрерывно
        PLAYING_STATE.start_time += time.time() - PLAYING_STATE.pause_at
        PLAYING_STATE.paused = False


async def leave_voice() -> None:
    if bot.voice_clients:
        await bot.voice_clients[0].disconnect()
        PLAYING_STATE.clear()


# ---------------------------------------------------------------------------
# Запуск клиента (функция для main.py)
# ---------------------------------------------------------------------------


def run_discord_bot() -> None:  # noqa: D401 — imperative mood OK
    """Выполняется в отдельном потоке, запускает клиент в BOT_LOOP."""

    asyncio.set_event_loop(BOT_LOOP)

    async def _runner():
        try:
            await bot.start(DISCORD_TOKEN)
        except Exception as exc:  # noqa: BLE001
            print(f"[ERR] Discord client stopped: {exc}")

    BOT_LOOP.run_until_complete(_runner())
