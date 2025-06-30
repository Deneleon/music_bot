"""gui_widgets.py
================
Переиспользуемые виджеты для графического интерфейса.

• **Splash**  — простое модальное окно с ProgressBar, используемое при
  синхронизации кеша.
• **AutoScrollbar** — скроллбар, который автоматически скрывается, когда
  содержимое полностью помещается в виджет.

Оба класса вынесены в отдельный модуль, чтобы держать `gui.py` компактным и
читаемым.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

__all__ = ["Splash", "AutoScrollbar"]

# ---------------------------------------------------------------------------
# Splash — модальное окно с прогрессбаром
# ---------------------------------------------------------------------------


class Splash(tk.Toplevel):
    """Неблокирующее модальное окно, информирующее о ходе работы."""

    def __init__(self, total: int = 1) -> None:  # noqa: D401 — imperative mood OK
        super().__init__()

        self.title("Подготовка…")
        self.resizable(False, False)
        self.protocol("WM_DELETE_WINDOW", lambda: None)  # нельзя закрыть вручную

        # --- UI ----------------------------------------------------------------
        self.prog = ttk.Progressbar(self, length=320, maximum=max(total, 1))
        self.lbl = ttk.Label(self, text="Проверка кеша…")

        self.prog.pack(padx=20, pady=(20, 6))
        self.lbl.pack(padx=20, pady=(0, 20))

        # --- Центрируем окно ----------------------------------------------------
        self.update_idletasks()
        w, h = self.winfo_width(), self.winfo_height()
        self.geometry(
            f"{w}x{h}+{self.winfo_screenwidth() // 2 - w // 2}+{self.winfo_screenheight() // 2 - h // 2}"
        )

    # ----------------------------------------------------------------------
    # API
    # ----------------------------------------------------------------------

    def step(self, msg: str = "") -> None:
        """Увеличить полоску на 1 единицу и (опц.) обновить текст."""
        self.prog["value"] = float(self.prog["value"]) + 1
        if msg:
            self.lbl.config(text=msg)
        self.update_idletasks()


# ---------------------------------------------------------------------------
# AutoScrollbar — скрывается, когда не нужен
# ---------------------------------------------------------------------------


class AutoScrollbar(ttk.Scrollbar):
    """Scrollbar, который прячется, если полоса прокрутки не требуется."""

    # — tk/ttk Scrollbar interface override --------------------------------
    def set(self, lo: float, hi: float) -> None:  # type: ignore[override]
        lo_f, hi_f = float(lo), float(hi)
        if lo_f <= 0.0 and hi_f >= 1.0:
            self.grid_remove()
        else:
            self.grid()
        super().set(lo, hi)

    # Отключаем pack/place, чтобы нечаянно не использовали не тот layout ----
    def pack(self, *args, **kwargs):  # noqa: D401,E501 – intentional override to disable
        raise RuntimeError("Use .grid() with AutoScrollbar, pack() запрещён.")

    def place(self, *args, **kwargs):  # noqa: D401,E501 – intentional override to disable
        raise RuntimeError("Use .grid() with AutoScrollbar, place() запрещён.")
