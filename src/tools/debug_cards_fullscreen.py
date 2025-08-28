# src/tools/debug_cards_fullscreen.py
import os, cv2
from datetime import datetime
from pathlib import Path

os.environ["POKERIA_WINDOWED"] = "0"

from src.config.settings import load_room_config, get_table_roi, ACTIVE_ROOM
from src.capture.screen import capture_table
from src.ocr.cards import read_card

# essaie de récupérer un moteur OCR déjà implémenté dans ton projet
def get_engine():
    try:
        from src.state.builder import get_engine as ge  # si tu as cette API
        return ge()
    except Exception:
        from src.ocr.engine import EasyOCREngine
        return EasyOCREngine(gpu=False)

CARDS = ["hero_card_left","hero_card_right",
         "board_card_1","board_card_2","board_card_3","board_card_4","board_card_5"]

def rel_to_abs(rel, W, H):
    rx, ry, rw, rh = rel
    x = int(rx*W); y = int(ry*H)
    w = max(1, int(rw*W)); h = max(1, int(rh*H))
    return x, y, w, h

def main():
    cfg = load_room_config(ACTIVE_ROOM)
    table = capture_table(get_table_roi(ACTIVE_ROOM))
    H, W = table.shape[:2]
    bgr = cv2.cvtColor(table, cv2.COLOR_RGB2BGR)
    eng = get_engine()

    outdir = Path("assets/exports/cards_" + datetime.now().strftime("%Y%m%d_%H%M%S"))
    outdir.mkdir(parents=True, exist_ok=True)

    results = {}
    for name in CARDS:
        node = (cfg.get("rois_hint", {}) or {}).get(name)
        if not node or not node.get("rel"): 
            results[name] = None
            continue
        x,y,w,h = rel_to_abs(node["rel"], W, H)
        crop = table[y:y+h, x:x+w].copy()

        card, meta = read_card(eng, crop, name, cfg)
        results[name] = (card, meta)

        # visu
        cv2.rectangle(bgr, (x,y), (x+w, y+h), (0,255,255) if "hero" in name else (255,0,255), 2)
        label = f"{name}: {card or '?'}  r={meta.get('rank_conf',0):.2f}  s={meta.get('suit_conf',0):.2f}"
        cv2.putText(bgr, label, (x+3, y-6 if y>14 else y+h+14), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255,255,255), 1)

        # export patch
        cv2.imwrite(str(outdir / f"{name}.png"), cv2.cvtColor(crop, cv2.COLOR_RGB2BGR))

    cv2.imwrite(str(outdir / "table_debug.png"), bgr)
    print("→ Exports:", outdir)
    for k,v in results.items():
        print(k, ":", v)

if __name__ == "__main__":
    main()
