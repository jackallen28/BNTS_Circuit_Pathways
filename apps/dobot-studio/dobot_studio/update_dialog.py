"""The Check for updates window."""
from queue import Empty, SimpleQueue
from threading import Thread
import tkinter as tk

from .theme import BORDER, DARK, GREEN, MUTED, PANEL, PURPLE, RED
from .updater import Updater

AMBER = "#8a5a00"


class UpdateDialog:
    def __init__(self, studio, updater=None):
        self.studio = studio
        self.updater = updater or Updater(studio.app_folder)
        self.results = SimpleQueue()
        self.working = None            # "check" or "update" while a job runs
        self.status = None
        self.result = None
        self.version = tk.StringVar()
        self.message = tk.StringVar()
        window = self.window = tk.Toplevel(studio.root, bg=PANEL, padx=16, pady=12)
        window.title("Check for updates")
        window.transient(studio.root)
        window.resizable(False, False)
        window.protocol("WM_DELETE_WINDOW", self.close)
        window.bind("<Escape>", lambda _event: self.close())
        self._build()
        window.update_idletasks()
        x = studio.root.winfo_rootx() + max(10, (studio.root.winfo_width() - window.winfo_reqwidth()) // 2)
        y = studio.root.winfo_rooty() + max(10, (studio.root.winfo_height() - window.winfo_reqheight()) // 3)
        window.geometry(f"+{x}+{y}")
        window.after(60, self._poll)
        self.check()

    def _build(self):
        ui = self.studio
        header = tk.Frame(self.window, bg="#dcebf7", padx=12, pady=8)
        header.pack(fill="x")
        ui._label(header, "Dobot Studio updates", size=15, weight="bold", fg=PURPLE, bg="#dcebf7").pack(anchor="w")
        ui._label(header, textvariable=self.version, size=9, fg=MUTED, bg="#dcebf7").pack(anchor="w")
        self.message_label = ui._label(self.window, textvariable=self.message, size=10, weight="bold",
                                       wraplength=470, justify="left")
        self.message_label.pack(fill="x", pady=(10, 4))
        self.news_title = ui._label(self.window, "What is new", size=9, fg=MUTED)
        self.news = tk.Listbox(self.window, height=6, width=64, activestyle="none", borderwidth=0,
                               highlightthickness=1, highlightbackground=BORDER, fg=DARK, bg="#ffffff",
                               font=ui.theme.font(9), selectbackground="#ffffff", selectforeground=DARK)
        self.notes = ui._label(self.window, size=9, fg=AMBER, wraplength=470, justify="left")
        self.buttons = tk.Frame(self.window, bg=PANEL)
        self.buttons.pack(side="bottom", fill="x", pady=(12, 0))
        self.close_button = ui._button(self.buttons, "Close", self.close)
        self.close_button.pack(side="right")
        self.restart_button = ui._button(self.buttons, "Restart now", self.restart, "Purple")
        self.restart_button.pack(side="right", padx=(0, 6), ipadx=8)
        self.update_button = ui._button(self.buttons, "Update now", self.update, "Purple")
        self.update_button.pack(side="right", padx=(0, 6), ipadx=8)
        self.check_button = ui._button(self.buttons, "Check again", self.check)
        self.check_button.pack(side="right", padx=(0, 6))
        self._refresh()

    # ---- jobs run off the screen's thread, so it never freezes
    def check(self):
        if self.working:
            return
        self.working, self.result = "check", None
        self.message.set("Checking GitHub…")
        self._refresh()
        Thread(target=lambda: self.results.put(("check", self.updater.check())), daemon=True, name="update-check").start()

    def update(self):
        if self.working or not self.status or self.status.state != "available" or not self._idle():
            return
        self.working = "update"
        self.message.set("Updating… this can take a few minutes if new packages are needed." if self.status.requirements_changed
                         else "Updating…")
        self._refresh()
        Thread(target=lambda: self.results.put(("update", self.updater.update())), daemon=True, name="update").start()

    def _poll(self):
        if not self.window.winfo_exists():
            return
        try:
            job, value = self.results.get_nowait()
        except Empty:
            self.window.after(100, self._poll)
            return
        self.working = None
        if job == "check":
            self.status = value
            self.version.set(("Installed:  " + value.version) if value.version else "")
        else:
            self.result = value
            self.status = None
        self._refresh()
        self.window.after(100, self._poll)

    # ---- what the studio is doing decides what is safe
    def _idle(self):
        return not self.studio.busy and not self.studio.armed and not self.studio.closing

    def restart(self):
        if self.result and self.result.restart and self._idle():
            self.window.destroy()
            self.studio.restart()

    def close(self):
        if self.working:
            return
        self.studio.update_dialog = None
        self.window.destroy()

    def _refresh(self):
        ui, status, result = self.studio, self.status, self.result
        colour = MUTED
        listed, notes = (), ""
        if self.working is None:
            if result is not None:
                self.message.set(result.message)
                colour = GREEN if result.ok else RED
                notes = " ".join(result.notes)
            elif status is not None:
                self.message.set(status.message)
                colour = {"current": GREEN, "available": PURPLE, "blocked": AMBER, "error": RED,
                          "unsupported": AMBER}[status.state]
                listed = status.incoming if status.state in ("available", "blocked") else ()
        if self.version.get() == "":
            try:
                known = self.updater.version()
            except Exception:
                known = ""
            self.version.set(("Installed:  " + known) if known else "")
        self.message_label.configure(fg=colour)
        self.notes.configure(text=notes)
        self.news.delete(0, "end")
        for subject in listed:
            self.news.insert("end", "•  " + subject)
        for widget in (self.news_title, self.news, self.notes):
            widget.pack_forget()
        if listed:
            self.news_title.pack(anchor="w", pady=(4, 2), after=self.message_label)
            self.news.pack(fill="x", after=self.news_title)
        if notes:
            self.notes.pack(fill="x", pady=(6, 0))
        free = self.working is None
        ui._set_button(self.check_button, free)
        ui._set_button(self.update_button, free and status is not None and status.state == "available" and self._idle())
        ui._set_button(self.restart_button, free and result is not None and result.restart and self._idle())
        ui._set_button(self.close_button, free)
        if free and status is not None and status.state == "available" and not self._idle():
            self.message.set(status.message + " Stop what the arm is doing first.")
