# src/ocr/cards.py
import os, cv2, numpy as np
from typing import Optional, Tuple, Dict, List
from src.ocr.engine import EasyOCREngine
from src.ocr.suit_shape import SuitHu
from src.ocr.template_match import load_templates_from_dir, best_match_rank
from src.ocr.template_match import load_suit_templates_from_dir, best_match_suit


# ====== CONSTANTES ======
RANK_ALLOW = "23456789TJQKA"
RANK_SET = set(RANK_ALLOW)
SUITS = ("h","d","s","c")

_SUITS_HU = SuitHu()

# banque de templates rangs, chargée lazy
_RANK_TEMPLATES: Dict[str, List[np.ndarray]] = {}

def _ensure_rank_bank():
    global _RANK_TEMPLATES
    if _RANK_TEMPLATES:
        return
    root = os.getenv("POKERIA_RANKS_DIR", "assets/templates/ranks")
    _RANK_TEMPLATES = load_templates_from_dir(root, list(RANK_ALLOW))
    # Optionnel: avertir si vide
    if not _RANK_TEMPLATES:
        print(f"[cards] WARN: aucune template de rang trouvée dans {root}")


_SUIT_TEMPLATES = {}
def _ensure_suit_bank():
    global _SUIT_TEMPLATES
    if _SUIT_TEMPLATES: return
    root = os.getenv("POKERIA_SUITS_DIR","assets/templates/suits")
    _SUIT_TEMPLATES = load_suit_templates_from_dir(root)
    if not any(_SUIT_TEMPLATES.values()):
        print(f"[cards] WARN: aucune template de suit trouvée dans {root}")

# ----------------- utils -----------------
def _nonempty(img) -> bool:
    return img is not None and hasattr(img, "size") and img.size > 0 and img.shape[0] > 0 and img.shape[1] > 0

def _roi_from_rel(parent_rgb, rel) -> Optional[np.ndarray]:
    if not rel: return None
    H, W = parent_rgb.shape[:2]
    rx, ry, rw, rh = rel
    x = max(0, min(int(rx * W), W - 1))
    y = max(0, min(int(ry * H), H - 1))
    w = max(1, min(int(rw * W), W - x))
    h = max(1, min(int(rh * H), H - y))
    return parent_rgb[y:y+h, x:x+w].copy()

def _prep_rank_bin(img_rgb, target_h=160) -> np.ndarray:
    gray = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2GRAY)
    gray = cv2.createCLAHE(3.0, (8, 8)).apply(gray)
    g = cv2.GaussianBlur(gray, (3, 3), 0)
    th = cv2.adaptiveThreshold(g, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                               cv2.THRESH_BINARY, 31, 5)
    if gray.mean() < 127: th = 255 - th
    h, w = th.shape[:2]; s = target_h / max(1.0, h)
    return cv2.resize(th, (max(1, int(w * s)), int(target_h)), interpolation=cv2.INTER_CUBIC)

def _suit_color_hint(rgb) -> str:
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    m1 = cv2.inRange(hsv, (0, 70, 40), (10, 255, 255))
    m2 = cv2.inRange(hsv, (170, 70, 40), (180, 255, 255))
    red_ratio = float(np.count_nonzero(m1 | m2)) / (rgb.shape[0] * rgb.shape[1] + 1e-6)
    return "red" if red_ratio > 0.04 else "black"

def _rank_cleanup(raw: str) -> str:
    s = (raw or "").upper().replace(" ", "")
    s = s.replace("10", "T").replace("IO", "T").replace("TO", "T").replace("I0", "T")
    for ch in s:
        if ch in RANK_SET:
            return ch
    return ""

