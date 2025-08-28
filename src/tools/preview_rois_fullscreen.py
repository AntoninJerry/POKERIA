# src/tools/preview_rois_fullscreen.py
import os, cv2
from typing import Tuple, Any
from src.capture.screen import capture_table
from src.config.settings import load_room_config, get_table_roi, ACTIVE_ROOM

HELP = "ESC=quit  SPACE=reload YAML  g=grid  s=snapshot"

def rect_to_tuple(rect: Any) -> Tuple[int,int,int,int]:
    """Supporte Rect(x,y,w,h) OU dict {left,top,width,height}."""
    if hasattr(rect, "x"):   # dataclass Rect
        return int(rect.x), int(rect.y), int(rect.w), int(rect.h)
    # dict-like
    x = int(getattr(rect, "left", getattr(rect, "x", rect["left"] if "left" in rect else rect["x"])))
    y = int(getattr(rect, "top",  getattr(rect, "y", rect["top"]  if "top"  in rect else rect["y"])))
    w = int(getattr(rect, "width",getattr(rect, "w", rect["width"]if "width"in rect else rect["w"])))
    h = int(getattr(rect, "height",getattr(rect,"h", rect["height"]if "height"in rect else rect["h"])))
    return x,y,w,h

def rel_to_abs(rel, W, H) -> Tuple[int,int,int,int]:
    rx, ry, rw, rh = rel
    x = int(rx * W); y = int(ry * H)
    w = max(1, int(rw * W)); h = max(1, int(rh * H))
    return x, y, w, h

def suit_rel_to_abs(srel, roi_abs):
    rx, ry, rw, rh = srel
    x, y, w, h = roi_abs
    sx = int(x + rx * w); sy = int(y + ry * h)
    sw = max(1, int(rw * w)); sh = max(1, int(rh * h))
    return sx, sy, sw, sh

def color_for(name: str):
    n = name.lower()
    if "hero_card" in n:  return (0,255,255)  # jaune
    if "board_card" in n: return (255,0,255)  # magenta
    if "pot" in n:        return (0,255,0)    # vert
    if "stack" in n:      return (255,255,0)  # cyan chaud
    if "action" in n:     return (0,200,255)  # orange/bleu
    return (200,200,200)

def main():
    print("=== PREVIEW ROIs (FULLSCREEN / YAML) ===")
    print(HELP)
    # Forcer le mode YAML (plein écran)
    os.environ["POKERIA_WINDOWED"] = "0"

    cfg = load_room_config(ACTIVE_ROOM)
    show_grid = False
    snap_id = 0

    cv2.namedWindow("TABLE + ROIs (FULLSCREEN)", cv2.WINDOW_NORMAL)

    while True:
        rect_obj = get_table_roi(ACTIVE_ROOM)  # objet Rect ou dict
        x0,y0,w0,h0 = rect_to_tuple(rect_obj)
        table = capture_table(rect_obj)        # ton capture accepte déjà Rect/dict
        H, W = table.shape[:2]
        bgr = cv2.cvtColor(table, cv2.COLOR_RGB2BGR)

        # cadre du table_roi (rouge)
        cv2.rectangle(bgr, (1,1), (W-2, H-2), (0,0,255), 1)

        if show_grid:
            for k in range(1,4):
                x = int(W * k/4.0); y = int(H * k/4.0)
                cv2.line(bgr, (x,0), (x,H), (60,60,60), 1, cv2.LINE_AA)
                cv2.line(bgr, (0,y), (W,y), (60,60,60), 1, cv2.LINE_AA)

        rois = cfg.get("rois_hint", {}) or {}
        for name, node in rois.items():
            rel = node.get("rel")
            if not rel: continue
            x,y,w,h = rel_to_abs(rel, W, H)
            clr = color_for(name)
            cv2.rectangle(bgr, (x,y), (x+w, y+h), clr, 2, cv2.LINE_AA)
            cv2.putText(bgr, name, (x+3, y+16), cv2.FONT_HERSHEY_SIMPLEX, 0.5, clr, 1, cv2.LINE_AA)

            srel = node.get("suit_rel")
            if srel:
                sx,sy,sw,sh = suit_rel_to_abs(srel, (x,y,w,h))
                cv2.rectangle(bgr, (sx,sy), (sx+sw, sy+sh), (0,255,0), 2, cv2.LINE_AA)
                cv2.putText(bgr, "suit_rel", (sx+2, sy-4 if sy>12 else sy+14),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0,255,0), 1, cv2.LINE_AA)

        banner = f"Mode: FULLSCREEN(YAML) | Room: {ACTIVE_ROOM} | ROI: {w0}x{h0}"
        cv2.rectangle(bgr, (0,0), (W, 26), (0,0,0), -1)
        cv2.putText(bgr, banner, (8,18), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255,255,255), 1, cv2.LINE_AA)
        cv2.putText(bgr, HELP, (8, H-10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (220,220,220), 1, cv2.LINE_AA)

        cv2.imshow("TABLE + ROIs (FULLSCREEN)", bgr)
        k = cv2.waitKey(60) & 0xFF
        if k == 27: break
        elif k == ord(' '): cfg = load_room_config(ACTIVE_ROOM)
        elif k == ord('g'): show_grid = not show_grid
        elif k == ord('s'):
            snap_id += 1
            out = f"roi_preview_full_{snap_id:02d}.png"
            cv2.imwrite(out, bgr); print("saved:", out)

    cv2.destroyAllWindows(); print("Bye.")

if __name__ == "__main__":
    main()
