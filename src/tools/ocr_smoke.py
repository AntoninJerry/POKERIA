import cv2, sys, argparse
from typing import Tuple, Dict
from src.capture.screen import capture_table
from src.config.settings import get_table_roi, load_room_config, ACTIVE_ROOM
from src.ocr.preprocess import preprocess_digits_variants, to_rgb
from src.ocr.engine import EasyOCREngine

def rel_to_abs(rel, W, H) -> Tuple[int, int, int, int]:
    rx, ry, rw, rh = rel
    x = int(rx * W); y = int(ry * H)
    w = max(1, int(rw * W)); h = max(1, int(rh * H))
    return x, y, w, h

def get_roi(cfg: Dict, name: str):
    v = cfg.get("rois_hint", {}).get(name)
    return v["rel"] if v and "rel" in v else None

def best_amount(engine, img_rgb):
    best = None
    variants = preprocess_digits_variants(img_rgb)
    for i, v in enumerate(variants):
        res = engine.read_amount(to_rgb(v))
        score = (res["value"] is not None) * 1.0 + res["conf"] * 0.1
        # priorité à une valeur parsée, puis à la confiance
        if best is None or score > best["_score"]:
            res["_score"] = score
            res["_idx"] = i
            best = res
    return best, variants

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--show", action="store_true", help="Afficher la meilleure variante")
    args = ap.parse_args()

    table_rgb = capture_table(get_table_roi(ACTIVE_ROOM))
    H, W = table_rgb.shape[:2]

    cfg = load_room_config(ACTIVE_ROOM)
    pot_rel = get_roi(cfg, "pot_amount")
    hero_rel = get_roi(cfg, "hero_stack")
    if pot_rel is None or hero_rel is None:
        print("❌ YAML incomplet: il faut 'pot_amount' et 'hero_stack'.")
        sys.exit(1)

    px, py, pw, ph = rel_to_abs(pot_rel, W, H)
    hx, hy, hw, hh = rel_to_abs(hero_rel, W, H)
    pot_crop = table_rgb[py:py+ph, px:px+pw].copy()
    hero_crop = table_rgb[hy:hy+hh, hx:hx+hw].copy()

    engine = EasyOCREngine(gpu=False)
    pot_res, pot_vars = best_amount(engine, pot_crop)
    hero_res, hero_vars = best_amount(engine, hero_crop)

    print("=== OCR SMOKE (multi-variants) ===")
    print(f"Pot:   idx={pot_res['_idx']} text='{pot_res['text']}' -> value={pot_res['value']} conf={pot_res['conf']:.2f}")
    print(f"Stack: idx={hero_res['_idx']} text='{hero_res['text']}' -> value={hero_res['value']} conf={hero_res['conf']:.2f}")

    if args.show:
        cv2.imshow("pot_best", cv2.cvtColor(pot_vars[pot_res['_idx']], cv2.COLOR_GRAY2BGR))
        cv2.imshow("stack_best", cv2.cvtColor(hero_vars[hero_res['_idx']], cv2.COLOR_GRAY2BGR))
        cv2.waitKey(0); cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
