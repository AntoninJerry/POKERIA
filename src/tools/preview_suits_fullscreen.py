# src/tools/preview_suits_fullscreen.py
import os, cv2, numpy as np
from typing import Tuple, Any, Dict
from src.capture.screen import capture_table
from src.config.settings import load_room_config, get_table_roi, ACTIVE_ROOM
from src.ocr.suit_shape import SuitHu

HELP = "ESC=quit  SPACE=reload YAML  g=grid  s=snapshot"

# --- helpers identiques à ton preview fullscreen ---
def rect_to_tuple(rect: Any) -> Tuple[int, int, int, int]:
    if hasattr(rect, "x"):   # dataclass Rect
        return int(rect.x), int(rect.y), int(rect.w), int(rect.h)
    x = int(getattr(rect, "left", getattr(rect, "x", rect["left"] if "left" in rect else rect["x"])))
    y = int(getattr(rect, "top",  getattr(rect, "y", rect["top"]  if "top"  in rect else rect["y"])))
    w = int(getattr(rect, "width",getattr(rect, "w", rect["width"]if "width"in rect else rect["w"])))
    h = int(getattr(rect, "height",getattr(rect,"h", rect["height"]if "height"in rect else rect["h"])))
    return x, y, w, h

def rel_to_abs(rel, W, H) -> Tuple[int, int, int, int]:
    rx, ry, rw, rh = rel
    x = int(rx * W); y = int(ry * H)
    w = max(1, int(rw * W)); h = max(1, int(rh * H))
    # clamp soft
    x = max(0, min(x, W-1)); y = max(0, min(y, H-1))
    w = max(1, min(w, W-x)); h = max(1, min(h, H-y))
    return x, y, w, h

def suit_rel_to_abs(srel, roi_abs):
    rx, ry, rw, rh = srel
    x, y, w, h = roi_abs
    sx = int(x + rx * w); sy = int(y + ry * h)
    sw = max(1, int(rw * w)); sh = max(1, int(rh * h))
    # clamp soft
    sx = max(0, min(sx, x + w - 1)); sy = max(0, min(sy, y + h - 1))
    sw = max(1, min(sw, x + w - sx)); sh = max(1, min(sh, y + h - sy))
    return sx, sy, sw, sh

def draw_grid(img, step=50):
    H, W = img.shape[:2]
    for x in range(0, W, step):
        cv2.line(img, (x, 0), (x, H), (60, 60, 60), 1, cv2.LINE_AA)
    for y in range(0, H, step):
        cv2.line(img, (0, y), (W, y), (60, 60, 60), 1, cv2.LINE_AA)

def color_for(name: str):
    n = name.lower()
    if "hero_card" in n:  return (0,255,255)   # jaune
    if "board_card" in n: return (255,0,255)   # magenta
    return (200,200,200)

def suit_color_hint(rgb):
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    m1 = cv2.inRange(hsv, (0,70,40), (10,255,255))
    m2 = cv2.inRange(hsv, (170,70,40), (180,255,255))
    red_ratio = float(np.count_nonzero(m1 | m2)) / (rgb.shape[0]*rgb.shape[1] + 1e-6)
    return "red" if red_ratio > 0.04 else "black"

def main():
    print("=== PREVIEW SUITS (FULLSCREEN / YAML) ===")
    print(HELP)

    # 🔒 Forcer le mode plein écran comme ton autre script
    os.environ["POKERIA_WINDOWED"] = "0"

    clf = SuitHu()
    cfg = load_room_config(ACTIVE_ROOM)
    show_grid = False
    snap_id = 0

    cv2.namedWindow("SUITS (FULLSCREEN)", cv2.WINDOW_NORMAL)

    # Ordre de cartes
    cards = ["hero_card_left","hero_card_right",
             "board_card_1","board_card_2","board_card_3","board_card_4","board_card_5"]

    while True:
        rect_obj = get_table_roi(ACTIVE_ROOM)
        _, _, w0, h0 = rect_to_tuple(rect_obj)

        table = capture_table(rect_obj)
        H, W = table.shape[:2]
        bgr = cv2.cvtColor(table, cv2.COLOR_RGB2BGR)

        # cadre global + grille optionnelle
        cv2.rectangle(bgr, (1,1), (W-2, H-2), (0,0,255), 1)
        if show_grid:
            draw_grid(bgr, 50)

        rois: Dict = cfg.get("rois_hint", {}) or {}
        for name in cards:
            node = rois.get(name)
            if not node: continue

            # cadre carte
            rel = node.get("rel")
            if not rel: continue
            x, y, w, h = rel_to_abs(rel, W, H)
            cv2.rectangle(bgr, (x, y), (x+w, y+h), color_for(name), 2, cv2.LINE_AA)
            cv2.putText(bgr, name, (x+3, y+16), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color_for(name), 1, cv2.LINE_AA)

            # suit_rel (obligatoire pour cette vue)
            srel = node.get("suit_rel")
            if not srel: 
                cv2.putText(bgr, "suit_rel MISSING", (x+6, y+h-8), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0,200,255), 1, cv2.LINE_AA)
                continue

            sx, sy, sw, sh = suit_rel_to_abs(srel, (x, y, w, h))
            cv2.rectangle(bgr, (sx, sy), (sx+sw, sy+sh), (0,255,0), 2, cv2.LINE_AA)

            patch = table[sy:sy+sh, sx:sx+sw].copy()
            hint = suit_color_hint(patch)

            # classification (sécurisée)
            lab, conf = None, 0.0
            try:
                lab, conf, _ = clf.classify(patch, color_hint=hint)
            except TypeError:
                # compat si signature différente: classify(patch) -> (lab, conf)
                tmp = clf.classify(patch)
                if isinstance(tmp, (list, tuple)) and len(tmp) >= 2:
                    lab, conf = tmp[0], float(tmp[1])
            except Exception:
                pass

            txt = f"{lab or '?'}  {conf:.2f}  ({hint})"
            cv2.putText(bgr, txt, (sx+2, sy-4 if sy>12 else sy+14),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0,255,0), 1, cv2.LINE_AA)

        banner = f"Mode: FULLSCREEN(YAML) | Room: {ACTIVE_ROOM} | ROI: {w0}x{h0}"
        cv2.rectangle(bgr, (0,0), (W, 26), (0,0,0), -1)
        cv2.putText(bgr, banner, (8,18), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255,255,255), 1, cv2.LINE_AA)
        cv2.putText(bgr, HELP, (8, H-10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (220,220,220), 1, cv2.LINE_AA)

        cv2.imshow("SUITS (FULLSCREEN)", bgr)
        k = cv2.waitKey(60) & 0xFF
        if k == 27: break
        elif k == ord(' '):
            cfg = load_room_config(ACTIVE_ROOM)
            print("↻ YAML rechargé")
        elif k == ord('g'):
            show_grid = not show_grid
        elif k == ord('s'):
            snap_id += 1
            out = f"suits_preview_full_{snap_id:02d}.png"
            cv2.imwrite(out, bgr); print("saved:", out)

    cv2.destroyAllWindows(); print("Bye.")

if __name__ == "__main__":
    main()
