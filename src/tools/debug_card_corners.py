import cv2
from src.capture.screen import capture_table
from src.config.settings import get_table_roi, load_room_config, ACTIVE_ROOM
from src.ocr.cards import _corner
from typing import Tuple, Dict

def r2a(rel, W, H): rx, ry, rw, rh = rel; return int(rx*W), int(ry*H), max(1,int(rw*W)), max(1,int(rh*H))
def roi(cfg, name): v = cfg.get("rois_hint", {}).get(name); return v["rel"] if v and "rel" in v else None

def main():
    table = capture_table(get_table_roi(ACTIVE_ROOM))
    H, W = table.shape[:2]
    cfg = load_room_config(ACTIVE_ROOM)
    names = ["hero_card_left","hero_card_right","board_card_1","board_card_2","board_card_3","board_card_4","board_card_5"]
    idx = 0
    for n in names:
        rel = roi(cfg, n)
        if not rel: continue
        x,y,w,h = r2a(rel, W, H)
        crop = table[y:y+h, x:x+w].copy()
        corner = _corner(crop)
        cv2.imshow(n, cv2.cvtColor(corner, cv2.COLOR_RGB2BGR)); idx += 1
    if idx == 0: print("Aucune ROI cartes trouvée.")
    cv2.waitKey(0); cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
