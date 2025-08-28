# src/tools/validate_rois.py
import os, cv2, argparse
from typing import Tuple, Any
from src.capture.screen import capture_table
from src.config.settings import load_room_config, get_table_roi, ACTIVE_ROOM

def rect_to_tuple(rect: Any) -> Tuple[int,int,int,int]:
    if hasattr(rect, "x"): return int(rect.x), int(rect.y), int(rect.w), int(rect.h)
    return int(rect["left"]), int(rect["top"]), int(rect["width"]), int(rect["height"])

def rel_to_abs(rel, W, H):
    rx,ry,rw,rh = rel
    x,y = int(rx*W), int(ry*H)
    w,h = max(1,int(rw*W)), max(1,int(rh*H))
    return x,y,w,h

def suit_rel_to_abs(srel, roi_abs):
    rx,ry,rw,rh = srel
    x,y,w,h = roi_abs
    sx, sy = int(x+rx*w), int(y+ry*h)
    sw, sh = max(1,int(rw*w)), max(1,int(rh*h))
    return sx,sy,sw,sh

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--room", default=ACTIVE_ROOM, help="nom du profil YAML (ex: winamax_windowed)")
    ap.add_argument("--windowed", type=int, default=None, help="1=rect Win32, 0=YAML; par défaut conserve l'env")
    ap.add_argument("--out", default="roi_validate.png")
    args = ap.parse_args()

    if args.windowed is not None:
        os.environ["POKERIA_WINDOWED"] = "1" if args.windowed==1 else "0"

    cfg = load_room_config(args.room)
    rect = get_table_roi(args.room)
    table = capture_table(rect)   # RGB
    H,W = table.shape[:2]
    bgr = cv2.cvtColor(table, cv2.COLOR_RGB2BGR)

    ok, warn = [], []
    rois = cfg.get("rois_hint", {}) or {}

    for name, node in rois.items():
        rel = node.get("rel")
        if not rel:
            warn.append(f"{name}: pas de 'rel'")
            continue
        x,y,w,h = rel_to_abs(rel, W, H)
        in_bounds = (0 <= x < W) and (0 <= y < H) and (x+w <= W) and (y+h <= H)
        nonempty = (w>2 and h>2)
        if in_bounds and nonempty:
            ok.append(name)
            clr = (0,255,0)
        else:
            warn.append(f"{name}: OUT/EMPTY x={x} y={y} w={w} h={h} (W={W} H={H})")
            clr = (0,0,255)
        cv2.rectangle(bgr, (x,y), (x+w,y+h), clr, 2, cv2.LINE_AA)
        cv2.putText(bgr, name, (x+3,y+16), cv2.FONT_HERSHEY_SIMPLEX, 0.5, clr, 1, cv2.LINE_AA)

        srel = node.get("suit_rel")
        if srel:
            sx,sy,sw,sh = suit_rel_to_abs(srel, (x,y,w,h))
            cv2.rectangle(bgr, (sx,sy), (sx+sw,sy+sh), (0,255,255), 2, cv2.LINE_AA)
            cv2.putText(bgr, "suit_rel", (sx+2, sy-4 if sy>12 else sy+14),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0,255,255), 1, cv2.LINE_AA)

    cv2.imwrite(args.out, bgr)
    print(f"Image annotée: {args.out}")
    print(f"OK: {len(ok)}  |  WARN: {len(warn)}")
    for w in warn:
        print(" -", w)

if __name__ == "__main__":
    main()
