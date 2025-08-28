import cv2, os, time
import numpy as np
from pathlib import Path
from src.capture.screen import capture_table
from src.config.settings import get_table_roi, load_room_config, ACTIVE_ROOM
from src.utils.geometry import Rect

os.environ["POKERIA_WINDOWED"] = "0"

def rel_to_abs_rect(rel, W, H) -> Rect:
    rx, ry, rw, rh = rel
    x = int(rx * W); y = int(ry * H)
    w = max(1, int(rw * W)); h = max(1, int(rh * H))
    return Rect(x, y, w, h)

def draw_overlay(img, rois_hint):
    out = img.copy()
    H, W = out.shape[:2]
    for name, val in rois_hint.items():
        r = rel_to_abs_rect(val["rel"], W, H)
        cv2.rectangle(out, (r.x, r.y), (r.x+r.w, r.y+r.h), (0,255,0), 2)
        cv2.putText(out, name, (r.x+4, r.y+16), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255,255,255), 1, cv2.LINE_AA)
    return out

def main():
    os.environ["POKERIA_WINDOWED"] = "0"
    cfg = load_room_config(ACTIVE_ROOM)

    cv2.namedWindow("ROIs Overlay - press R to reload, S to save, ESC to quit", cv2.WINDOW_NORMAL)
    while True:
        table_rect = get_table_roi(ACTIVE_ROOM)
        table_img = capture_table(table_rect)  # RGB frais à chaque tour
        if table_img is None:
            print("❌ Impossible de capturer la table."); break

        img_bgr = cv2.cvtColor(table_img, cv2.COLOR_RGB2BGR)
        rois_hint = cfg.get("rois_hint", {})
        overlay = draw_overlay(img_bgr, rois_hint)
        cv2.imshow("ROIs Overlay - press R to reload, S to save, ESC to quit", overlay)

        k = cv2.waitKey(60) & 0xFF
        if k == 27:  # ESC
            break
        elif k == ord('r'):   # recharge YAML (et prochaine itération recapture)
            cfg = load_room_config(ACTIVE_ROOM)
        elif k == ord('s'):
            outdir = Path("assets/exports")/time.strftime("%Y%m%d_%H%M%S")
            outdir.mkdir(parents=True, exist_ok=True)
            cv2.imwrite(str(outdir/"overlay.png"), overlay)
            print(f"💾 overlay sauvegardé: {outdir/'overlay.png'}")

    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
