import cv2
from src.config.settings import get_table_roi, load_room_config, ACTIVE_ROOM
from src.capture.screen import capture_table
from src.ocr.engine import EasyOCREngine
from src.ocr.cards import read_card
from src.ocr.preprocess import preprocess_digits, to_rgb
from src.state.models import TableState
from src.tools.detect_dealer import main as detect_dealer  # tu as déjà la détection bouton

def rel_to_abs(rel, W, H):
    rx, ry, rw, rh = rel
    return int(rx*W), int(ry*H), int(rw*W), int(rh*H)

def crop_from_cfg(cfg, table_rgb, name):
    H,W = table_rgb.shape[:2]
    roi = cfg.get("rois_hint",{}).get(name)
    if not roi: return None
    x,y,w,h = rel_to_abs(roi["rel"],W,H)
    return table_rgb[y:y+h, x:x+w].copy()

def build_state() -> TableState:
    table_rgb = capture_table(get_table_roi(ACTIVE_ROOM))
    H,W = table_rgb.shape[:2]
    cfg = load_room_config(ACTIVE_ROOM)
    engine = EasyOCREngine(gpu=False)

    state = TableState(seats_n=cfg.get("table_meta",{}).get("seats_n",6))

    # Hero cards
    for n in ["hero_card_left","hero_card_right"]:
        crop = crop_from_cfg(cfg,table_rgb,n)
        if crop is not None:
            val,meta = read_card(engine,crop,n)
            if val: state.hero_cards.append(val)

    # Board cards
    for n in ["board_card_1","board_card_2","board_card_3","board_card_4","board_card_5"]:
        crop = crop_from_cfg(cfg,table_rgb,n)
        if crop is not None:
            val,meta = read_card(engine,crop,n)
            if val: state.community_cards.append(val)

    # Pot
    crop = crop_from_cfg(cfg,table_rgb,"pot_amount")
    if crop is not None:
        pot_img = preprocess_digits(crop)
        pot_res = engine.read_amount(to_rgb(pot_img))
        if pot_res["value"] is not None:
            state.pot_size = pot_res["value"]

    # Hero stack
    crop = crop_from_cfg(cfg,table_rgb,"hero_stack")
    if crop is not None:
        stk_img = preprocess_digits(crop)
        stk_res = engine.read_amount(to_rgb(stk_img))
        if stk_res["value"] is not None:
            state.hero_stack = stk_res["value"]

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
