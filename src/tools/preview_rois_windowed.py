# src/tools/preview_rois_windowed.py
import cv2
from typing import Tuple, Any, Dict

from src.capture.screen import capture_table
from src.config.settings import load_room_config, get_table_roi, ACTIVE_ROOM

HELP = "ESC=quit  SPACE=reload YAML  g=grid  s=snapshot"

def _rect_to_tuple(rect: Any) -> Tuple[int, int, int, int]:
    if hasattr(rect, "x"):
        return int(rect.x), int(rect.y), int(rect.w), int(rect.h)
    return int(rect["left"]), int(rect["top"]), int(rect["width"]), int(rect["height"])

def _rel_to_abs(rel, W, H):
    rx, ry, rw, rh = rel
    return int(rx * W), int(ry * H), max(1, int(rw * W)), max(1, int(rh * H))

def _draw_grid(img, step=50):
    H, W = img.shape[:2]
    for x in range(0, W, step):
        cv2.line(img, (x, 0), (x, H), (200, 200, 200), 1, lineType=cv2.LINE_AA)
    for y in range(0, H, step):
        cv2.line(img, (0, y), (W, y), (200, 200, 200), 1, lineType=cv2.LINE_AA)

def _draw_rois(img_bgr, cfg: Dict):
    H, W = img_bgr.shape[:2]
    rois = cfg.get("rois_hint", {})
    for name, meta in rois.items():
        rel = meta.get("rel")
        if not rel or len(rel) != 4:
            continue
        x, y, w, h = _rel_to_abs(rel, W, H)
        cv2.rectangle(img_bgr, (x, y), (x + w, y + h), (0, 255, 255), 2, lineType=cv2.LINE_AA)
        cv2.putText(img_bgr, name, (x + 4, max(12, y - 6)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 255), 1, cv2.LINE_AA)

def main():
    print("=== PREVIEW ROIS (WINDOWED) ===")
    print(HELP)
    cfg = load_room_config(ACTIVE_ROOM)

    show_grid = True
    snap_id = 0

    while True:
        # Capture de la zone TABLE courante (fenêtrée si lock, sinon ROI du YAML)
        rect = get_table_roi(ACTIVE_ROOM)
        table = capture_table(rect)

        bgr = cv2.cvtColor(table, cv2.COLOR_RGB2BGR)
        if show_grid:
            _draw_grid(bgr, step=50)

        # Dessin des ROIs calculées à l'intérieur de la table
        _draw_rois(bgr, cfg)

        # Titre/overlay
        title = f"Room={ACTIVE_ROOM}  Size={bgr.shape[1]}x{bgr.shape[0]}  [SPACE=reload YAML, g=grid, s=snap, ESC=quit]"
        cv2.putText(bgr, title, (10, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1, cv2.LINE_AA)

        cv2.imshow("ROI Preview (WINDOWED)", bgr)
        k = cv2.waitKey(25) & 0xFF

        if k == 27:  # ESC
            break
        elif k == ord(' '):
            cfg = load_room_config(ACTIVE_ROOM)
            print("↻ YAML rechargé.")
        elif k == ord('g'):
            show_grid = not show_grid
        elif k == ord('s'):
            snap_id += 1
            out = f"roi_preview_windowed_{snap_id:02d}.png"
            cv2.imwrite(out, bgr)
            print("💾 snapshot:", out)

    cv2.destroyAllWindows()
    print("Bye.")

if __name__ == "__main__":
    main()
