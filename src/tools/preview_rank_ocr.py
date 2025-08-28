# src/tools/preview_rank_ocr.py
import os, time
from pathlib import Path
from typing import List, Tuple, Optional
import cv2

# Forcer le mode plein écran pour utiliser le YAML fullscreen
os.environ["POKERIA_WINDOWED"] = "0"

from src.config.settings import load_room_config, get_table_roi, ACTIVE_ROOM
from src.capture.screen import capture_table
from src.ocr.engine_singleton import get_engine
from src.ocr.cards import _roi_from_rel, _read_rank

CARDS: List[str] = [
    "hero_card_left", "hero_card_right",
    "board_card_1", "board_card_2", "board_card_3", "board_card_4", "board_card_5"
]

WIN_TITLE = "RANK preview [FS] — R: recapture  O: toggle OCR  S: save  ESC: quit"
EXPORT_DIR = Path("assets/exports"); EXPORT_DIR.mkdir(parents=True, exist_ok=True)

def rel_to_abs(rect_rel, W: int, H: int) -> Tuple[int, int, int, int]:
    rx, ry, rw, rh = rect_rel
    x = int(rx * W); y = int(ry * H)
    w = max(1, int(rw * W)); h = max(1, int(rh * H))
    return x, y, w, h

def main():
    cfg = load_room_config(ACTIVE_ROOM)
    eng = get_engine()

    cv2.namedWindow(WIN_TITLE, cv2.WINDOW_NORMAL)
    ocr_on = True
    last_save = 0.0

    while True:
        # Recapture en boucle pour suivre un éventuel déplacement/redimensionnement
        table_rect = get_table_roi(ACTIVE_ROOM)
        rgb = capture_table(table_rect)  # RGB
        if rgb is None:
            print("❌ Impossible de capturer la table.")
            break

        H, W = rgb.shape[:2]
        bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)

        rois = cfg.get("rois_hint", {}) or {}
        for name in CARDS:
            node = rois.get(name, {}) or {}
            rel = node.get("rel"); rr = node.get("rank_rel")
            if not rel or not rr:
                continue

            # Cadre carte (jaune)
            x, y, w, h = rel_to_abs(rel, W, H)
            cv2.rectangle(bgr, (x, y), (x + w, y + h), (0, 255, 255), 2)

            # Cadre rank (vert)
            rx, ry, rw, rh = rr
            gx1, gy1 = x + int(rx * w), y + int(ry * h)
            gx2, gy2 = x + int((rx + rw) * w), y + int((ry + rh) * h)
            cv2.rectangle(bgr, (gx1, gy1), (gx2, gy2), (0, 255, 0), 2)

            code, conf = None, 0.0
            if ocr_on:
                try:
                    # Patch relatif à la carte
                    card_rgb = rgb[y:y + h, x:x + w]
                    patch = _roi_from_rel(card_rgb, rr)  # RGB
                    code, conf, _meta = _read_rank(eng, patch)
                except Exception as e:
                    code, conf = None, 0.0

            label = f"{name}: {code or '?'} {conf:.2f}"
            ty = y - 6 if y > 14 else y + h + 14
            cv2.putText(bgr, label, (x + 3, ty), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 2)

        # Bandeau info
        top = f"room={ACTIVE_ROOM}  size={W}x{H}  OCR={'ON' if ocr_on else 'OFF'}"
        cv2.putText(bgr, top, (10, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255,255,255), 2)

        cv2.imshow(WIN_TITLE, bgr)
        k = cv2.waitKey(60) & 0xFF

        if k == 27:  # ESC
            break
        elif k == ord('o'):
            ocr_on = not ocr_on
        elif k == ord('r'):
            cfg = load_room_config(ACTIVE_ROOM)  # recharger YAML si modifié
        elif k == ord('s'):
            now = time.time()
            if now - last_save > 0.5:
                out = EXPORT_DIR / f"rank_preview_{time.strftime('%Y%m%d_%H%M%S')}.png"
                cv2.imwrite(str(out), bgr)
                print(f"💾 saved {out}")
                last_save = now

    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
