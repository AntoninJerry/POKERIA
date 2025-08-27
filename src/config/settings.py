from dataclasses import dataclass
from pathlib import Path
import yaml
from typing import Dict, Any, Optional
from src.utils.geometry import Rect
import os

ROOT = Path(__file__).resolve().parents[2]
ROOMS_DIR = ROOT / "src" / "config" / "rooms"

ACTIVE_ROOM = "winamax"  # changeable plus tard via CLI/ENV

@dataclass
class TableROI:
    left: int = 100
    top: int = 100
    width: int = 1280
    height: int = 720

def room_yaml_path(room: Optional[str] = None) -> Path:
    r = room or ACTIVE_ROOM
    ROOMS_DIR.mkdir(parents=True, exist_ok=True)
    return ROOMS_DIR / f"{r}.yaml"

def load_room_config(room: Optional[str] = None) -> Dict[str, Any]:
    p = room_yaml_path(room)
    if not p.exists():
        cfg = {
            "room": room or ACTIVE_ROOM,
            "dpi_scale": 1.0,
            "table_roi": TableROI().__dict__,
            "rois_hint": {}
        }
        p.write_text(yaml.safe_dump(cfg, sort_keys=False), encoding="utf-8")
        return cfg
    return yaml.safe_load(p.read_text(encoding="utf-8"))

def save_room_config(data: Dict[str, Any], room: Optional[str] = None) -> None:
    p = room_yaml_path(room)
    p.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")

def get_table_roi(room: Optional[str] = None) -> Rect:
    # Mode fenêtré/locké → rect client Win32
    if os.getenv("POKERIA_WINDOWED", "0") == "1":
        try:
            from src.runtime.window_lock import LOCK
            r = LOCK.get_rect()
            if r:
                return Rect(x=int(r["left"]), y=int(r["top"]), w=int(r["width"]), h=int(r["height"]))
        except Exception:
            pass  # fallback YAML si erreur

    # Fallback profil YAML (plein écran ou pas de lock)
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
