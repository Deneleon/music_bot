"""utils.py
===========
Небольшие универсальные функции, не зависящие от остальных модулей.
"""
from __future__ import annotations

from datetime import timedelta

__all__ = ["fmt"]


def fmt(seconds: int | float) -> str:  # noqa: D401 — imperative mood OK
    """Форматировать секунды в "MM:SS" или "H:MM:SS".

    • Подрезает отрицательные значения до 0.
    • Преобразует float → int, чтобы не мельтешили миллисекунды.
    """
    seconds = max(0, int(seconds))
    td = timedelta(seconds=seconds)
    h, remainder = divmod(td.seconds, 3600)
    m, s = divmod(remainder, 60)
    if td.days or h:
        return f"{td.days * 24 + h}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"
