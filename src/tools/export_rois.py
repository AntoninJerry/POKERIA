import cv2, time
import numpy as np
from pathlib import Path
from src.capture.screen import capture_table
from src.config.settings import get_table_roi, load_room_config, ACTIVE_ROOM
from src.utils.geometry import Rect

def rel_to_abs_rect(rel, W, H) -> Rect:
    rx, ry, rw, rh = rel
    return Rect(int(rx*W), int(ry*H), max(1,int(rw*W)), max(1,int(rh*H)))

def main():
    table = capture_table(get_table_roi(ACTIVE_ROOM))  # RGB
    if table is None:
        print("❌ Pas de capture table.")
        return
    H, W = table.shape[:2]
    bgr = cv2.cvtColor(table, cv2.COLOR_RGB2BGR)

    cfg = load_room_config(ACTIVE_ROOM)
    rois = cfg.get("rois_hint", {})
    outdir = Path("assets/exports")/time.strftime("%Y%m%d_%H%M%S")
    outdir.mkdir(parents=True, exist_ok=True)

    for name, val in rois.items():
        r = rel_to_abs_rect(val["rel"], W, H)
        crop = bgr[r.y:r.y+r.h, r.x:r.x+r.w].copy()
        cv2.imwrite(str(outdir/f"{name}.png"), crop)
    print(f"✅ Exports: {outdir}")

if __name__ == "__main__":
    main()
