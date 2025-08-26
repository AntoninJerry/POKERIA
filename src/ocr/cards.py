# src/ocr/cards.py
import cv2, numpy as np
from typing import Optional, Tuple, Dict
from src.ocr.engine import EasyOCREngine
from src.ocr.suit_shape import SuitHu

_SUITS_HU = SuitHu()

RANK_ALLOW = "0123456789TJQKA"
RANK_SET = set("23456789TJQKA")

# ----------------- utils -----------------
def _nonempty(img):
    return img is not None and hasattr(img, "size") and img.size > 0 and img.shape[0] > 0 and img.shape[1] > 0

def _is_small_roi(w, h):  # si tu passes déjà un coin ou une petite sous-zone
    return w < 40 or h < 40 or (w * h) <= 2000

def _roi_from_rel(img_rgb, rel):
    """Découpe une sous-ROI relative [rx,ry,rw,rh] dans img_rgb."""
    if not _nonempty(img_rgb) or not rel: return None
    h, w = img_rgb.shape[:2]
    rx, ry, rw, rh = rel
    x, y = int(rx * w), int(ry * h)
    ww, hh = max(1, int(rw * w)), max(1, int(rh * h))
    x = max(0, min(x, w - 1)); y = max(0, min(y, h - 1))
    ww = max(1, min(ww, w - x)); hh = max(1, min(hh, h - y))
    return img_rgb[y:y + hh, x:x + ww].copy()

# ----------------- prétraitements -----------------
def _prep_bin_otsu(img_rgb, target_h=140):
    gray = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2GRAY)
    gray = cv2.createCLAHE(3.0, (8, 8)).apply(gray)
    g = cv2.GaussianBlur(gray, (3, 3), 0)
    _, th = cv2.threshold(g, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    if gray.mean() < 127: th = 255 - th
    h, w = th.shape[:2]; s = target_h / max(1.0, h)
    return cv2.resize(th, (max(1, int(w * s)), int(target_h)), interpolation=cv2.INTER_CUBIC)

def _prep_bin_adapt(img_rgb, target_h=140):
    gray = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2GRAY)
    gray = cv2.createCLAHE(3.0, (8, 8)).apply(gray)
    g = cv2.GaussianBlur(gray, (3, 3), 0)
    th = cv2.adaptiveThreshold(g, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 5)
    if gray.mean() < 127: th = 255 - th
    h, w = th.shape[:2]; s = target_h / max(1.0, h)
    return cv2.resize(th, (max(1, int(w * s)), int(target_h)), interpolation=cv2.INTER_CUBIC)

# ----------------- heuristiques rang/suit -----------------
def _rank_q_vs_9(corner_rgb, rank_code, alt_code, margin: float):
    if {rank_code, alt_code} != {"Q", "9"} or margin >= 0.05: return rank_code
    h, w = corner_rgb.shape[:2]
    br = corner_rgb[int(0.60 * h):h, int(0.55 * w):w]
    if not _nonempty(br): return rank_code
    th = _prep_bin_otsu(br, target_h=80)
    black_ratio = float(np.count_nonzero(255 - th)) / (th.size + 1e-6)
    return "Q" if black_ratio > 0.20 else "9"

def _suit_by_color(corner_rgb) -> str:
    hsv = cv2.cvtColor(corner_rgb, cv2.COLOR_RGB2HSV)
    mask1 = cv2.inRange(hsv, (0, 70, 40), (10, 255, 255))
    mask2 = cv2.inRange(hsv, (170, 70, 40), (180, 255, 255))
    red_ratio = float(np.count_nonzero(mask1 | mask2)) / (corner_rgb.shape[0] * corner_rgb.shape[1] + 1e-6)
    return "red" if red_ratio > 0.05 else "black"

