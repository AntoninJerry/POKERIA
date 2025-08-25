# src/tools/collect_corners.py
import cv2, time
from pathlib import Path
from typing import Tuple, Dict
from src.capture.screen import capture_table
from src.config.settings import get_table_roi, load_room_config, ACTIVE_ROOM
from src.ocr.cards import _best_tl_corner_for_rank, _extract_rank_patch

OUT_R = Path("assets/dataset/unlabeled/rank")
OUT_S = Path("assets/dataset/unlabeled/suit")
OUT_R.mkdir(parents=True, exist_ok=True)
OUT_S.mkdir(parents=True, exist_ok=True)

def r2a(rel, W, H) -> Tuple[int,int,int,int]:
    rx, ry, rw, rh = rel
    return int(rx*W), int(ry*H), max(1,int(rw*W)), max(1,int(rh*H))

def roi(cfg: Dict, name: str):
    v = cfg.get("rois_hint", {}).get(name)
    return v["rel"] if v and "rel" in v else None

def suit_patch_from_corner(corner_rgb):
    h, w = corner_rgb.shape[:2]
    x1, y1, x2, y2 = int(0.45*w), 0, w, int(0.75*h)
    return corner_rgb[y1:y2, x1:x2].copy()

class DummyEngine:
    """Simule .read_text pour _best_tl_corner_for_rank()"""
    def read_text(self, *args, **kwargs):
        return "", 0.0, []

def _nonempty(img):
    return img is not None and hasattr(img, "size") and img.size > 0 and img.shape[0] > 0 and img.shape[1] > 0

def main():
    names = [
        "hero_card_left","hero_card_right",
        "board_card_1","board_card_2","board_card_3","board_card_4","board_card_5"
    ]
    dummy = DummyEngine()

    while True:
        table = capture_table(get_table_roi(ACTIVE_ROOM))  # RGB
        H, W = table.shape[:2]
        cfg = load_room_config(ACTIVE_ROOM)
        ts = time.strftime("%Y%m%d_%H%M%S")
        saved = 0

        for n in names:
            rel = roi(cfg, n)
            if not rel:
                continue
            x, y, w, h = r2a(rel, W, H)
            crop = table[y:y+h, x:x+w].copy()
            if not _nonempty(crop):
                continue

            # coin TL (choix data-driven) – pas d'OCR, on passe un dummy engine
            corner, _ = _best_tl_corner_for_rank(dummy, crop)
            if not _nonempty(corner):
                continue

            rank_patch = _extract_rank_patch(corner)
            suit_patch = suit_patch_from_corner(corner)

            if _nonempty(rank_patch):
                cv2.imwrite(str(OUT_R/f"{ts}_{n}_rank.png"),
                            cv2.cvtColor(rank_patch, cv2.COLOR_RGB2BGR))
                saved += 1
            if _nonempty(suit_patch):
                cv2.imwrite(str(OUT_S/f"{ts}_{n}_suit.png"),
                            cv2.cvtColor(suit_patch, cv2.COLOR_RGB2BGR))
                saved += 1

        print(f"✅ Capturé {saved} patches. [ESPACE=continuer | ESC=quitter]")
        # petite fenêtre pour capter les touches (OpenCV)
        cv2.imshow("collect_corners", (table[:, :, ::-1] * 0 + 128))
        while True:
            k = cv2.waitKey(0) & 0xFF
            if k == 27:  # ESC
                cv2.destroyAllWindows()
                return
            if k == 32:  # SPACE
                cv2.destroyWindow("collect_corners")
                break

if __name__ == "__main__":
    main()
