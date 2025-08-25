import cv2, sys
from typing import Tuple, Dict
from src.capture.screen import capture_table
from src.config.settings import get_table_roi, load_room_config, ACTIVE_ROOM
from src.ocr.cards import read_card
from src.ocr.engine import EasyOCREngine

def rel_to_abs(rel, W, H) -> Tuple[int,int,int,int]:
    rx, ry, rw, rh = rel
    return int(rx*W), int(ry*H), max(1,int(rw*W)), max(1,int(rh*H))

def get_roi(cfg: Dict, name: str):
    v = cfg.get("rois_hint", {}).get(name)
    return v["rel"] if v and "rel" in v else None

def read_named(engine, table_rgb, cfg, name):
    rel = get_roi(cfg, name)
    if not rel: return name, None, {}
    H, W = table_rgb.shape[:2]
    x,y,w,h = rel_to_abs(rel, W, H)
    crop = table_rgb[y:y+h, x:x+w].copy()
    val, meta = read_card(engine, crop)
    return name, val, meta

def main():
    table_rgb = capture_table(get_table_roi(ACTIVE_ROOM))
    cfg = load_room_config(ACTIVE_ROOM)
    engine = EasyOCREngine(gpu=False)

    names = [
        "hero_card_left","hero_card_right",
        "board_card_1","board_card_2","board_card_3","board_card_4","board_card_5"
    ]
    print("=== OCR CARTES (héros + board) ===")
    for n in names:
        n, val, meta = read_named(engine, table_rgb, cfg, n)
        print(f"{n:15s} -> {val}  (rank_conf={meta.get('rank_conf')}, suit_conf={meta.get('suit_conf')})")

if __name__ == "__main__":
    main()
