# src/ocr/cards.py
from __future__ import annotations
import os, cv2, numpy as np
from typing import Optional, Tuple, Dict, List
from pathlib import Path

from src.ocr.engine import EasyOCREngine
from src.ocr.suit_shape import SuitHu
from src.ocr.preprocess import card_presence_score, red_ratio

# ───────── Constantes
RANK_ALLOW = "23456789TJQKA"
RANK_SET   = set(RANK_ALLOW)
SUITS      = ("h","d","s","c")

# Chargeur de shapes pour les enseignes (unique instance)
_SUITS_HU = SuitHu()

# ───────── Config OCR stricte (abstention + tolérance board)
DEFAULTS = {
    "strict": True,                  # strict pour Héro
    "board_tolerant": True,          # tolérance pour Board
    "min_rank_conf": 0.92,
    "min_suit_conf": 0.85,
    "min_card_score": 0.35,
    "min_edge_density": 0.012,
    "min_white_ratio": 0.04,
    # Seuils spécifiques board (plus permissifs)
    "min_rank_conf_board": 0.90,
    "min_suit_conf_board": 0.55,
    "min_card_score_board": 0.25,
    "min_white_ratio_board": 0.02,
}

def _get_card_ocr_cfg(room_cfg: dict | None):
    d = dict(DEFAULTS)
    try:
        c = (room_cfg or {}).get("ocr", {}).get("cards", {})
        for k in DEFAULTS.keys():
            if k in c:
                d[k] = c[k]
    except Exception:
        pass
    # Overrides via ENV
    def _f(name, defv):
        try: return float(os.getenv(name, defv))
        except: return defv
    d["min_rank_conf"]  = _f("POKERIA_MIN_RANK_CONF",  d["min_rank_conf"])
    d["min_suit_conf"]  = _f("POKERIA_MIN_SUIT_CONF",  d["min_suit_conf"])
    d["min_card_score"] = _f("POKERIA_MIN_CARD_SCORE", d["min_card_score"])
    d["min_edge_density"] = _f("POKERIA_MIN_EDGE_DENS", d["min_edge_density"])
    d["min_white_ratio"]  = _f("POKERIA_MIN_WHITE_RATIO", d["min_white_ratio"])
    d["min_rank_conf_board"]  = _f("POKERIA_MIN_RANK_CONF_BOARD",  d["min_rank_conf_board"])
    d["min_suit_conf_board"]  = _f("POKERIA_MIN_SUIT_CONF_BOARD",  d["min_suit_conf_board"])
    d["min_card_score_board"] = _f("POKERIA_MIN_CARD_SCORE_BOARD", d["min_card_score_board"])
    d["min_white_ratio_board"]= _f("POKERIA_MIN_WHITE_RATIO_BOARD",d["min_white_ratio_board"])
    strict_env = os.getenv("POKERIA_STRICT", None)
    if strict_env is not None:
        d["strict"] = (strict_env == "1")
    bt_env = os.getenv("POKERIA_BOARD_TOLERANT", None)
    if bt_env is not None:
        d["board_tolerant"] = (bt_env == "1")
    return d

# ───────── Utils
def _nonempty(img) -> bool:
    return img is not None and hasattr(img, "size") and img.size>0 and img.shape[0]>0 and img.shape[1]>0

def _roi_from_rel(parent_rgb, rel) -> Optional[np.ndarray]:
    if not rel: return None
    H, W = parent_rgb.shape[:2]
    rx, ry, rw, rh = rel
    x = max(0, min(int(rx * W), W - 1))
    y = max(0, min(int(ry * H), H - 1))
    w = max(1, min(int(rw * W), W - x))
    h = max(1, min(int(rh * H), H - y))
    return parent_rgb[y:y+h, x:x+w].copy()

def _suit_color_hint(rgb) -> str:
    # Indice HSV + renfort par red_ratio
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    m1 = cv2.inRange(hsv, (0,70,40), (10,255,255))
    m2 = cv2.inRange(hsv, (170,70,40), (180,255,255))
    ratio_hsv = float(np.count_nonzero(m1 | m2)) / (rgb.shape[0]*rgb.shape[1] + 1e-6)
    ratio_rr  = red_ratio(rgb)
    return "red" if max(ratio_hsv, ratio_rr) > 0.04 else "black"

