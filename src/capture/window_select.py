# src/capture/window_select.py
from dataclasses import dataclass
from typing import List, Optional, Dict

try:
    import win32gui
except Exception:
    win32gui = None  # pywin32 non installé → pas de sélection fenêtre

@dataclass
class Candidate:
    hwnd: int
    title: str
    rect: Dict[str, int]   # {left, top, width, height}
    room: str
    area: int

ROOM_PATTERNS = {
    "winamax": ["Winamax"],
    "pmu":     ["PMU"],
}
EXCLUDE_TITLE = ["Lobby"]

def _client_rect(hwnd) -> Optional[Dict[str,int]]:
    try:
        cx, cy, cw, ch = win32gui.GetClientRect(hwnd)
        sx, sy = win32gui.ClientToScreen(hwnd, (0, 0))
        L, T, W, H = sx, sy, cw, ch
        if W <= 0 or H <= 0: return None
        if W < 400 or H < 300: return None  # filtre fenêtres trop petites
        return {"left": int(L), "top": int(T), "width": int(W), "height": int(H)}
    except Exception:
        return None

def _match_room(title: str) -> Optional[str]:
    t = (title or "").lower()
    for room, pats in ROOM_PATTERNS.items():
        if any(p.lower() in t for p in pats):
            return room
    return None

def list_poker_windows() -> List[Candidate]:
    if not win32gui:
        return []
    out: List[Candidate] = []

    def _enum(hwnd, _):
        if not win32gui.IsWindowVisible(hwnd): return
        title = win32gui.GetWindowText(hwnd) or ""
        if not title.strip(): return
        if any(k.lower() in title.lower() for k in EXCLUDE_TITLE):
            return
        room = _match_room(title)
        if not room: return
        rect = _client_rect(hwnd)
        if not rect: return
        area = rect["width"] * rect["height"]
        out.append(Candidate(hwnd=hwnd, title=title, rect=rect, room=room, area=area))

    win32gui.EnumWindows(_enum, None)
    # dédoublonnage + tri par surface décroissante
    uniq, seen = [], set()
    for c in out:
        if c.hwnd in seen: continue
        seen.add(c.hwnd); uniq.append(c)
    uniq.sort(key=lambda c: c.area, reverse=True)
    return uniq

def get_foreground_hwnd() -> Optional[int]:
    try:
        return win32gui.GetForegroundWindow() if win32gui else None
    except Exception:
        return None

def pick_primary(cands: List[Candidate]) -> Optional[Candidate]:
    if not cands: return None
    fg = get_foreground_hwnd()
    for c in cands:
        if fg and c.hwnd == fg:
            return c
    return cands[0]
