"""main.py — точка входа Discord-музыкального бота."""

from __future__ import annotations

import logging
import threading
from pathlib import Path

import discord_client as dc          # run_discord_bot(), BOT_LOOP, …
from gui import MusicGUI

# ---------------------------------------------------------------------------
# базовая настройка логов
# ---------------------------------------------------------------------------

LOG_PATH = Path("bot.log")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOG_PATH, mode="w", encoding="utf8"),
    ],
)
logger = logging.getLogger("main")


# ---------------------------------------------------------------------------
# вспомогательная обёртка для запуска бота в отдельном потоке
# ---------------------------------------------------------------------------

def _run_discord_bot() -> None:
    """Стартует discord-клиент; работает до выключения программы."""
    try:
        dc.run_discord_bot()
    except Exception:                        # noqa: BLE001 — логируем всё
        logger.exception("Discord bot crashed")


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> None:
    logger.info("starting Discord bot thread")

    # Discord-клиент — в фоновом daemon-потоке
    threading.Thread(
        target=_run_discord_bot,
        name="DiscordBotThread",
        daemon=True,
    ).start()

    # Tk-GUI — в главном потоке
    MusicGUI().mainloop()


# ---------------------------------------------------------------------------

if __name__ == "__main__":
    main()