# ───────── Prétraitements rank (light & fast)
def _prep_rank_bin_adapt(img_rgb, target_h=112) -> np.ndarray:
    gray = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2GRAY)
    gray = cv2.createCLAHE(3.0, (8,8)).apply(gray)
    g = cv2.GaussianBlur(gray, (3,3), 0)
    th = cv2.adaptiveThreshold(g,255,cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY,31,5)
    if gray.mean() < 127: th = 255 - th
    h,w = th.shape[:2]; s = target_h/max(1.0,h)
    return cv2.resize(th, (max(1,int(w*s)), int(target_h)), interpolation=cv2.INTER_LINEAR)

def _prep_rank_bin_otsu(img_rgb, target_h=112) -> np.ndarray:
    gray = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2GRAY)
    gray = cv2.createCLAHE(3.0, (8,8)).apply(gray)
    g = cv2.GaussianBlur(gray, (3,3), 0)
    _, th = cv2.threshold(g, 0, 255, cv2.THRESH_BINARY+cv2.THRESH_OTSU)
    if gray.mean() < 127: th = 255 - th
    h,w = th.shape[:2]; s = target_h/max(1.0,h)
    return cv2.resize(th, (max(1,int(w*s)), int(target_h)), interpolation=cv2.INTER_LINEAR)

def _rank_cleanup(raw: str) -> str:
    s = (raw or "").upper().replace(" ", "")
    s = s.replace("10","T").replace("IO","T").replace("TO","T").replace("I0","T")
    for ch in s:
        if ch in RANK_SET:
            return ch
    return ""

