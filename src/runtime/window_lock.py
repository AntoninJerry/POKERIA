# src/runtime/window_lock.py
import os
from typing import Optional, Dict, List
from dataclasses import dataclass
from src.capture.window_select import list_poker_windows, pick_primary, Candidate

try:
    import win32gui
except Exception:
    win32gui = None

@dataclass
class Status:
    room: str
    title: str
    locked: bool

class WindowLock:
    def __init__(self):
        self.locked: bool = False
        self.cands: List[Candidate] = []
        self.idx: int = 0
        self.cur: Optional[Candidate] = None

    def refresh(self):
        self.cands = list_poker_windows()
        if self.locked and self.cur:
            still = [c for c in self.cands if c.hwnd == self.cur.hwnd]
            if still:
                self.cur = still[0]
                return
            self.locked = False
            self.cur = None
        if not self.locked:
            self.cur = pick_primary(self.cands)

    def cycle(self):
        self.refresh()
        if not self.cands:
            self.cur = None
            return None
        self.idx = (self.idx + 1) % len(self.cands)
        self.cur = self.cands[self.idx]
        self.locked = False
        return self.cur

    def toggle_lock(self):
        if not self.cur:
            self.refresh()
        self.locked = not self.locked
        return self.locked

    def get_rect(self) -> Optional[Dict[str,int]]:
        if os.getenv("POKERIA_WINDOWED","0") != "1":
            return None
        if self.locked and self.cur:
            return self.cur.rect
        self.refresh()
        return self.cur.rect if self.cur else None

    def get_status(self) -> Status:
        if self.cur:
            return Status(room=self.cur.room, title=self.cur.title, locked=self.locked)
        return Status(room="unknown", title="(none)", locked=self.locked)
    
    def is_minimized(self) -> bool:
        if not win32gui or not self.cur:
            return False
        try:
            return win32gui.IsIconic(self.cur.hwnd) == 1
        except Exception:
            return False

    def is_foreground(self) -> bool:
        if not win32gui or not self.cur:
            return False
        try:
            fg = win32gui.GetForegroundWindow()
            return fg == self.cur.hwnd
        except Exception:
            return False

LOCK = WindowLock()
