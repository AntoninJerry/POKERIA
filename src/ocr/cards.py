import cv2, numpy as np
from typing import Optional, Tuple, Dict
from src.ocr.engine import EasyOCREngine

RANK_ALLOW = "0123456789TJQKA"
RANK_SET = set(list("23456789TJQKA"))

# --------- Prétraitements ----------
def _prep_bin_otsu(img_rgb, target_h=140):
    gray = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2GRAY)
    gray = cv2.createCLAHE(3.0,(8,8)).apply(gray)
    g = cv2.GaussianBlur(gray,(3,3),0)
    _, th = cv2.threshold(g,0,255,cv2.THRESH_BINARY+cv2.THRESH_OTSU)
    if gray.mean() < 127: th = 255-th
    h,w = th.shape[:2]
    s = target_h/float(max(1,h))
    return cv2.resize(th,(max(1,int(w*s)), target_h),interpolation=cv2.INTER_CUBIC)

def _prep_bin_adapt(img_rgb, target_h=140):
    gray = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2GRAY)
    gray = cv2.createCLAHE(3.0,(8,8)).apply(gray)
    g = cv2.GaussianBlur(gray,(3,3),0)
    th = cv2.adaptiveThreshold(g,255,cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                               cv2.THRESH_BINARY,31,5)
    if gray.mean() < 127: th = 255-th
    h,w = th.shape[:2]
    s = target_h/float(max(1,h))
    return cv2.resize(th,(max(1,int(w*s)), target_h),interpolation=cv2.INTER_CUBIC)

# --------- Utilitaires ----------
def _nonempty(img): return img is not None and hasattr(img,"size") and img.size>0

def _rank_q_vs_9(corner_rgb, rank_code, alt_code, margin: float):
    if {rank_code, alt_code} != {"Q","9"} or margin>=0.05: return rank_code
    h,w = corner_rgb.shape[:2]
    br = corner_rgb[int(0.60*h):h, int(0.55*w):w]
    if not _nonempty(br): return rank_code
    th = _prep_bin_otsu(br, target_h=80)
    black_ratio = float(np.count_nonzero(255-th))/(th.size+1e-6)
    return "Q" if black_ratio>0.20 else "9"

def _suit_by_color(corner_rgb) -> str:
    hsv = cv2.cvtColor(corner_rgb, cv2.COLOR_RGB2HSV)
    mask1 = cv2.inRange(hsv, (0,70,40), (10,255,255))
    mask2 = cv2.inRange(hsv, (170,70,40), (180,255,255))
    red_ratio = float(np.count_nonzero(mask1|mask2))/(corner_rgb.size+1e-6)
    return "h" if red_ratio>0.05 else "s"

# --------- OCR multi-pass ----------
def _read_rank(engine: EasyOCREngine, corner_rgb) -> Tuple[Optional[str], float, Dict]:
    variants = [_prep_bin_otsu(corner_rgb,140), _prep_bin_adapt(corner_rgb,140)]
    best = None
    for i,th in enumerate(variants):
        img3 = cv2.cvtColor(th, cv2.COLOR_GRAY2RGB)
        txt, conf, raw = engine.read_text(img3, allowlist=RANK_ALLOW)
        toks = [t for (_b,t,_c) in (raw or []) if t.strip()]
        guess = "".join(toks or [txt or ""]).upper().replace(" ","")
        guess = guess.replace("I","1").replace("O","0").replace("D","Q")
        if "10" in guess: guess="T"
        elif guess and guess[0] in RANK_SET: guess=guess[0]
        else: guess=None
        if guess and (best is None or conf>best["conf"]):
            best={"rank":guess,"conf":conf,"var":i}
    if best: return best["rank"],best["conf"],best
    return None,0.0,{}

def _read_suit(engine: EasyOCREngine, corner_rgb) -> Tuple[Optional[str], float]:
    # Ici on ne fait que rouge/noir simple, car les symboles sont très confus.
    hint = _suit_by_color(corner_rgb)
    return hint, 0.7

# --------- API ----------
def read_card(engine: EasyOCREngine, crop_rgb, roi_name: Optional[str]=None):
    if not _nonempty(crop_rgb): 
        return None, {"roi_name":roi_name,"error":"empty"}
    # 1) Coin TL
    h,w = crop_rgb.shape[:2]
    corner = crop_rgb[0:int(0.55*h), 0:int(0.60*w)].copy()
    if not _nonempty(corner): return None, {"roi_name":roi_name,"error":"corner"}
    # 2) Rank
    r_code,r_conf,r_meta = _read_rank(engine,corner)
    # 3) Suit
    s_code,s_conf = _read_suit(engine,corner)
    # 4) Q vs 9 tie-break
    if r_code in ["Q","9"] and r_meta.get("conf",0)<0.7:
        r_code=_rank_q_vs_9(corner,r_code,"Q" if r_code=="9" else "9",0.0)
    card=f"{r_code}{s_code}" if r_code and s_code else None
    return card, {"roi_name":roi_name,"rank_code":r_code,"rank_conf":r_conf,"suit_code":s_code,"suit_conf":s_conf}