def _q_vs_9_heuristic(bin_patch: np.ndarray, guess: str) -> str:
    if guess not in ("Q","9"): return guess
    img = cv2.morphologyEx(bin_patch, cv2.MORPH_ERODE, np.ones((2,2), np.uint8), iterations=1)
    cnts,_ = cv2.findContours(img, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not cnts: return guess
    cnt = max(cnts, key=cv2.contourArea)
    (w,h) = cv2.minAreaRect(cnt)[1]
    if w<1 or h<1: return guess
    aspect = float(min(w,h)/max(w,h))
    return "Q" if aspect < 0.45 else guess

# ───────── Bank templates RANK (facultatif mais utile)
def _default_ranks_dir() -> Path:
    # assets/templates/ranks/<R>/*.png  ou  ranks/R_*.png
    here = Path(__file__).resolve()
    repo = here.parents[2]  # .../pokeria/
    return repo / "assets" / "templates" / "ranks"

def _to_bin_rank_for_match(img_rgb, target_h=140) -> np.ndarray:
    th = _prep_rank_bin_otsu(img_rgb, target_h)
    th = cv2.morphologyEx(th, cv2.MORPH_OPEN, np.ones((1,1), np.uint8))
    return th

def _largest_cnt(th: np.ndarray):
    try:
        cnts,_ = cv2.findContours(255-th, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    except Exception:
        cnts = []
    if not cnts: return None
    c = max(cnts, key=cv2.contourArea)
    if cv2.contourArea(c) < 10: return None
    return c

def _hu_vec(cnt) -> np.ndarray:
    hu = cv2.HuMoments(cv2.moments(cnt)).flatten()
    return -np.sign(hu) * np.log10(np.abs(hu) + 1e-12)

_RANK_DB: Dict[str, List[np.ndarray]] = {}  # label -> list[hu]

def _ensure_rank_db():
    global _RANK_DB
    if _RANK_DB: return
    root = Path(os.getenv("POKERIA_RANKS_DIR", str(_default_ranks_dir())))
    if not root.exists(): return
    for lab in list(RANK_ALLOW):
        files = list((root/lab).glob("*.png")) + list(root.glob(f"{lab}_*.png"))
        for p in files:
            try:
                bgr = cv2.imread(str(p), cv2.IMREAD_COLOR)
                if bgr is None: continue
                rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
                th  = _to_bin_rank_for_match(rgb, 140)
                cnt = _largest_cnt(th)
                if cnt is None: continue
                hu  = _hu_vec(cnt)
                _RANK_DB.setdefault(lab, []).append(hu)
            except Exception:
                continue

def _rank_from_templates(rank_rgb) -> Tuple[Optional[str], float]:
    _ensure_rank_db()
    if not _RANK_DB: return None, 0.0
    th  = _to_bin_rank_for_match(rank_rgb, 140)
    cnt = _largest_cnt(th)
    if cnt is None: return None, 0.0
    hu  = _hu_vec(cnt)
    best = None; second = None
    for lab, hus in _RANK_DB.items():
        for hu_t in hus:
            d = float(np.linalg.norm(hu - hu_t))
            if (best is None) or d < best[0]:
                second = best
                best   = (d, lab)
            elif (second is None) or d < second[0]:
                second = (d, lab)
    if best is None: return None, 0.0
    d1, lab1 = best
    d2       = second[0] if second is not None else d1 + 1.0
    margin   = max(0.0, d2 - d1)
    conf     = 0.5 * (1.0/(1.0+d1)) + 0.5 * min(1.0, margin/(d1+0.5))
    return lab1, float(min(0.99, conf))

# ───────── Lecture RANK (template-first + 1 seule OCR fallback)
def _read_rank(engine: EasyOCREngine, rank_rgb) -> Tuple[Optional[str], float, Dict]:
    if not _nonempty(rank_rgb):
        return None, 0.0, {"error": "empty_rank"}

    # 0) Essai ultra-rapide par templates (si base chargée)
    lab_tm, conf_tm = _rank_from_templates(rank_rgb)
    if lab_tm in RANK_SET and conf_tm >= 0.93:
        return lab_tm, float(conf_tm), {"src":"tm_fast"}

    # 1) OCR (UNE seule variante rapide Otsu)
    th = _prep_rank_bin_otsu(rank_rgb, 112)
    txt, conf, raw = engine.read_text(cv2.cvtColor(th, cv2.COLOR_GRAY2RGB), allowlist=RANK_ALLOW)
    toks  = [t for (_b,t,_c) in (raw or []) if t and t.strip()]
    guess = _rank_cleanup("".join(toks or [txt or ""]))
    best_code, best_conf, best_meta = (guess if guess in RANK_SET else None), float(conf or 0.0), {"bin": th, "src": "ocr"}

    # 2) Q vs 9 si conf moyenne
    if best_code in ("Q","9") and best_conf < 0.90 and "bin" in best_meta:
        best_code = _q_vs_9_heuristic(best_meta["bin"], best_code)

    # 3) Fallback templates si doute
    if (best_code is None) or (best_conf < 0.88) or (best_code in ("Q","9") and best_conf < 0.97):
        lab_tm2, conf_tm2 = _rank_from_templates(rank_rgb)
        if lab_tm2 in RANK_SET and conf_tm2 >= best_conf:
            best_code, best_conf, best_meta = lab_tm2, conf_tm2, {"src":"tm"}

    return best_code, best_conf, best_meta

# ───────── Lecture SUIT
def _read_suit(suit_rgb) -> Tuple[Optional[str], float, Dict]:
    if not _nonempty(suit_rgb):
        return None, 0.0, {"error":"empty_suit"}
    hint = _suit_color_hint(suit_rgb)
    lab, conf, meta = _SUITS_HU.classify(suit_rgb, color_hint=hint)
    conf = float(conf or 0.0)
    meta = meta or {}

    # Cohérence couleur: pénalise les incohérences fortes
    rr = red_ratio(suit_rgb)
    strong_red   = rr >= 0.12
    strong_black = rr <= 0.01
    if lab in {"h","d"} and rr < 0.02:
        conf *= 0.6
    if lab in {"s","c"} and rr > 0.08:
        conf *= 0.6

    if (lab not in SUITS) or conf < 0.70:
        # dernier fallback sur la couleur si vraiment rien
        lab = ("h" if hint=="red" else "s") if (lab not in SUITS) else lab
        conf = max(conf, 0.5)
    return lab, conf, {"color_hint":hint, "rr":float(rr), "strong_red":bool(strong_red), "strong_black":bool(strong_black), **meta}

# ───────── défauts si pas de sous-ROIs dans YAML
def _default_rank_rel() -> Tuple[float,float,float,float]:
    return (0.02, 0.02, 0.52, 0.56)
def _default_suit_rel() -> Tuple[float,float,float,float]:
    return (0.56, 0.06, 0.38, 0.44)

# ───────── API (stricte, avec abstention & tolérance board)
def read_card(engine: EasyOCREngine, crop_rgb, roi_name: Optional[str]=None, cfg: Optional[dict]=None):
    """
    Lit une carte depuis un crop RGB (ROI carte).
    - Détecte d'abord la PRÉSENCE de carte (score/bords/blancs).
    - RANK: template-first, puis 1 OCR Otsu (light), fallback template si doute.
    - SUIT: Hu + couleur (cohérence rouge/noir).
    - Seuils stricts via YAML/env → abstention (None) si non fiable.
    """
    if not _nonempty(crop_rgb):
        return None, {"roi_name":roi_name, "error":"empty"}

    cfgc = _get_card_ocr_cfg(cfg or {})
    is_board = isinstance(roi_name, str) and roi_name.startswith("board_card_")

    # 0) Présence de carte ? (board plus permissif)
    min_edge = cfgc["min_edge_density"]
    min_white= cfgc["min_white_ratio"]
    min_score= cfgc["min_card_score"]
    if is_board and cfgc.get("board_tolerant", True):
        min_edge = cfgc.get("min_edge_density_board", min_edge)
        min_white= cfgc.get("min_white_ratio_board",  min_white)
        min_score= cfgc.get("min_card_score_board",   min_score)

    score, present = card_presence_score(crop_rgb, min_edge_density=min_edge, min_white_ratio=min_white)
    if cfgc["strict"] and (not present or score < min_score):
        return None, {"roi_name":roi_name, "present":False, "score":float(score)}

    h,w = crop_rgb.shape[:2]

    # RANK patch
    rank_patch = None
    if cfg and roi_name:
        rank_rel = (cfg.get("rois_hint",{}).get(roi_name, {}) or {}).get("rank_rel")
        if rank_rel: rank_patch = _roi_from_rel(crop_rgb, rank_rel)
    if rank_patch is None:
        rx,ry,rw,rh = _default_rank_rel()
        rank_patch = crop_rgb[int(ry*h):int((ry+rh)*h), int(rx*w):int((rx+rw)*w)].copy()

    r_code, r_conf, r_meta = _read_rank(engine, rank_patch)

    # SUIT patch
    suit_patch = None
    if cfg and roi_name:
        suit_rel = (cfg.get("rois_hint",{}).get(roi_name, {}) or {}).get("suit_rel")
        if suit_rel: suit_patch = _roi_from_rel(crop_rgb, suit_rel)
    if suit_patch is None:
        sx,sy,sw,sh = _default_suit_rel()
        suit_patch = crop_rgb[int(sy*h):int((sy+sh)*h), int(sx*w):int((sx+sw)*w)].copy()

    s_code, s_conf, s_meta = _read_suit(suit_patch)

    # Sécurité Q/9 finale
    if r_code in ("Q","9") and r_conf < 0.90 and "bin" in r_meta:
        r_code = _q_vs_9_heuristic(r_meta["bin"], r_code)

    # Seuils d'acceptation finaux (board plus tolérant)
    mr = cfgc["min_rank_conf_board"] if (is_board and cfgc.get("board_tolerant", True)) else cfgc["min_rank_conf"]
    ms = cfgc["min_suit_conf_board"] if (is_board and cfgc.get("board_tolerant", True)) else cfgc["min_suit_conf"]

    if cfgc["strict"]:
        if r_conf < mr:
            r_code = None
        if s_conf < ms:
            # si suit un peu bas mais hint couleur très marqué, tolère pour board
            if is_board and cfgc.get("board_tolerant", True):
                strong_hint = bool(s_meta.get("strong_red") or s_meta.get("strong_black"))
                if r_code and (r_conf >= (mr + 0.03)) and strong_hint and (s_conf >= max(0.50, ms - 0.1)):
                    pass  # accepte
                else:
                    s_code = None
            else:
                s_code = None

    card = f"{r_code}{s_code}" if (r_code and s_code) else None
    return card, {
        "roi_name": roi_name,
        "present": True,
        "score": float(score),
        "rank_code": r_code, "rank_conf": float(r_conf), **({k:v for k,v in (r_meta or {}).items() if k!="rank_patch"}),
        "suit_code": s_code, "suit_conf": float(s_conf), **(s_meta or {})
    }
