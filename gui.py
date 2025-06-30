"""gui.py – полный GUI-файл Discord-музыкального бота.

● Встроенные формы справа:
   • “＋ / ✎” под списком плейлистов выводят форму редактирования плейлиста
     (одно поле «Название» + Save/Cancel).
   • “＋ / ✎” под списком треков выводят форму трека (URL • Название • Плейлист).
● Обе формы появляются под индикатором 🔊/🔇, ничего не перекрывают
  и прячутся по Cancel/Save или Esc.
"""

from __future__ import annotations

import asyncio
import time
import logging
import platform
import random
import threading
import tkinter as tk
from io import BytesIO
from pathlib import Path
from tkinter import messagebox, simpledialog, ttk
from typing import Any, Dict, List, Literal, Optional

import requests
from PIL import Image, ImageTk

from cache_utils import thumb_from_disk
from config import ICON_H, ICON_W, PLAYLIST_FILE, PREVIEW_H, PREVIEW_W
from discord_client import ensure_join, leave_voice, pause_toggle, start_playback
from gui_widgets import AutoScrollbar
from playlist_manager import PlaylistManager
from utils import fmt
from youtube_utils import download_thumbnail, ytdlp_info, youtube_id

# -----------------------------------------------------------------------
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

GAP = 20
MODE_BTN_W = 5
MODE_FONT = ("Segoe UI Emoji", 12)


