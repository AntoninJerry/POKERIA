# src/ocr/suit_shape.py
from __future__ import annotations
import os, cv2, numpy as np
from pathlib import Path
from typing import Optional, Tuple, Dict, List

# NB: ce module est léger; il charge les templates une seule fois.

def _default_suits_dir() -> Path:
    here = Path(__file__).resolve()
    repo = here.parents[2]  # .../pokeria/
    return repo / "assets" / "templates" / "suits"

TEMPL_DIR = Path(os.getenv("POKERIA_SUITS_DIR", str(_default_suits_dir())))

def _prep_bin_otsu(img_rgb, target_h=120):
    gray = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2GRAY)
    gray = cv2.createCLAHE(3.0, (8,8)).apply(gray)
    g = cv2.GaussianBlur(gray,(3,3),0)
    _, th = cv2.threshold(g,0,255,cv2.THRESH_BINARY+cv2.THRESH_OTSU)
    if gray.mean() < 127: th = 255 - th
    h,w = th.shape[:2]; s = target_h/max(1.0,h)
    return cv2.resize(th,(max(1,int(w*s)), int(target_h)), interpolation=cv2.INTER_CUBIC)

def _largest_contour(th):
    try:
        cnts,_ = cv2.findContours(255-th, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    except Exception:
        cnts = []
    if not cnts: return None
    cnt = max(cnts, key=cv2.contourArea)
    if cv2.contourArea(cnt) < 12: return None
    return cnt

def _hu_vec(cnt):
    hu = cv2.HuMoments(cv2.moments(cnt)).flatten()
    return -np.sign(hu) * np.log10(np.abs(hu) + 1e-12)

def _geom_feats(cnt):
    area = cv2.contourArea(cnt)
    hull = cv2.convexHull(cnt)
    hull_area = max(1.0, cv2.contourArea(hull))
    solidity = float(area)/hull_area
    rect = cv2.minAreaRect(cnt); (w,h) = rect[1]
    if w<1 or h<1:
        ar = 1.0; ang = 0.0
    else:
        ar = float(min(w,h)/max(w,h))
        ang = abs(rect[2]);  ang = 180-ang if ang>90 else ang
    return {"solidity":solidity, "aspect":ar, "angle":ang}

class SuitHu:
    """
    k-NN (k=1) sur Hu + tie-break géométrique (angle/aspect/solidity).
    Templates: assets/templates/suits/{h,d,s,c}/*.png ou h_*.png …
    """
    def __init__(self, templ_dir: Optional[str]=None):
        self.templ_dir = Path(templ_dir) if templ_dir else TEMPL_DIR
        self.db: List[Tuple[str, np.ndarray, Dict]] = []
        self._load_templates()
        if os.getenv("POKERIA_DEBUG_SUITS","0")=="1":
            print(f"[SuitHu] dir={self.templ_dir} counts={self.template_counts()}")

    def template_counts(self) -> Dict[str,int]:
        cnt = {"h":0,"d":0,"s":0,"c":0}
        for lab,_hu,_geo in self.db:
            if lab in cnt: cnt[lab]+=1
        return cnt

    def templates_dir(self) -> str:
        return str(self.templ_dir)

    def _load_templates(self):
        if not self.templ_dir.exists():
            self.templ_dir.mkdir(parents=True, exist_ok=True)
        for lab in ["h","d","s","c"]:
            files = list(self.templ_dir.glob(f"{lab}_*.png")) + list((self.templ_dir/lab).glob("*.png"))
            for p in files:
                try:
                    bgr = cv2.imread(str(p), cv2.IMREAD_COLOR)
                    if bgr is None: continue
                    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
                    th  = _prep_bin_otsu(rgb, 120)
                    cnt = _largest_contour(th)
                    if cnt is None: continue
                    hu  = _hu_vec(cnt)
                    geo = _geom_feats(cnt)
                    self.db.append((lab, hu, geo))
                except Exception:
                    continue

    def classify(self, suit_patch_rgb, color_hint: Optional[str]=None) -> Tuple[Optional[str], float, Dict]:
        if suit_patch_rgb is None or suit_patch_rgb.size==0:
            return None, 0.0, {"reason":"empty_patch"}

        th  = _prep_bin_otsu(suit_patch_rgb, 120)
        cnt = _largest_contour(th)
        if cnt is None:
            return None, 0.0, {"reason":"no_cnt"}

        hu  = _hu_vec(cnt)
        geo = _geom_feats(cnt)

        allowed = {"h","d","s","c"}
        if color_hint == "red":   allowed = {"h","d"}
        elif color_hint == "black": allowed = {"s","c"}

        best, second = None, None
        for lab,hu_t,_geo_t in self.db:
            if lab not in allowed: continue
            d = float(np.linalg.norm(hu - hu_t))
            if (best is None) or (d < best[0]):
                second = best; best = (d, lab)
            elif (second is None) or (d < second[0]):
                second = (d, lab)

        if best is None:
            if color_hint == "red":
                is_diamond = (abs(geo["angle"]-45) < 15) and (geo["aspect"]>0.75) and (geo["solidity"]>0.92)
                return ("d" if is_diamond else "h"), 0.6, {"reason":"geom_fallback_red", **geo}
            if color_hint == "black":
                is_club = (geo["aspect"]>0.85) and (geo["solidity"]>0.93)
                return ("c" if is_club else "s"), 0.55, {"reason":"geom_fallback_black", **geo}
            return None, 0.0, {"reason":"no_templates", **geo}

        d1, lab1 = best
        d2       = second[0] if second is not None else d1 + 1.0
        margin   = max(0.0, d2 - d1)
        conf     = 0.5*(1.0/(1.0+d1)) + 0.5*min(1.0, margin/(d1+0.5))

        if color_hint == "red":
            is_diamond = (abs(geo["angle"]-45) < 15) and (geo["aspect"]>0.75) and (geo["solidity"]>0.90)
            if (lab1 in {"h","d"} and margin < 0.15) or conf < 0.4:
                lab1 = "d" if is_diamond else "h"
                conf = max(conf, 0.65)

        if color_hint == "black" and conf < 0.4:
            is_club = (geo["aspect"]>0.85) and (geo["solidity"]>0.93)
            lab1 = "c" if is_club else "s"
            conf = max(conf, 0.60)

        return lab1, float(conf), {"d1":d1, "d2":d2, "margin":margin, **geo}