def _q_vs_9_heuristic(bin_patch: np.ndarray, guess: str) -> str:
    if guess not in ("Q", "9"): return guess
    img = cv2.morphologyEx(bin_patch, cv2.MORPH_ERODE, np.ones((2,2), np.uint8), iterations=1)
    cnts, _ = cv2.findContours(img, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not cnts: return guess
    cnt = max(cnts, key=cv2.contourArea)
    rect = cv2.minAreaRect(cnt)
    (w, h) = rect[1]
    if w < 1 or h < 1: return guess
    aspect = float(min(w, h) / max(w, h))
    return "Q" if aspect < 0.45 else guess

# ----------------- RANK -----------------
def _read_rank(engine: EasyOCREngine, rank_rgb) -> Tuple[Optional[str], float, Dict]:
    if not _nonempty(rank_rgb):
        return None, 0.0, {"error": "empty_rank"}

    # OCR (whitelist)
    bin1 = _prep_rank_bin(rank_rgb, 160)
    txt, conf, raw = engine.read_text(cv2.cvtColor(bin1, cv2.COLOR_GRAY2RGB), allowlist=RANK_ALLOW)
    toks = [t for (_b, t, _c) in (raw or []) if t and t.strip()]
    guess = _rank_cleanup("".join(toks or [txt or ""]))
    best_code, best_conf, best_meta = guess if guess in RANK_SET else None, float(conf or 0.0), {"bin": bin1, "src": "ocr"}

    # Tie-break Q vs 9 si conf moyenne
    if best_code in ("Q","9") and best_conf < 0.88:
        best_code = _q_vs_9_heuristic(bin1, best_code)

    # Fallback templates si doute (ou None)
    if (best_code is None) or (best_conf < 0.88) or (best_code in ("Q","9") and best_conf < 0.97):
        _ensure_rank_bank()
        if _RANK_TEMPLATES:
            lab, score = best_match_rank(rank_rgb, _RANK_TEMPLATES, (0.7,0.85,1.0))
            if lab in RANK_SET and score >= 0.58:
                best_code, best_conf, best_meta = lab, max(best_conf, min(0.99, 0.85 + score*0.15)), {"tm_score": score, "src": "tm"}

    return best_code, best_conf, best_meta

# ----------------- SUIT -----------------
def _read_suit(suit_rgb) -> Tuple[Optional[str], float, Dict]:
    if not _nonempty(suit_rgb):
        return None, 0.0, {"error": "empty_suit"}

    hint = _suit_color_hint(suit_rgb)

    # 1) Classif. HU
    try:
        lab, conf, meta = _SUITS_HU.classify(suit_rgb, color_hint=hint)
    except TypeError:
        tmp = _SUITS_HU.classify(suit_rgb)
        lab, conf = (tmp[0], float(tmp[1])) if isinstance(tmp, (list, tuple)) and len(tmp) >= 2 else (None, 0.0)
        meta = {}

    conf = float(conf or 0.0)
    meta = meta or {}

    # 2) Fallback TM si invalide ou confiance trop faible
    if (lab not in SUITS) or (conf < 0.70):
        try:
            _ensure_suit_bank()
            # filtre par couleur: rouge -> {h,d} ; noir -> {s,c}
            targ = ("h", "d") if hint == "red" else ("s", "c")
            bank = {k: v for k, v in _SUIT_TEMPLATES.items() if k in targ and v}

            if bank:
                lab_tm, sc = best_match_suit(suit_rgb, bank)  # -> (label, score[0..1])
                if (lab_tm in SUITS) and (sc is not None) and (sc >= 0.58):
                    # rehausse de confiance en douceur, capée à 0.99
                    blended = min(0.99, 0.85 + float(sc) * 0.15)
                    conf = max(conf, blended)
                    lab = lab_tm
                    meta = {**meta, "tm_suit_score": float(sc), "src_suit": "tm"}
        except Exception as e:
            # on n'écrase rien si le fallback plante; on log juste l'erreur
            meta = {**meta, "tm_error": str(e)}

    if lab in SUITS:
        return lab, conf, {"color_hint": hint, **meta}

    # rien de concluant
    return None, conf, {"color_hint": hint, **meta}
# ----------------- défauts si pas de sous-ROIs -----------------
def _default_rank_rel() -> Tuple[float,float,float,float]:
    return (0.02, 0.02, 0.52, 0.56)

def _default_suit_rel() -> Tuple[float,float,float,float]:
    return (0.56, 0.06, 0.38, 0.44)

# ----------------- API -----------------
def read_card(engine: EasyOCREngine, crop_rgb, roi_name: Optional[str] = None, cfg: Optional[dict] = None):
    if not _nonempty(crop_rgb):
        return None, {"roi_name": roi_name, "error": "empty"}

    h, w = crop_rgb.shape[:2]

    # RANK
    rank_patch = None
    if cfg and roi_name:
        rank_rel = (cfg.get("rois_hint", {}).get(roi_name, {}) or {}).get("rank_rel")
        if rank_rel: rank_patch = _roi_from_rel(crop_rgb, rank_rel)
    if rank_patch is None:
        rx, ry, rw, rh = _default_rank_rel()
        rank_patch = crop_rgb[int(ry*h):int((ry+rh)*h), int(rx*w):int((rx+rw)*w)].copy()

    r_code, r_conf, r_meta = _read_rank(engine, rank_patch)

    # SUIT
    suit_patch = None
    if cfg and roi_name:
        suit_rel = (cfg.get("rois_hint", {}).get(roi_name, {}) or {}).get("suit_rel")
        if suit_rel: suit_patch = _roi_from_rel(crop_rgb, suit_rel)
    if suit_patch is None:
        sx, sy, sw, sh = _default_suit_rel()
        suit_patch = crop_rgb[int(sy*h):int((sy+sh)*h), int(sx*w):int((sx+sw)*w)].copy()

    s_code, s_conf, s_meta = _read_suit(suit_patch)

    # Dernière sécurité Q/9
    if r_code in ("Q","9") and "bin" in r_meta and r_conf < 0.88:
        r_code = _q_vs_9_heuristic(r_meta["bin"], r_code)

    card = f"{r_code}{s_code}" if (r_code and s_code) else None
    return card, {
        "roi_name": roi_name,
        "rank_code": r_code, "rank_conf": r_conf, **{k:v for k,v in r_meta.items() if k != "rank_patch"},
        "suit_code": s_code, "suit_conf": s_conf, **(s_meta or {})
    }
