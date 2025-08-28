# src/tools/ocr_cards_smoke.py
from __future__ import annotations
import os, sys, argparse, cv2
from typing import Tuple, Dict, Any

from src.capture.screen import capture_table
from src.config.settings import get_table_roi, load_room_config, ACTIVE_ROOM
from src.ocr.engine_singleton import get_engine
from src.ocr.cards import read_card

def rel_to_abs(rel, W, H) -> Tuple[int,int,int,int]:
    rx, ry, rw, rh = rel
    return int(rx*W), int(ry*H), max(1,int(rw*W)), max(1,int(rh*H))

def get_roi(cfg: Dict[str, Any], name: str):
    v = (cfg.get("rois_hint", {}) or {}).get(name) or {}
    return v.get("rel")

def read_named(engine, table_rgb, cfg, name):
    rel = get_roi(cfg, name)
    if not rel:
        return name, None, {}, None
    H, W = table_rgb.shape[:2]
    x,y,w,h = rel_to_abs(rel, W, H)
    crop = table_rgb[y:y+h, x:x+w].copy()
    try:
        val, meta = read_card(engine, crop, name, cfg)   # ✅ on passe roi_name + cfg
    except Exception as e:
        val, meta = None, {"error": str(e)}
    return name, val, (meta or {}), (x,y,w,h)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--show", action="store_true")
    args = ap.parse_args()

    # Plein écran strict
    os.environ["POKERIA_WINDOWED"] = "0"

    table_rgb = capture_table(get_table_roi(ACTIVE_ROOM))
    if table_rgb is None:
        print("❌ Impossible de capturer la table."); sys.exit(1)

    cfg = load_room_config(ACTIVE_ROOM)
    engine = get_engine()

    H, W = table_rgb.shape[:2]
    bgr = cv2.cvtColor(table_rgb, cv2.COLOR_RGB2BGR)

    names = [
        "hero_card_left","hero_card_right",
        "board_card_1","board_card_2","board_card_3","board_card_4","board_card_5"
    ]

    print("=== OCR CARTES (héros + board) ===")
    for n in names:
        n, val, meta, rect = read_named(engine, table_rgb, cfg, n)
        rank_conf = float(meta.get("rank_conf", 0.0))
        suit_conf = float(meta.get("suit_conf", 0.0))
        print(f"{n:15s} -> {val}  (rank_conf={rank_conf:.6f}, suit_conf={suit_conf:.6f})")

        if args.show and rect is not None:
            x,y,w,h = rect
            cv2.rectangle(bgr, (x,y), (x+w,y+h), (0,255,255), 2)
            node = (cfg.get("rois_hint", {}) or {}).get(n, {}) or {}
            rank_rel = node.get("rank_rel"); suit_rel = node.get("suit_rel")
            if rank_rel and len(rank_rel)==4:
                rx,ry,rw,rh = rank_rel
                gx1, gy1 = x + int(rx*w), y + int(ry*h)
                gx2, gy2 = x + int((rx+rw)*w), y + int((ry+rh)*h)
                cv2.rectangle(bgr, (gx1,gy1), (gx2,gy2), (0,255,0), 2)   # vert
            if suit_rel and len(suit_rel)==4:
                sx,sy,sw,sh = suit_rel
                hx1, hy1 = x + int(sx*w), y + int(sy*h)
                hx2, hy2 = x + int((sx+sw)*w), y + int((sy+sh)*h)
                cv2.rectangle(bgr, (hx1,hy1), (hx2,hy2), (255,255,0), 2) # cyan

            label = f"{n}: {val or '?'}  r={rank_conf:.2f} s={suit_conf:.2f}"
            tx, ty = x+5, max(y+18, 18)
            (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 2)
            cv2.rectangle(bgr, (tx-4, ty-14), (tx-4+tw+8, ty-14+th+8), (0,0,0), -1)
            cv2.putText(bgr, label, (tx,ty), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255,255,255), 2)

    if args.show:
        cv2.imshow("ocr_cards_smoke — overlay", bgr)
        cv2.waitKey(0); cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
