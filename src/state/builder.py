import cv2
import re
from src.config.settings import get_table_roi, load_room_config, ACTIVE_ROOM
from src.capture.screen import capture_table
from src.ocr.engine import EasyOCREngine
from src.ocr.cards import read_card
from src.ocr.preprocess import preprocess_digits, to_rgb
from src.state.models import TableState
from src.tools.detect_dealer import main as detect_dealer  # tu as déjà la détection bouton
from src.ocr.engine_singleton import get_engine
from src.ocr.preprocess import preprocess_digits_variants, to_rgb

def _read_amount_variants(engine, crop_rgb):
    """
    Essaie plusieurs binarisations/variants pour lire un montant.
    Retourne float(value) ou 0.0 si tout échoue.
    Attend que engine.read_amount(...) renvoie au minimum:
      - {"value": <float|str>, "conf": <0..1>}
    """
    best = None
    for th in preprocess_digits_variants(crop_rgb):
        res = engine.read_amount(to_rgb(th))
        if not res:
            continue
        val = res.get("value", None)
        try:
            if val is None:
                continue
            v = float(val)
            c = float(res.get("conf", 0.0))
        except Exception:
            continue
        if (best is None) or (c > best["conf"]):
            best = {"value": v, "conf": c}
    return best["value"] if best is not None else 0.0


def rel_to_abs(rel, W, H):
    rx, ry, rw, rh = rel
    return int(rx*W), int(ry*H), int(rw*W), int(rh*H)

def crop_from_cfg(cfg, table_rgb, name):
    H,W = table_rgb.shape[:2]
    roi = cfg.get("rois_hint",{}).get(name)
    if not roi: return None
    x,y,w,h = rel_to_abs(roi["rel"],W,H)
    return table_rgb[y:y+h, x:x+w].copy()

def _read_amount_any(engine, rgb):
    # 1) tentative directe
    try:
        from src.ocr.preprocess import preprocess_digits, to_rgb
        th = preprocess_digits(rgb)
        res = engine.read_amount(to_rgb(th))
        if res and res.get("value") is not None:
            return float(res["value"])
    except Exception:
        pass
    # 2) fallback regex (€, virgule décimale)
    txt, conf, raw = engine.read_text(rgb, allowlist="0123456789,€. ")
    m = re.findall(r"(\d{1,3}(?:[\s\.]\d{3})*|\d+)[,\.](\d{2})\s*€?", txt or "")
    if m:
        x = m[-1]  # on prend la dernière valeur trouvée (souvent la plus à droite)
        whole = re.sub(r"[^\d]", "", x[0])
        cents = x[1]
        try:
            return float(f"{whole}.{cents}")
        except Exception:
            return 0.0
    return 0.0

def build_state(engine: EasyOCREngine | None = None) -> TableState:
    table_rgb = capture_table(get_table_roi(ACTIVE_ROOM))
    H, W = table_rgb.shape[:2]
    cfg = load_room_config(ACTIVE_ROOM)
    engine = engine or get_engine()

    state = TableState(seats_n=cfg.get("table_meta",{}).get("seats_n",6))

    # Hero cards
    for n in ["hero_card_left","hero_card_right"]:
        crop = crop_from_cfg(cfg,table_rgb,n)
        if crop is not None:
            card, meta = read_card(engine, crop, n, cfg)
            val,meta = read_card(engine,crop,n, cfg)
            if val: state.hero_cards.append(val)

    # Board cards
    for n in ["board_card_1","board_card_2","board_card_3","board_card_4","board_card_5"]:
        crop = crop_from_cfg(cfg,table_rgb,n)
        if crop is not None:
            card, meta = read_card(engine, crop, n, cfg)
            val,meta = read_card(engine,crop,n, cfg)
            if val: state.community_cards.append(val)

    # Pot
    crop = crop_from_cfg(cfg, table_rgb, "pot_amount")
    if crop is not None:
        state.pot_size = _read_amount_variants(engine, crop)

    crop = crop_from_cfg(cfg, table_rgb, "hero_stack")
    if crop is not None:
        state.hero_stack = _read_amount_variants(engine, crop)

            
    act = crop_from_cfg(cfg, table_rgb, "action_strip")
    if act is not None:
        try:
            state.to_call = float(_read_amount_any(engine, act) or 0.0)
        except Exception:
            state.to_call = 0.0

    # Dealer seat
    try:
        from src.state.seating import seat_centers_from_yaml, nearest_seat
        from src.tools.detect_dealer import detect_by_template, detect_by_hough
        img_bgr = cv2.cvtColor(table_rgb, cv2.COLOR_RGB2BGR)
        res = detect_by_template(img_bgr) or detect_by_hough(img_bgr)
        if res:
            (cx,cy),score = res
            centers = seat_centers_from_yaml(W,H,cfg)
            state.dealer_seat = nearest_seat(cx,cy,centers)
            # Héros = seat 0 (bas), donc position relative se calcule ensuite
            state.hero_seat = 0
    except Exception as e:
        print("Dealer detection failed:", e)

    return state