class MusicGUI(tk.Tk):
    # -------------- property -------------------------------------------
    @property
    def playlists(self) -> Dict[str, List[Dict[str, Any]]]:
        return self.pm.data

    # -------------- init ------------------------------------------------
    def __init__(self) -> None:
        super().__init__()
        self.title("Discord Music Bot")
        self.geometry("1080x720")
        self.minsize(920, 640)

        # manager
        self.pm = PlaylistManager(Path(PLAYLIST_FILE))

        sty = ttk.Style(self)
        sty.configure("Treeview", rowheight=ICON_H + 4)
        sel_bg = sty.lookup("Treeview", "selectbackground") or "#3399ff"
        sty.configure("Mode.TButton", font=MODE_FONT, width=MODE_BTN_W, padding=2)
        sty.map(
            "Mode.TButton",
            foreground=[("selected", "blue")],
            relief=[("selected", "sunken")],
        )

        # layout
        self.columnconfigure(0, weight=0, minsize=260)
        self.columnconfigure(1, weight=3)
        self.columnconfigure(2, weight=0, minsize=PREVIEW_W)
        self.rowconfigure(0, weight=1)

        # ===== LEFT – playlists ==========================================
        left = ttk.Frame(self, padding=(6, 6, 0, 6))
        left.grid(row=0, column=0, sticky="nsew", padx=(0, GAP))
        left.columnconfigure(0, weight=1)
        left.rowconfigure(0, weight=1)

        lf = ttk.Frame(left, borderwidth=1, relief="solid")
        lf.grid(row=0, column=0, sticky="nsew")
        lf.columnconfigure(0, weight=1)
        lf.rowconfigure(0, weight=1)

        pl_scr = AutoScrollbar(lf, orient="vertical")
        pl_scr.grid(row=0, column=1, sticky="ns")

        self.pl_lb = tk.Listbox(
            lf, exportselection=False, yscrollcommand=pl_scr.set, borderwidth=0, highlightthickness=0
        )
        self.pl_lb.grid(row=0, column=0, sticky="nsew")
        pl_scr.config(command=self.pl_lb.yview)
        self.pl_lb.bind("<<ListboxSelect>>", self.refresh_tracks)

        pl_btn = ttk.Frame(left)
        pl_btn.grid(row=1, column=0, columnspan=2, pady=4, sticky="n")
        for i in range(5):
            pl_btn.columnconfigure(i, weight=1)
        for txt, cmd, col in (
            ("＋", self.pl_form_add, 0),
            ("✎", self.pl_form_edit, 1),
            ("🗑", self.pl_del, 2),
            ("▲", lambda: self.pl_move(-1), 3),
            ("▼", lambda: self.pl_move(+1), 4),
        ):
            ttk.Button(pl_btn, text=txt, width=3, command=cmd).grid(row=0, column=col, padx=1)

        # ===== CENTER – tracks ===========================================
        center = ttk.Frame(self, padding=6)
        center.grid(row=0, column=1, sticky="nsew", padx=(0, GAP))
        center.columnconfigure(0, weight=1)
        center.rowconfigure(0, weight=1)

        tr_scr = AutoScrollbar(center, orient="vertical")
        tr_scr.grid(row=0, column=1, sticky="ns")
        self.tr_tv = ttk.Treeview(center, show="tree", yscrollcommand=tr_scr.set)
        self.tr_tv.grid(row=0, column=0, sticky="nsew")
        tr_scr.config(command=self.tr_tv.yview)
        self.tr_tv.bind("<Double-1>", lambda *_: self.play_selected())

        tr_btn = ttk.Frame(center)
        tr_btn.grid(row=1, column=0, columnspan=2, pady=4, sticky="n")
        for i in range(5):
            tr_btn.columnconfigure(i, weight=1)
        for txt, cmd, col in (
            ("＋", self.tr_form_add, 0),
            ("✎", self.tr_form_edit, 1),
            ("🗑", self.tr_del, 2),
            ("▲", lambda: self.tr_move(-1), 3),
            ("▼", lambda: self.tr_move(+1), 4),
        ):
            ttk.Button(tr_btn, text=txt, width=3, command=cmd).grid(row=0, column=col, padx=1)

        # wheel scrolling: listbox + treeview
        def _wheel(evt, widget):
            d = evt.delta if platform.system() == "Windows" else (-120 if evt.num == 5 else 120)
            widget.yview_scroll(int(-d / 120), "units")
            return "break"

        for w in (self.pl_lb, self.tr_tv):
            for ev in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
                w.bind(ev, lambda e, w=w: _wheel(e, w))

        # ===== RIGHT – preview & controls =================================
        right = ttk.Frame(self, padding=8)
        right.grid(row=0, column=2, sticky="n")
        right.columnconfigure(0, weight=1)

        self.url_e = ttk.Entry(right, width=40)
        self.url_e.grid(row=0, column=0, sticky="ew")
        ttk.Button(right, text="Play URL", command=lambda: self.play_url(self.url_e.get().strip())).grid(
            row=1, column=0, pady=(4, 8), sticky="ew"
        )

        pv_fr = tk.Frame(right, width=PREVIEW_W, height=PREVIEW_H, bg="black")
        pv_fr.grid_propagate(False)
        pv_fr.grid(row=2, column=0, sticky="n")
        self.preview_lbl = tk.Label(pv_fr, bg="black")
        self.preview_lbl.place(relx=0.5, rely=0.5, anchor="center")

        self.now_lbl = tk.Label(right, text="—", font=("Segoe UI", 11, "bold"), cursor="hand2")
        self.now_lbl.grid(row=3, column=0, pady=(6, 4), sticky="ew")

        self.prog = ttk.Progressbar(right, length=PREVIEW_W)
        self.prog.grid(row=4, column=0, sticky="ew")

        self.time_lbl = ttk.Label(right, text="00:00 / 00:00")
        self.time_lbl.grid(row=5, column=0)

        # режимы
        self.mode_var = tk.StringVar(value="stop")
        mode_fr = ttk.Frame(right)
        mode_fr.grid(row=6, column=0, pady=4, sticky="ew")
        mode_fr.columnconfigure((0, 1, 2, 3), weight=1)
        for icon, val, col in (("🔁", "loop", 0), ("■", "stop", 1), ("⏭", "next", 2), ("🔀", "random", 3)):
            ttk.Radiobutton(mode_fr, text=icon, value=val, variable=self.mode_var, style="Mode.TButton").grid(
                row=0, column=col, padx=2, sticky="ew"
            )

        # основные кнопки
        ctrl = ttk.Frame(right)
        ctrl.grid(row=7, column=0, pady=6, sticky="ew")
        for i in range(4):
            ctrl.columnconfigure(i, weight=1)
        for txt, cmd, col in (
            ("Join", lambda: self.run_async(ensure_join()), 0),
            ("Leave", lambda: self.run_async(leave_voice()), 1),
            ("Play", self.play_selected, 2),
            ("Pause/Res", lambda: self.run_async(pause_toggle()), 3),
        ):
            ttk.Button(ctrl, text=txt, command=cmd).grid(row=0, column=col, padx=2, sticky="ew")

        self.icon = tk.Label(right, text="🔇", font=("Segoe UI", 16))
        self.icon.grid(row=8, column=0)

        # ========== TRACK FORM ============================================
        self.tr_form = ttk.Frame(right)
        self.tr_form.grid(row=9, column=0, sticky="ew", pady=(10, 0))
        self.tr_form.columnconfigure(1, weight=1)
        ttk.Label(self.tr_form, text="URL:").grid(row=0, column=0, sticky="e")
        self.tr_url = ttk.Entry(self.tr_form)
        self.tr_url.grid(row=0, column=1, sticky="ew", padx=3, pady=2)
        ttk.Label(self.tr_form, text="Title:").grid(row=1, column=0, sticky="e")
        self.tr_title = ttk.Entry(self.tr_form)
        self.tr_title.grid(row=1, column=1, sticky="ew", padx=3, pady=2)
        ttk.Label(self.tr_form, text="Playlist:").grid(row=2, column=0, sticky="e")
        self.tr_pl = ttk.Combobox(self.tr_form, state="readonly")
        self.tr_pl.grid(row=2, column=1, sticky="ew", padx=3, pady=2)
        tr_btn_fr = ttk.Frame(self.tr_form)
        tr_btn_fr.grid(row=3, column=0, columnspan=2, pady=4)
        ttk.Button(tr_btn_fr, text="Save", command=self.tr_save).grid(row=0, column=0, padx=2)
        ttk.Button(tr_btn_fr, text="Cancel", command=self.tr_hide).grid(row=0, column=1, padx=2)
        self.tr_form.grid_remove()
        self.tr_mode: Literal["add", "edit"] = "add"
        self.tr_src_pl: Optional[str] = None
        self.tr_src_idx: Optional[int] = None

        # ========== PLAYLIST FORM =========================================
        self.pl_form = ttk.Frame(right)
        self.pl_form.grid(row=10, column=0, sticky="ew", pady=(10, 0))
        self.pl_form.columnconfigure(1, weight=1)
        ttk.Label(self.pl_form, text="Name:").grid(row=0, column=0, sticky="e")
        self.pl_name = ttk.Entry(self.pl_form)
        self.pl_name.grid(row=0, column=1, sticky="ew", padx=3, pady=2)
        pl_btn_fr = ttk.Frame(self.pl_form)
        pl_btn_fr.grid(row=1, column=0, columnspan=2, pady=4)
        ttk.Button(pl_btn_fr, text="Save", command=self.pl_save).grid(row=0, column=0, padx=2)
        ttk.Button(pl_btn_fr, text="Cancel", command=self.pl_hide).grid(row=0, column=1, padx=2)
        self.pl_form.grid_remove()
        self.pl_mode: Literal["add", "edit"] = "add"
        self.pl_oldname: Optional[str] = None

        # ---------------------------------------------------------------
        self.current_track: Optional[Dict[str, Any]] = None
        self.refresh_playlist_listbox()
        self.after(500, self.tick)

    # ======== TRACK FORM METHODS =======================================
    def tr_show(
        self,
        mode: Literal["add", "edit"],
        *,
        url: str = "",
        title: str = "",
        pl_name: str = "",
        src_pl: str | None = None,
        src_idx: int | None = None,
    ):
        self.tr_mode, self.tr_src_pl, self.tr_src_idx = mode, src_pl, src_idx
        self.tr_url.delete(0, "end")
        self.tr_url.insert(0, url)
        self.tr_title.delete(0, "end")
        self.tr_title.insert(0, title or url)
        self.tr_pl["values"] = list(self.playlists)
        self.tr_pl.set(pl_name or (list(self.playlists)[0] if self.playlists else ""))
        self.tr_form.grid()
        self.tr_url.focus_set()
        self.pl_hide()  # гарантируем только одну форму на экране

    def tr_hide(self):
        self.tr_form.grid_remove()
        self.tr_src_pl = self.tr_src_idx = None

    def tr_form_add(self):
        if not self.playlists:
            messagebox.showwarning("Нет плейлистов", "Сначала создайте плейлист.")
            return
        cur_pl = (
            self.pl_lb.get(int(self.pl_lb.curselection()[0]))
            if self.pl_lb.curselection()
            else list(self.playlists)[0]
        )
        self.tr_show("add", pl_name=cur_pl)

    def tr_form_edit(self):
        ps, it = self.pl_lb.curselection(), self.tr_tv.selection()
        if not (ps and it):
            return
        pl = self.pl_lb.get(int(ps[0]))
        idx = int(it[0])
        tr = self.playlists[pl][idx]
        self.tr_show("edit", url=tr["url"], title=tr["title"], pl_name=pl, src_pl=pl, src_idx=idx)

    def tr_save(self):
        url = self.tr_url.get().strip()
        title = self.tr_title.get().strip() or url
        dest_pl = self.tr_pl.get()
        if not url or not dest_pl:
            messagebox.showwarning("Ошибка", "URL и плейлист обязательны.")
            return
        if self.tr_mode == "add":
            info = asyncio.run(ytdlp_info(url))
            vid = info["id"]
            download_thumbnail(info["thumbnail"], vid, (ICON_W, ICON_H))
            self.pm.add_track(dest_pl, {"title": title, "url": url, "vid": vid})
        else:  # edit
            if self.tr_src_pl is None or self.tr_src_idx is None:
                return
            tr = self.playlists[self.tr_src_pl][self.tr_src_idx]
            tr["title"], tr["url"] = title, url
            if dest_pl != self.tr_src_pl:
                self.pm.delete_track(self.tr_src_pl, self.tr_src_idx)
                self.pm.add_track(dest_pl, tr)
        self.save_and_refresh()
        self.tr_hide()

    # ======== PLAYLIST FORM METHODS ====================================
    def pl_show(self, mode: Literal["add", "edit"], *, name: str = "", oldname: str | None = None):
        self.pl_mode, self.pl_oldname = mode, oldname
        self.pl_name.delete(0, "end")
        self.pl_name.insert(0, name)
        self.pl_form.grid()
        self.pl_name.focus_set()
        self.tr_hide()

    def pl_hide(self):
        self.pl_form.grid_remove()
        self.pl_oldname = None

    def pl_form_add(self):
        self.pl_show("add")

    def pl_form_edit(self):
        if not self.pl_lb.curselection():
            return
        old = self.pl_lb.get(int(self.pl_lb.curselection()[0]))
        self.pl_show("edit", name=old, oldname=old)

    def pl_save(self):
        name = self.pl_name.get().strip()
        if not name:
            messagebox.showwarning("Ошибка", "Имя плейлиста не может быть пустым.")
            return
        if self.pl_mode == "add":
            if name in self.playlists:
                messagebox.showwarning("Существует", "Такой плейлист уже есть.")
                return
            self.pm.add_playlist(name)
        else:
            if self.pl_oldname and name != self.pl_oldname:
                if name in self.playlists:
                    messagebox.showwarning("Существует", "Такой плейлист уже есть.")
                    return
                self.pm.rename_playlist(self.pl_oldname, name)
        self.refresh_playlist_listbox()
        self.pl_hide()

    # ======== playlist ops =============================================
    def refresh_playlist_listbox(self):
        self.pl_lb.delete(0, "end")
        for n in self.playlists:
            self.pl_lb.insert("end", n)
        if self.playlists:
            self.pl_lb.selection_set(0)
            self.pl_lb.activate(0)
            self.refresh_tracks()
        self.tr_pl["values"] = list(self.playlists)  # обновить combobox

    def pl_del(self):
        if not self.pl_lb.curselection():
            return
        name = self.pl_lb.get(int(self.pl_lb.curselection()[0]))
        if messagebox.askyesno("Удалить", f"Удалить «{name}»?"):
            self.pm.delete_playlist(name)
            self.refresh_playlist_listbox()

    def pl_move(self, delta: int):
        if not self.pl_lb.curselection():
            return
        idx = int(self.pl_lb.curselection()[0])
        self.pm.move_playlist(idx, delta)
        self.refresh_playlist_listbox()
        new = max(0, min(len(self.playlists) - 1, idx + delta))
        self.pl_lb.selection_clear(0, "end")
        self.pl_lb.selection_set(new)
        self.pl_lb.activate(new)

    # ======== track ops ===============================================
    def save_and_refresh(self):
        self.pm.save()
        self.refresh_tracks()

    def refresh_tracks(self, *_):
        if not self.pl_lb.curselection():
            return
        pl = self.pl_lb.get(int(self.pl_lb.curselection()[0]))
        self.tr_tv.delete(*self.tr_tv.get_children())
        self.tr_tv._img = {}
        for idx, tr in enumerate(self.playlists[pl]):
            vid = tr.get("vid") or youtube_id(tr["url"])
            tr["vid"] = vid
            img = thumb_from_disk(vid)
            iid = self.tr_tv.insert("", "end", text="\u2003" + tr["title"], image=img, iid=str(idx))
            self.tr_tv._img[iid] = img

    def tr_del(self):
        ps, it = self.pl_lb.curselection(), self.tr_tv.selection()
        if not (ps and it):
            return
        pl = self.pl_lb.get(int(ps[0]))
        idx = int(it[0])
        self.pm.delete_track(pl, idx)
        self.save_and_refresh()

    def tr_move(self, delta: int):
        ps, it = self.pl_lb.curselection(), self.tr_tv.selection()
        if not (ps and it):
            return
        pl = self.pl_lb.get(int(ps[0]))
        idx = int(it[0])
        self.pm.move_track(pl, idx, delta)
        self.save_and_refresh()
        self.tr_tv.selection_set(str(max(0, min(len(self.playlists[pl]) - 1, idx + delta))))

    # ======== playback =================================================
    def selected_track(self):
        ps, it = self.pl_lb.curselection(), self.tr_tv.selection()
        if not (ps and it):
            return None
        pl = self.pl_lb.get(int(ps[0]))
        return self.playlists[pl][int(it[0])]

    def play_selected(self):
        tr = self.selected_track()
        if tr:
            self.current_track = tr
            self.run_async(start_playback(tr))

    def play_url(self, url: str):
        if url:
            tr = {"title": url, "url": url}
            self.current_track = tr
            self.run_async(start_playback(tr))

    # ======== behaviour on finish =====================================
    def on_track_end(self, st):
        mode = self.mode_var.get()
        if mode == "loop" and self.current_track:
            self.run_async(start_playback(self.current_track))
        elif mode == "next":
            if not self.pl_lb.curselection():
                return
            pl = self.pl_lb.get(int(self.pl_lb.curselection()[0]))
            tracks = self.playlists[pl]
            if tracks:
                cur = int(self.tr_tv.selection()[0]) if self.tr_tv.selection() else -1
                nxt = (cur + 1) % len(tracks)
                self.tr_tv.selection_set(str(nxt))
                self.tr_tv.focus(str(nxt))
                self.play_selected()
        elif mode == "random":
            if not self.pl_lb.curselection():
                return
            pl = self.pl_lb.get(int(self.pl_lb.curselection()[0]))
            tracks = self.playlists[pl]
            if tracks:
                idx = random.randrange(len(tracks))
                self.tr_tv.selection_set(str(idx))
                self.tr_tv.focus(str(idx))
                self.play_selected()
        else:  # stop
            from discord_client import BOT_LOOP

            async def _halt():
                if BOT_LOOP.voice_clients:
                    BOT_LOOP.voice_clients[0].stop()

            self.run_async(_halt())
            st.clear()
            self.current_track = None

    # ======== tick =====================================================
    def tick(self):
        from discord_client import PLAYING_STATE as st

        self.icon.config(text="🔊" if st.voice_connected else "🔇")
        if st.is_playing:
            elapsed = max(0, st.elapsed_seconds or 0)
            dur = st.duration
            self.now_lbl.config(text=st.title)
            self.time_lbl.config(text=f"{fmt(min(elapsed, dur) if dur else elapsed)} / {fmt(dur)}")
            self.prog.config(maximum=max(dur, 1), value=min(elapsed, dur))

            if dur and elapsed >= dur and not st.paused:
                self.on_track_end(st)
                st.paused = True
                st.pause_at = time.time()

            if st.preview_loaded:
                self.preview_lbl.config(image=st.preview_loaded)
            elif not st.preview_loader_started:
                st.preview_loader_started = True
                threading.Thread(target=self._load_preview, daemon=True).start()
        else:
            self.now_lbl.config(text="—")
            self.time_lbl.config(text="00:00 / 00:00")
            self.prog.config(value=0)
            self.preview_lbl.config(image="")

        self.after(500, self.tick)

    # ======== helpers ===================================================
    def _open_now_playing(self):
        from discord_client import PLAYING_STATE as st

        if st.src_url:
            import webbrowser

            webbrowser.open_new(st.src_url)

    def _load_preview(self):
        from discord_client import PLAYING_STATE as st
        if not st.thumb_url:
            return

        try:
            r = requests.get(st.thumb_url, timeout=15)
            r.raise_for_status()
            img = ImageTk.PhotoImage(
                Image.open(BytesIO(r.content)).resize((PREVIEW_W, PREVIEW_H))
            )
            st.preview_loaded = img
            self.preview_lbl.after(
                0, lambda: (self.preview_lbl.config(image=img), setattr(self.preview_lbl, "img", img))
            )
        except Exception as exc:
            logger.warning("preview load: %s", exc)

    def run_async(self, coro):
        from discord_client import BOT_LOOP

        fut = asyncio.run_coroutine_threadsafe(coro, BOT_LOOP)
        fut.add_done_callback(lambda f: logger.debug("Coroutine finished: %s", f.exception()))
