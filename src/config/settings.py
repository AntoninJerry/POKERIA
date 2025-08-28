from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Any, Optional
import os, yaml

from src.utils.geometry import Rect

# ──────────────────────────────────────────────────────────────────────────────
# Emplacements des YAML "rooms"
#   - priorité à assets/rooms (si présent)
#   - fallback à src/config/rooms
# ──────────────────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parents[2]
CANDIDATE_DIRS = [
    ROOT / "assets" / "rooms",
    ROOT / "src" / "config" / "rooms",
]

def _pick_rooms_dir() -> Path:
    for d in CANDIDATE_DIRS:
        if d.exists():
            return d
    # si aucun n'existe encore → on crée le premier
    d = CANDIDATE_DIRS[0]
    d.mkdir(parents=True, exist_ok=True)
    return d

ROOMS_DIR = _pick_rooms_dir()

# Room active (plein écran). Surchargable via env: POKERIA_ROOM=winamax
ACTIVE_ROOM = os.getenv("POKERIA_ROOM", "winamax")

@dataclass
class TableROI:
    left: int = 100
    top: int = 100
    width: int = 1280
    height: int = 720

def room_yaml_path(room: Optional[str] = None) -> Path:
    r = room or ACTIVE_ROOM
    return ROOMS_DIR / f"{r}.yaml"

def load_room_config(room: Optional[str] = None) -> Dict[str, Any]:
    """
    Charge le YAML de la room (plein écran). Si manquant, écrit un squelette minimal.
    """
    p = room_yaml_path(room)
    if not p.exists():
        cfg = {
            "room": room or ACTIVE_ROOM,
            "dpi_scale": 1.0,
            "table_roi": TableROI().__dict__,
            "rois_hint": {}
        }
        p.write_text(yaml.safe_dump(cfg, sort_keys=False, allow_unicode=True), encoding="utf-8")
        return cfg
    return yaml.safe_load(p.read_text(encoding="utf-8"))

def save_room_config(data: Dict[str, Any], room: Optional[str] = None) -> None:
    p = room_yaml_path(room)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")

def get_table_roi(room: Optional[str] = None) -> Rect:
    """
    PLEIN ÉCRAN UNIQUEMENT :
    Lit systématiquement le `table_roi` du YAML (aucun code fenêtré/Win32 ici).
    """
    cfg = load_room_config(room)
    t = cfg.get("table_roi", {})
    return Rect(
        x=int(t.get("left", 100)),
        y=int(t.get("top", 100)),
        w=int(t.get("width", 1280)),
        h=int(t.get("height", 720)),
    )

def set_table_roi(rect: Rect, room: Optional[str] = None) -> None:
    cfg = load_room_config(room)
    cfg["table_roi"] = {
        "left": int(rect.x),
        "top": int(rect.y),
        "width": int(rect.w),
        "height": int(rect.h),
    }
    save_room_config(cfg, room)