def _suit_patch_auto(corner_rgb):
    """
    Cherche le symbole dans la moitié droite du coin TL.
    - ROI droite (0..80% H, 40..100% L)
    - Otsu + plus gros contour
    - fallback: bloc fixe (0..75% H, 45..100% L)
    """
    h, w = corner_rgb.shape[:2]
    x1, y1, x2, y2 = int(0.40 * w), 0, w, int(0.80 * h)
    if x2 <= x1 or y2 <= y1:
        return None
    right = corner_rgb[y1:y2, x1:x2].copy()

    th = _prep_bin_otsu(right, target_h=120)
    try:
        contours, _ = cv2.findContours(255 - th, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    except Exception:
        contours = []

    if contours:
        c = max(contours, key=cv2.contourArea)
        x, y, ww, hh = cv2.boundingRect(c)
        if ww * hh >= 16:  # filtre bruit
            ys1 = max(0, y - 2); ys2 = min(th.shape[0], y + hh + 2)
            xs1 = max(0, x - 2); xs2 = min(th.shape[1], x + ww + 2)
            return right[ys1:ys2, xs1:xs2].copy()

    # fallback fixe si pas de contour utilisable
    fx1, fy2 = int(0.45 * w), int(0.75 * h)
    if fx1 < w and fy2 > 0:
        return corner_rgb[0:fy2, fx1:w].copy()
    return None

# ----------------- OCR rang -----------------
def _read_rank(engine: EasyOCREngine, rank_rgb) -> Tuple[Optional[str], float, Dict]:
    variants = [_prep_bin_otsu(rank_rgb, 160), _prep_bin_adapt(rank_rgb, 160)]
    best = None
    for i, th in enumerate(variants):
        img3 = cv2.cvtColor(th, cv2.COLOR_GRAY2RGB)
        txt, conf, raw = engine.read_text(img3, allowlist=RANK_ALLOW)
        toks = [t for (_b, t, _c) in (raw or []) if t and t.strip()]
        guess = "".join(toks or [txt or ""]).upper().replace(" ", "")
        guess = guess.replace("I", "1").replace("O", "0").replace("D", "Q")
        if "10" in guess: rank = "T"
        elif guess and guess[0] in RANK_SET: rank = guess[0]
        else: rank = None
        if rank and (best is None or conf > best["conf"]):
            best = {"rank": rank, "conf": float(conf), "var": i}
    if best: return best["rank"], best["conf"], best
    return None, 0.0, {}

# ----------------- API -----------------
def read_card(
    engine: EasyOCREngine,
    crop_rgb,
    roi_name: Optional[str] = None,
    cfg: Optional[dict] = None
):
    """
    Lit une carte à partir d'un crop (carte entière ou coin).
    - Si cfg['rois_hint'][roi_name]['rank_rel'] existe -> on lit le rang dedans.
    - Si cfg['rois_hint'][roi_name]['suit_rel'] existe -> on lit le symbole dedans.
    - Sinon, extraction auto (coin TL pour rang, recherche symbole côté droit).
    """
    if not _nonempty(crop_rgb):
        return None, {"roi_name": roi_name, "error": "empty"}

    h, w = crop_rgb.shape[:2]
    small = _is_small_roi(w, h)

    # --- RANK patch ---
    rank_patch = None
    if cfg and roi_name:
        rank_rel = (cfg.get("rois_hint", {}).get(roi_name, {}) or {}).get("rank_rel")
        if rank_rel:
            rank_patch = _roi_from_rel(crop_rgb, rank_rel)

    if rank_patch is None:
        # coin TL si carte entière, sinon on suppose que crop_rgb est déjà focalisé
        rank_patch = crop_rgb.copy() if small else crop_rgb[0:int(0.55 * h), 0:int(0.60 * w)].copy()

    if not _nonempty(rank_patch):
        return None, {"roi_name": roi_name, "error": "rank_patch"}

    # --- OCR rang ---
    r_code, r_conf, r_meta = _read_rank(engine, rank_patch)

    # --- SUIT patch ---
    suit_patch = None
    if cfg and roi_name:
        suit_rel = (cfg.get("rois_hint", {}).get(roi_name, {}) or {}).get("suit_rel")
        if suit_rel:
            suit_patch = _roi_from_rel(crop_rgb, suit_rel)

    if suit_patch is None:
        # extraction auto depuis le "coin" (zone rang/symbole)
        corner = crop_rgb.copy() if small else crop_rgb[0:int(0.55 * h), 0:int(0.60 * w)].copy()
        color_hint = _suit_by_color(corner)  # "red"/"black"
        suit_patch = _suit_patch_auto(corner)
        if not _nonempty(suit_patch):
            # fallback couleur si on n'a rien de propre
            s_code = "h" if color_hint == "red" else "s"
            s_conf = 0.5
            s_meta = {"reason": "no_suit_patch"}
        else:
            s_code, s_conf, s_meta = _SUITS_HU.classify(suit_patch, color_hint=color_hint)
            if s_code is None:
                s_code = "h" if color_hint == "red" else "s"
                s_conf = 0.5
                s_meta = {"reason": "classify_none"}
    else:
        # zone manuelle -> pas besoin du hint couleur
        s_code, s_conf, s_meta = _SUITS_HU.classify(suit_patch, color_hint=None)
        if s_code is None:
            s_code, s_conf, s_meta = "s", 0.5, {"reason": "cfg_fallback"}

    # --- Tie-break Q vs 9 si faible confiance rang ---
    if r_code in ("Q", "9") and r_meta.get("conf", 0.0) < 0.7:
        # On utilise le patch où le rang a été lu (rank_patch)
        r_code = _rank_q_vs_9(rank_patch, r_code, "Q" if r_code == "9" else "9", 0.0)

    card = f"{r_code}{s_code}" if (r_code and s_code) else None
    return card, {
        "roi_name": roi_name,
        "rank_code": r_code,
        "rank_conf": r_conf,
        **{k: v for k, v in r_meta.items() if k != "rank_patch"},
        "suit_code": s_code,
        "suit_conf": s_conf,
        **(s_meta or {})
    }
