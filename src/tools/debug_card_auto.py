# src/tools/debug_card_auto.py
import cv2
from src.capture.screen import capture_table
from src.config.settings import get_table_roi, load_room_config, ACTIVE_ROOM
from src.ocr.cards import _candidate_corners
from typing import Tuple, Dict

def r2a(rel, W, H): rx, ry, rw, rh = rel; return int(rx*W), int(ry*H), max(1,int(rw*W)), max(1,int(rh*H))
def roi(cfg, name): v = cfg.get("rois_hint", {}).get(name); return v["rel"] if v and "rel" in v else None

def main():
    table = capture_table(get_table_roi(ACTIVE_ROOM))
    H, W = table.shape[:2]
    cfg = load_room_config(ACTIVE_ROOM)
    names = ["hero_card_left","hero_card_right","board_card_1","board_card_2","board_card_3","board_card_4","board_card_5"]
    for n in names:
        rel = roi(cfg, n)
        if not rel: continue
        x,y,w,h = r2a(rel, W, H)
        crop = table[y:y+h, x:x+w].copy()
        h2,w2 = crop.shape[:2]
        if w2*h2 > 2000 and w2>=40 and h2>=40:
            corners = _candidate_corners(crop)
            for k,im in corners.items():
                cv2.imshow(f"{n}_{k}", cv2.cvtColor(im, cv2.COLOR_RGB2BGR))
        else:
            cv2.imshow(f"{n}_small", cv2.cvtColor(crop, cv2.COLOR_RGB2BGR))
    cv2.waitKey(0); cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
